import os
import re
import time
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)

# Permite o Mini App da Vercel acessar o Render
ALLOWED_ORIGINS = [
    "https://bot-raposa-cacadora.vercel.app",
]

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": ALLOWED_ORIGINS,
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": [
                "Content-Type",
                "X-Telegram-Init-Data",
                "Authorization",
            ],
        }
    },
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

# ============================================================
# VARIÁVEIS DE AMBIENTE
# ============================================================

# Shopee
SHOPEE_APP_ID = os.getenv("SHOPEE_APP_ID", "").strip()
SHOPEE_APP_SECRET = os.getenv("SHOPEE_APP_SECRET", "").strip()

# URL da API da Shopee.
# CONFIRA no painel/documentação da sua integração qual endpoint
# sua conta utiliza.
SHOPEE_API_URL = os.getenv(
    "SHOPEE_API_URL",
    ""
).strip()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Segurança opcional do Mini App
TELEGRAM_INIT_DATA_REQUIRED = (
    os.getenv("TELEGRAM_INIT_DATA_REQUIRED", "false").lower()
    == "true"
)

# ============================================================
# CONSTANTES
# ============================================================

REQUEST_TIMEOUT = 30

SHOPEE_DOMAINS = {
    "shopee.com.br",
    "www.shopee.com.br",
    "s.shopee.com.br",
}

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================


def money(value):
    """
    Converte valores para formato brasileiro.
    Exemplo:
        69.99 -> R$ 69,99
    """
    try:
        number = Decimal(str(value))
        return f"R$ {number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (InvalidOperation, ValueError, TypeError):
        return "Preço indisponível"


def percentual(value):
    """
    0.38 -> 38%
    38 -> 38%
    """
    try:
        number = Decimal(str(value))

        if number <= 1:
            number *= 100

        return f"{number:.0f}%"
    except Exception:
        return "N/A"


def validar_url_shopee(url):
    """
    Valida se a URL pertence à Shopee.
    """
    if not url:
        return False

    try:
        parsed = urlparse(url.strip())

        if parsed.scheme not in ("http", "https"):
            return False

        hostname = (parsed.hostname or "").lower()

        return hostname in SHOPEE_DOMAINS

    except Exception:
        return False


def extrair_ids_produto(url):
    """
    Tenta extrair shop_id e item_id de uma URL normal da Shopee.

    Exemplo:
    https://shopee.com.br/product/864885365/58266424970

    Retorna:
        {
            "shop_id": "864885365",
            "item_id": "58266424970"
        }

    Links curtos não possuem necessariamente os IDs no próprio texto.
    Nesse caso retornamos None.
    """

    if not url:
        return None

    match = re.search(
        r"/product/(\d+)/(\d+)",
        url,
        re.IGNORECASE,
    )

    if not match:
        return None

    return {
        "shop_id": match.group(1),
        "item_id": match.group(2),
    }


# ============================================================
# SHOPEE
# ============================================================

def consultar_shopee(shop_id=None, item_id=None, url=None):
    """
    Consulta a integração Shopee.

    ATENÇÃO:
    O formato exato da requisição depende da API/parceiro Shopee
    que sua conta está utilizando.

    O código abaixo foi preparado para receber uma resposta no
    formato que você mostrou na conversa:

    {
        "data": {
            "productOfferV2": {
                "nodes": [...]
            }
        }
    }

    Ajuste apenas a parte da requisição caso seu endpoint exija
    autenticação/assinatura diferente.
    """

    if not SHOPEE_API_URL:
        raise RuntimeError(
            "SHOPEE_API_URL não está configurada no Render."
        )

    if not SHOPEE_APP_ID:
        raise RuntimeError(
            "SHOPEE_APP_ID não está configurado no Render."
        )

    if not SHOPEE_APP_SECRET:
        raise RuntimeError(
            "SHOPEE_APP_SECRET não está configurado no Render."
        )

    logger.info("🛒 Consultando Shopee")

    payload = {
        "app_id": SHOPEE_APP_ID,
        "app_secret": SHOPEE_APP_SECRET,
    }

    if shop_id:
        payload["shop_id"] = shop_id

    if item_id:
        payload["item_id"] = item_id

    if url:
        payload["url"] = url

    response = requests.post(
        SHOPEE_API_URL,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )

    logger.info(
        "📡 Shopee respondeu HTTP %s",
        response.status_code,
    )

    if response.status_code >= 400:
        logger.error(
            "Resposta Shopee: %s",
            response.text[:2000],
        )

        raise RuntimeError(
            f"Shopee respondeu HTTP {response.status_code}"
        )

    try:
        data = response.json()
    except Exception:
        raise RuntimeError(
            "Shopee não retornou JSON válido."
        )

    return data


def encontrar_produto(data, shop_id=None, item_id=None):
    """
    Procura o produto dentro da resposta productOfferV2.
    """

    try:
        nodes = (
            data
            .get("data", {})
            .get("productOfferV2", {})
            .get("nodes", [])
        )
    except Exception:
        nodes = []

    if not nodes:
        raise RuntimeError(
            "Nenhum produto foi encontrado na resposta da Shopee."
        )

    # Se temos item_id, procuramos exatamente ele.
    if item_id:
        for produto in nodes:
            if str(produto.get("itemId")) == str(item_id):
                return produto

    # Se não encontrou exatamente, devolve o primeiro.
    return nodes[0]


# ============================================================
# NORMALIZAÇÃO DO PRODUTO
# ============================================================

def normalizar_produto(produto):
    """
    Transforma a resposta da Shopee em um formato simples
    para o Mini App e para o Telegram.
    """

    nome = produto.get(
        "productName",
        "Produto Shopee",
    )

    preco = produto.get("price")

    preco_min = produto.get("priceMin", preco)
    preco_max = produto.get("priceMax", preco)

    desconto = produto.get(
        "priceDiscountRate",
        0,
    )

    comissao = produto.get(
        "commission",
        0,
    )

    rating = produto.get(
        "ratingStar",
        0,
    )

    vendas = produto.get(
        "sales",
        0,
    )

    imagem = produto.get(
        "imageUrl",
        "",
    )

    loja = produto.get(
        "shopName",
        "Loja Shopee",
    )

    product_link = produto.get(
        "productLink",
        "",
    )

    offer_link = produto.get(
        "offerLink",
        product_link,
    )

    return {
        "nome": nome,
        "item_id": produto.get("itemId"),
        "shop_id": produto.get("shopId"),
        "preco": preco,
        "preco_min": preco_min,
        "preco_max": preco_max,
        "preco_formatado": money(preco),
        "preco_min_formatado": money(preco_min),
        "preco_max_formatado": money(preco_max),
        "desconto": desconto,
        "desconto_formatado": percentual(desconto),
        "comissao": comissao,
        "comissao_formatada": money(comissao),
        "comissao_percentual": percentual(
            produto.get("commissionRate")
        ),
        "avaliacao": rating,
        "vendas": vendas,
        "imagem": imagem,
        "loja": loja,
        "link_produto": product_link,
        "link_oferta": offer_link,
        "categoria": produto.get(
            "productCatIds",
            [],
        ),
    }


# ============================================================
# MENSAGEM TELEGRAM
# ============================================================

def montar_mensagem(produto):
    """
    Cria a publicação que será enviada ao canal.
    """

    nome = produto["nome"]

    # Limita títulos muito grandes.
    if len(nome) > 180:
        nome = nome[:177] + "..."

    mensagem = (
        f"🔥 <b>OFERTA SHOPEE</b>\n\n"
        f"🛍️ <b>{nome}</b>\n\n"
        f"💰 <b>Preço:</b> {produto['preco_formatado']}\n"
    )

    if produto["desconto"] not in (None, "", 0, "0"):
        mensagem += (
            f"🏷️ <b>Desconto:</b> "
            f"{produto['desconto_formatado']}\n"
        )

    if produto["avaliacao"]:
        mensagem += (
            f"⭐ <b>Avaliação:</b> "
            f"{produto['avaliacao']}\n"
        )

    if produto["vendas"]:
        mensagem += (
            f"📦 <b>Vendas:</b> "
            f"{produto['vendas']}\n"
        )

    mensagem += (
        f"🏪 <b>Loja:</b> "
        f"{produto['loja']}\n\n"
        f"💸 <b>Comissão:</b> "
        f"{produto['comissao_formatada']}\n\n"
        f"🛒 <a href=\"{produto['link_oferta']}\">"
        f"COMPRAR AGORA</a>"
    )

    return mensagem


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(produto):
    """
    Envia o produto para o canal Telegram.

    Se houver imagem, tenta enviar foto.
    Caso contrário, envia somente texto.
    """

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN não configurado."
        )

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID não configurado."
        )

    mensagem = montar_mensagem(produto)

    base_url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}"
    )

    imagem = produto.get("imagem")

    # --------------------------------------------------------
    # TENTA ENVIAR FOTO
    # --------------------------------------------------------

    if imagem:
        try:
            response = requests.post(
                f"{base_url}/sendPhoto",
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "photo": imagem,
                    "caption": mensagem,
                    "parse_mode": "HTML",
                },
                timeout=REQUEST_TIMEOUT,
            )

            if response.ok:
                logger.info(
                    "✅ Produto enviado com imagem."
                )

                return response.json()

            logger.warning(
                "⚠️ Falha no envio da imagem: %s",
                response.text[:500],
            )

        except Exception as exc:
            logger.warning(
                "⚠️ Erro ao enviar imagem: %s",
                exc,
            )

    # --------------------------------------------------------
    # FALLBACK: TEXTO
    # --------------------------------------------------------

    response = requests.post(
        f"{base_url}/sendMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": mensagem,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=REQUEST_TIMEOUT,
    )

    if not response.ok:
        logger.error(
            "❌ Telegram recusou envio: %s",
            response.text[:1000],
        )

        raise RuntimeError(
            "Telegram recusou o envio."
        )

    logger.info(
        "✅ Produto enviado ao canal."
    )

    return response.json()


# ============================================================
# AUTENTICAÇÃO BÁSICA DO MINI APP
# ============================================================

def validar_miniapp():
    """
    Por enquanto mantém o fluxo simples.

    Se TELEGRAM_INIT_DATA_REQUIRED=false,
    o endpoint funciona normalmente para testes.

    Quando o sistema estiver funcionando, podemos ativar
    a validação criptográfica do initData do Telegram.
    """

    if not TELEGRAM_INIT_DATA_REQUIRED:
        return True

    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        "",
    ).strip()

    if not init_data:
        logger.warning(
            "❌ X-Telegram-Init-Data ausente."
        )

        return False

    # Aqui entra a validação oficial do initData.
    # Não devemos simplesmente confiar no header em produção.

    return True


# ============================================================
# ROTAS
# ============================================================

@app.route("/", methods=["GET", "HEAD"])
def index():
    return jsonify({
        "ok": True,
        "service": "Raposa Caçadora",
        "integracao": "Shopee",
        "status": "online",
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "status": "online",
        "shopee_configurada": bool(
            SHOPEE_APP_ID
            and SHOPEE_APP_SECRET
            and SHOPEE_API_URL
        ),
        "telegram_configurado": bool(
            TELEGRAM_BOT_TOKEN
            and TELEGRAM_CHAT_ID
        ),
    })


@app.route(
    "/api/configurar",
    methods=["OPTIONS"],
)
def configurar_options():
    """
    Responde ao preflight CORS.
    """

    return "", 204


@app.route(
    "/api/configurar",
    methods=["POST"],
)
def configurar():
    """
    Endpoint principal do Mini App.

    JSON esperado:

    {
        "link": "https://shopee.com.br/product/864885365/58266424970",
        "quantidade": 1,
        "intervalo": 1,
        "enviar": true
    }
    """

    logger.info(
        "📥 POST /api/configurar"
    )

    if not validar_miniapp():
        return jsonify({
            "ok": False,
            "error": "Mini App não autorizado.",
        }), 401

    data = request.get_json(
        silent=True
    ) or {}

    logger.info(
        "JSON recebido: %s",
        data,
    )

    link = str(
        data.get("link", "")
    ).strip()

    if not link:
        return jsonify({
            "ok": False,
            "error": "Informe o link da Shopee.",
        }), 400

    if not validar_url_shopee(link):
        return jsonify({
            "ok": False,
            "error": "O link informado não parece ser da Shopee.",
        }), 400

    # Quantidade
    try:
        quantidade = int(
            data.get("quantidade", 1)
        )
    except Exception:
        quantidade = 1

    quantidade = max(
        1,
        min(quantidade, 20),
    )

    # Intervalo em segundos
    try:
        intervalo = float(
            data.get("intervalo", 1)
        )
    except Exception:
        intervalo = 1

    intervalo = max(
        0,
        min(intervalo, 3600),
    )

    # Por padrão NÃO enviamos automaticamente durante testes.
    enviar = bool(
        data.get("enviar", False)
    )

    try:
        ids = extrair_ids_produto(link)

        shop_id = (
            ids.get("shop_id")
            if ids
            else None
        )

        item_id = (
            ids.get("item_id")
            if ids
            else None
        )

        logger.info(
            "🔎 shop_id=%s item_id=%s",
            shop_id,
            item_id,
        )

        # ----------------------------------------------------
        # CONSULTA SHOPEE
        # ----------------------------------------------------

        resposta = consultar_shopee(
            shop_id=shop_id,
            item_id=item_id,
            url=link,
        )

        produto_bruto = encontrar_produto(
            resposta,
            shop_id=shop_id,
            item_id=item_id,
        )

        produto = normalizar_produto(
            produto_bruto
        )

        logger.info(
            "✅ Produto encontrado: %s",
            produto["nome"],
        )

        resultados_envio = []

        # ----------------------------------------------------
        # ENVIO TELEGRAM
        # ----------------------------------------------------

        if enviar:

            for i in range(quantidade):

                resultado = enviar_telegram(
                    produto
                )

                resultados_envio.append({
                    "numero": i + 1,
                    "ok": True,
                })

                # Não espera depois do último.
                if i < quantidade - 1:
                    time.sleep(intervalo)

        return jsonify({
            "ok": True,
            "message": (
                "Produto encontrado com sucesso."
                if not enviar
                else "Produto processado e enviado."
            ),
            "produto": produto,
            "quantidade": quantidade,
            "intervalo": intervalo,
            "enviado": enviar,
            "envios": resultados_envio,
        })

    except Exception as exc:

        logger.exception(
            "❌ Erro em /api/configurar"
        )

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


# ============================================================
# ENDPOINT PARA TESTAR O TELEGRAM
# ============================================================

@app.route(
    "/api/testar-telegram",
    methods=["POST", "OPTIONS"],
)
def testar_telegram():

    if request.method == "OPTIONS":
        return "", 204

    produto_teste = {
        "nome": "Produto de teste Shopee",
        "preco": "39.90",
        "preco_formatado": "R$ 39,90",
        "desconto": 20,
        "desconto_formatado": "20%",
        "avaliacao": "4.9",
        "vendas": 100,
        "loja": "Loja Teste",
        "comissao": "10",
        "comissao_formatada": "R$ 10,00",
        "link_oferta": "https://shopee.com.br/",
        "imagem": "",
    }

    try:

        resultado = enviar_telegram(
            produto_teste
        )

        return jsonify({
            "ok": True,
            "message": "Teste enviado ao Telegram.",
            "telegram": resultado,
        })

    except Exception as exc:

        logger.exception(
            "Erro no teste Telegram."
        )

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


# ============================================================
# TRATAMENTO DE ERROS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "ok": False,
        "error": "Rota não encontrada.",
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "ok": False,
        "error": "Método HTTP não permitido para esta rota.",
    }), 405


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "ok": False,
        "error": "Erro interno do servidor.",
    }), 500


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    logger.info(
        "🚀 Servidor iniciando na porta %s",
        port,
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
