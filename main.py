import os
import re
import time
import json
import hashlib
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse, parse_qs, unquote

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS


# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)

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

# ------------------------------------------------------------
# SHOPEE
# ------------------------------------------------------------

SHOPEE_APP_ID = os.getenv(
    "SHOPEE_APP_ID",
    "",
).strip()

SHOPEE_APP_SECRET = os.getenv(
    "SHOPEE_APP_SECRET",
    "",
).strip()

SHOPEE_API_URL = os.getenv(
    "SHOPEE_API_URL",
    "https://open-api.affiliate.shopee.com.br/graphql",
).strip()


# ------------------------------------------------------------
# TELEGRAM
#
# Aceita tanto:
# TELEGRAM_TOKEN / CHAT_ID
#
# quanto:
# TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
# ------------------------------------------------------------

TELEGRAM_BOT_TOKEN = (
    os.getenv("TELEGRAM_TOKEN", "").strip()
    or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
)

TELEGRAM_CHAT_ID = (
    os.getenv("CHAT_ID", "").strip()
    or os.getenv("TELEGRAM_CHAT_ID", "").strip()
)


# ------------------------------------------------------------
# SEGURANÇA DO MINI APP
# ------------------------------------------------------------

TELEGRAM_INIT_DATA_REQUIRED = (
    os.getenv(
        "TELEGRAM_INIT_DATA_REQUIRED",
        "false",
    ).strip().lower()
    == "true"
)


# ============================================================
# CONSTANTES
# ============================================================

REQUEST_TIMEOUT = 30
SHORT_URL_TIMEOUT = 15

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
    Converte valor para moeda brasileira.

    Exemplos:
        69.99 -> R$ 69,99
        "69.99" -> R$ 69,99
    """

    if value is None or value == "":
        return "Preço indisponível"

    try:
        number = Decimal(str(value))

        return (
            f"R$ {number:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return "Preço indisponível"


def percentual(value):
    """
    Converte porcentagem.

    Exemplos:
        0.38 -> 38%
        38 -> 38%
    """

    if value is None or value == "":
        return "N/A"

    try:
        number = Decimal(str(value))

        if number <= 1:
            number *= 100

        return f"{number:.0f}%"

    except Exception:
        return "N/A"


def validar_url_shopee(url):
    """
    Verifica se a URL pertence à Shopee.
    """

    if not url:
        return False

    try:
        parsed = urlparse(url.strip())

        if parsed.scheme not in (
            "http",
            "https",
        ):
            return False

        hostname = (
            parsed.hostname or ""
        ).lower()

        return hostname in SHOPEE_DOMAINS

    except Exception:
        return False


# ============================================================
# RESOLUÇÃO DE LINK CURTO
# ============================================================

def resolver_url_shopee(url):
    """
    Resolve links curtos da Shopee.

    Exemplo:

        https://s.shopee.com.br/xxxx

    pode redirecionar para:

        https://shopee.com.br/produto-i.123456.987654

    Retorna a URL final quando possível.
    """

    if not url:
        return url

    try:

        parsed = urlparse(url)

        hostname = (
            parsed.hostname or ""
        ).lower()

        # Se não é link curto, não precisamos resolver.
        if hostname != "s.shopee.com.br":
            return url

        logger.info(
            "🔗 Resolvendo link curto da Shopee..."
        )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Linux; Android 15) "
                "AppleWebKit/537.36 "
                "Chrome/151.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
        }

        # HEAD primeiro.
        try:

            response = requests.head(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=SHORT_URL_TIMEOUT,
            )

            final_url = response.url

            if final_url and final_url != url:

                logger.info(
                    "🔗 Link resolvido: %s",
                    final_url,
                )

                return final_url

        except Exception as exc:

            logger.warning(
                "⚠️ HEAD falhou ao resolver link: %s",
                exc,
            )

        # Fallback GET.
        response = requests.get(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=SHORT_URL_TIMEOUT,
        )

        final_url = response.url

        if final_url:

            logger.info(
                "🔗 URL final: %s",
                final_url,
            )

            return final_url

    except Exception as exc:

        logger.warning(
            "⚠️ Não foi possível resolver link curto: %s",
            exc,
        )

    return url


# ============================================================
# EXTRAÇÃO DOS IDS DA SHOPEE
# ============================================================

def extrair_ids_produto(url):
    """
    Extrai shop_id e item_id de vários formatos de URL Shopee.

    Formato 1:
        /product/123/456

    Formato 2:
        /produto-i.123.456

    Formato 3:
        /opaanlp/123/456

    Formato 4:
        ?shopid=123&itemid=456
    """

    if not url:
        return None

    url = unquote(url.strip())

    # --------------------------------------------------------
    # /product/{shop_id}/{item_id}
    # --------------------------------------------------------

    match = re.search(
        r"/product/(\d+)/(\d+)",
        url,
        re.IGNORECASE,
    )

    if match:

        return {
            "shop_id": match.group(1),
            "item_id": match.group(2),
        }

    # --------------------------------------------------------
    # /opaanlp/{shop_id}/{item_id}
    # --------------------------------------------------------

    match = re.search(
        r"/opaanlp/(\d+)/(\d+)",
        url,
        re.IGNORECASE,
    )

    if match:

        return {
            "shop_id": match.group(1),
            "item_id": match.group(2),
        }

    # --------------------------------------------------------
    # slug-i.{shop_id}.{item_id}
    # --------------------------------------------------------

    match = re.search(
        r"-i\.(\d+)\.(\d+)",
        url,
        re.IGNORECASE,
    )

    if match:

        return {
            "shop_id": match.group(1),
            "item_id": match.group(2),
        }

    # --------------------------------------------------------
    # shopid / itemid na query string
    # --------------------------------------------------------

    try:

        parsed = urlparse(url)

        params = parse_qs(
            parsed.query
        )

        shop_id = (
            params.get("shopid", [None])[0]
            or params.get("shop_id", [None])[0]
        )

        item_id = (
            params.get("itemid", [None])[0]
            or params.get("item_id", [None])[0]
        )

        if shop_id and item_id:

            return {
                "shop_id": shop_id,
                "item_id": item_id,
            }

    except Exception:
        pass

    return None


# ============================================================
# GRAPHQL SHOPEE
# ============================================================

def assinar_requisicao_shopee(payload_string):
    """
    Gera a assinatura SHA256 da Shopee.

    Signature =
        SHA256(
            AppId +
            Timestamp +
            Payload +
            Secret
        )

    O Payload precisa ser exatamente o JSON enviado.
    """

    timestamp = str(
        int(time.time())
    )

    factor = (
        SHOPEE_APP_ID
        + timestamp
        + payload_string
        + SHOPEE_APP_SECRET
    )

    signature = hashlib.sha256(
        factor.encode("utf-8")
    ).hexdigest()

    authorization = (
        "SHA256 "
        f"Credential={SHOPEE_APP_ID},"
        f"Timestamp={timestamp},"
        f"Signature={signature}"
    )

    return timestamp, authorization


def executar_graphql(query, variables=None):
    """
    Executa uma requisição GraphQL autenticada na Shopee.
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

    if variables is None:
        variables = {}

    payload = {
        "query": query,
        "variables": variables,
    }

    # IMPORTANTE:
    # O mesmo JSON usado na assinatura deve ser enviado.
    payload_string = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    timestamp, authorization = (
        assinar_requisicao_shopee(
            payload_string
        )
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": authorization,
    }

    logger.info(
        "🛒 Consultando API GraphQL da Shopee"
    )

    response = requests.post(
        SHOPEE_API_URL,
        data=payload_string.encode("utf-8"),
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )

    logger.info(
        "📡 Shopee respondeu HTTP %s",
        response.status_code,
    )

    if response.status_code >= 400:

        logger.error(
            "Resposta HTTP da Shopee: %s",
            response.text[:2000],
        )

        raise RuntimeError(
            f"Shopee respondeu HTTP "
            f"{response.status_code}."
        )

    try:

        data = response.json()

    except Exception:

        logger.error(
            "Resposta Shopee não é JSON: %s",
            response.text[:2000],
        )

        raise RuntimeError(
            "Shopee não retornou JSON válido."
        )

    # GraphQL pode retornar HTTP 200 com errors.
    if data.get("errors"):

        logger.error(
            "❌ Erro GraphQL Shopee: %s",
            data["errors"],
        )

        errors = data.get(
            "errors",
            [],
        )

        mensagens = []

        for error in errors:

            if isinstance(error, dict):

                mensagem = error.get(
                    "message"
                )

                if mensagem:
                    mensagens.append(
                        str(mensagem)
                    )

        if mensagens:

            raise RuntimeError(
                "Shopee GraphQL: "
                + " | ".join(mensagens)
            )

        raise RuntimeError(
            "Shopee retornou erro GraphQL."
        )

    return data


# ============================================================
# CONSULTA DE PRODUTO
# ============================================================

def consultar_produto_shopee(
    shop_id,
    item_id,
):
    """
    Busca um produto específico através do
    productOfferV2.
    """

    query = """
query ProductOffer(
    $shopId: Int64,
    $itemId: Int64,
    $page: Int,
    $limit: Int
) {
    productOfferV2(
        shopId: $shopId,
        itemId: $itemId,
        page: $page,
        limit: $limit
    ) {
        nodes {
            itemId
            commissionRate
            sellerCommissionRate
            shopeeCommissionRate
            commission
            sales
            priceMax
            priceMin
            productCatIds
            ratingStar
            priceDiscountRate
            imageUrl
            productName
            shopId
            shopName
            shopType
            productLink
            offerLink
            periodStartTime
            periodEndTime
        }

        pageInfo {
            page
            limit
            hasNextPage
        }
    }
}
"""

    variables = {
        "shopId": int(shop_id),
        "itemId": int(item_id),
        "page": 1,
        "limit": 10,
    }

    return executar_graphql(
        query=query,
        variables=variables,
    )


# ============================================================
# BUSCA ALTERNATIVA POR ITEM ID
# ============================================================

def consultar_produto_por_item(
    item_id,
):
    """
    Fallback.

    Caso a combinação shopId/itemId não retorne,
    tenta localizar pelo itemId.
    """

    query = """
query ProductOffer(
    $itemId: Int64,
    $page: Int,
    $limit: Int
) {
    productOfferV2(
        itemId: $itemId,
        page: $page,
        limit: $limit
    ) {
        nodes {
            itemId
            commissionRate
            sellerCommissionRate
            shopeeCommissionRate
            commission
            sales
            priceMax
            priceMin
            productCatIds
            ratingStar
            priceDiscountRate
            imageUrl
            productName
            shopId
            shopName
            shopType
            productLink
            offerLink
            periodStartTime
            periodEndTime
        }

        pageInfo {
            page
            limit
            hasNextPage
        }
    }
}
"""

    variables = {
        "itemId": int(item_id),
        "page": 1,
        "limit": 10,
    }

    return executar_graphql(
        query=query,
        variables=variables,
    )


# ============================================================
# EXTRAÇÃO DO PRODUTO DA RESPOSTA
# ============================================================

def extrair_nodes_produto(data):
    """
    Extrai nodes de productOfferV2.
    """

    try:

        return (
            data
            .get("data", {})
            .get("productOfferV2", {})
            .get("nodes", [])
        )

    except Exception:

        return []


def encontrar_produto(
    data,
    shop_id=None,
    item_id=None,
):
    """
    Encontra exatamente o produto solicitado.
    """

    nodes = extrair_nodes_produto(
        data
    )

    if not nodes:

        raise RuntimeError(
            "Nenhum produto foi encontrado "
            "na resposta da Shopee."
        )

    # --------------------------------------------------------
    # Primeiro: item + shop
    # --------------------------------------------------------

    if item_id:

        for produto in nodes:

            produto_item = str(
                produto.get("itemId", "")
            )

            if produto_item != str(item_id):
                continue

            if shop_id:

                produto_shop = str(
                    produto.get("shopId", "")
                )

                if produto_shop == str(shop_id):

                    return produto

            else:

                return produto

    # --------------------------------------------------------
    # Segundo: somente item
    # --------------------------------------------------------

    if item_id:

        for produto in nodes:

            if str(
                produto.get("itemId", "")
            ) == str(item_id):

                return produto

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    return nodes[0]


# ============================================================
# CONSULTA PRINCIPAL DA SHOPEE
# ============================================================

def consultar_shopee(
    shop_id=None,
    item_id=None,
    url=None,
):
    """
    Fluxo completo:

    1. Resolve link curto.
    2. Extrai shop_id/item_id.
    3. Consulta productOfferV2.
    4. Retorna produto.
    """

    # --------------------------------------------------------
    # Resolve o link antes da consulta.
    # --------------------------------------------------------

    url_original = url

    if url:

        url = resolver_url_shopee(
            url
        )

    # --------------------------------------------------------
    # Se os IDs não vieram, tenta extrair
    # novamente da URL resolvida.
    # --------------------------------------------------------

    if not shop_id or not item_id:

        ids = extrair_ids_produto(
            url
        )

        if ids:

            shop_id = ids.get(
                "shop_id"
            )

            item_id = ids.get(
                "item_id"
            )

    logger.info(
        "🔎 shop_id=%s item_id=%s",
        shop_id,
        item_id,
    )

    if not item_id:

        raise RuntimeError(
            "Não foi possível identificar o "
            "item_id do produto Shopee. "
            "O link curto pode não ter sido resolvido."
        )

    # --------------------------------------------------------
    # Consulta pelo produto.
    # --------------------------------------------------------

    try:

        resposta = consultar_produto_shopee(
            shop_id=shop_id,
            item_id=item_id,
        )

        nodes = extrair_nodes_produto(
            resposta
        )

        if nodes:

            produto = encontrar_produto(
                resposta,
                shop_id=shop_id,
                item_id=item_id,
            )

            return produto, url

    except RuntimeError as exc:

        logger.warning(
            "⚠️ Consulta shopId/itemId falhou: %s",
            exc,
        )

    # --------------------------------------------------------
    # Fallback: somente itemId.
    # --------------------------------------------------------

    logger.info(
        "🔄 Tentando busca alternativa por itemId=%s",
        item_id,
    )

    resposta = consultar_produto_por_item(
        item_id=item_id
    )

    produto = encontrar_produto(
        resposta,
        item_id=item_id,
    )

    return produto, url


# ============================================================
# NORMALIZAÇÃO DO PRODUTO
# ============================================================

def normalizar_produto(produto):
    """
    Converte a resposta Shopee para o formato
    usado pelo Mini App/Telegram.
    """

    nome = produto.get(
        "productName",
        "Produto Shopee",
    )

    preco = produto.get(
        "price"
    )

    preco_min = produto.get(
        "priceMin",
        preco,
    )

    preco_max = produto.get(
        "priceMax",
        preco,
    )

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
        "item_id": produto.get(
            "itemId"
        ),
        "shop_id": produto.get(
            "shopId"
        ),
        "preco": preco,
        "preco_min": preco_min,
        "preco_max": preco_max,
        "preco_formatado": money(
            preco
        ),
        "preco_min_formatado": money(
            preco_min
        ),
        "preco_max_formatado": money(
            preco_max
        ),
        "desconto": desconto,
        "desconto_formatado": percentual(
            desconto
        ),
        "comissao": comissao,
        "comissao_formatada": money(
            comissao
        ),
        "comissao_percentual": percentual(
            produto.get(
                "commissionRate"
            )
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

def escapar_html(texto):
    """
    Escapa caracteres HTML básicos.
    """

    if texto is None:
        return ""

    texto = str(texto)

    return (
        texto
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def montar_mensagem(produto):
    """
    Cria mensagem para Telegram.
    """

    nome = escapar_html(
        produto.get(
            "nome",
            "Produto Shopee",
        )
    )

    if len(nome) > 180:

        nome = (
            nome[:177]
            + "..."
        )

    mensagem = (
        "🔥 <b>OFERTA SHOPEE</b>\n\n"
        f"🛍️ <b>{nome}</b>\n\n"
        f"💰 <b>Preço:</b> "
        f"{produto.get('preco_formatado', 'Indisponível')}\n"
    )

    desconto = produto.get(
        "desconto"
    )

    if desconto not in (
        None,
        "",
        0,
        "0",
    ):

        mensagem += (
            "🏷️ <b>Desconto:</b> "
            f"{produto.get('desconto_formatado', 'N/A')}\n"
        )

    avaliacao = produto.get(
        "avaliacao"
    )

    if avaliacao not in (
        None,
        "",
        0,
        "0",
    ):

        mensagem += (
            "⭐ <b>Avaliação:</b> "
            f"{escapar_html(avaliacao)}\n"
        )

    vendas = produto.get(
        "vendas"
    )

    if vendas not in (
        None,
        "",
        0,
        "0",
    ):

        mensagem += (
            "📦 <b>Vendas:</b> "
            f"{escapar_html(vendas)}\n"
        )

    loja = escapar_html(
        produto.get(
            "loja",
            "Loja Shopee",
        )
    )

    mensagem += (
        f"🏪 <b>Loja:</b> {loja}\n\n"
        "💸 <b>Comissão:</b> "
        f"{produto.get('comissao_formatada', 'N/A')}\n\n"
    )

    link = produto.get(
        "link_oferta"
    )

    if link:

        mensagem += (
            f'🛒 <a href="{link}">'
            "COMPRAR AGORA</a>"
        )

    return mensagem


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(produto):
    """
    Envia produto ao Telegram.
    """

    if not TELEGRAM_BOT_TOKEN:

        raise RuntimeError(
            "TELEGRAM_TOKEN não configurado."
        )

    if not TELEGRAM_CHAT_ID:

        raise RuntimeError(
            "CHAT_ID não configurado."
        )

    mensagem = montar_mensagem(
        produto
    )

    base_url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}"
    )

    imagem = produto.get(
        "imagem"
    )

    # --------------------------------------------------------
    # FOTO
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
                "⚠️ Telegram recusou foto: %s",
                response.text[:500],
            )

        except Exception as exc:

            logger.warning(
                "⚠️ Erro ao enviar foto: %s",
                exc,
            )

    # --------------------------------------------------------
    # TEXTO
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
        "✅ Produto enviado ao Telegram."
    )

    return response.json()


# ============================================================
# TELEGRAM MINI APP
# ============================================================

def validar_miniapp():
    """
    Validação simples.

    Por padrão:
        TELEGRAM_INIT_DATA_REQUIRED=false

    Nesse modo o endpoint funciona sem exigir
    o header X-Telegram-Init-Data.

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

    # Não registramos initData nos logs.
    return True


# ============================================================
# ROTAS
# ============================================================

@app.route(
    "/",
    methods=["GET", "HEAD"],
)
def index():

    return jsonify({
        "ok": True,
        "service": "Raposa Caçadora",
        "integracao": "Shopee Affiliate Open API",
        "status": "online",
    })


@app.route(
    "/health",
    methods=["GET"],
)
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

    return "", 204


@app.route(
    "/api/configurar",
    methods=["POST"],
)
def configurar():

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

    # NÃO registra initData.
    safe_data = dict(data)

    if "initData" in safe_data:

        safe_data["initData"] = (
            "[OCULTO]"
        )

    logger.info(
        "JSON recebido: %s",
        safe_data,
    )

    link = str(
        data.get(
            "link",
            "",
        )
    ).strip()

    if not link:

        return jsonify({
            "ok": False,
            "error": "Informe o link da Shopee.",
        }), 400

    if not validar_url_shopee(
        link
    ):

        return jsonify({
            "ok": False,
            "error": (
                "O link informado não "
                "parece ser da Shopee."
            ),
        }), 400

    # --------------------------------------------------------
    # QUANTIDADE
    # --------------------------------------------------------

    try:

        quantidade = int(
            data.get(
                "quantidade",
                1,
            )
        )

    except Exception:

        quantidade = 1

    quantidade = max(
        1,
        min(
            quantidade,
            20,
        ),
    )

    # --------------------------------------------------------
    # INTERVALO
    # --------------------------------------------------------

    try:

        intervalo = float(
            data.get(
                "intervalo",
                1,
            )
        )

    except Exception:

        intervalo = 1

    intervalo = max(
        0,
        min(
            intervalo,
            3600,
        ),
    )

    # --------------------------------------------------------
    # ENVIO
    # --------------------------------------------------------

    enviar = bool(
        data.get(
            "enviar",
            False,
        )
    )

    try:

        # ----------------------------------------------------
        # RESOLVE E EXTRAI IDS
        # ----------------------------------------------------

        url_resolvida = (
            resolver_url_shopee(
                link
            )
        )

        ids = extrair_ids_produto(
            url_resolvida
        )

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

        produto_bruto, url_final = (
            consultar_shopee(
                shop_id=shop_id,
                item_id=item_id,
                url=url_resolvida,
            )
        )

        produto = normalizar_produto(
            produto_bruto
        )

        # Se a API retornou link de produto,
        # usamos esse link quando disponível.
        if not produto.get(
            "link_produto"
        ):

            produto[
                "link_produto"
            ] = url_final

        if not produto.get(
            "link_oferta"
        ):

            produto[
                "link_oferta"
            ] = url_final

        logger.info(
            "✅ Produto encontrado: %s",
            produto.get("nome"),
        )

        # ----------------------------------------------------
        # ENVIO TELEGRAM
        # ----------------------------------------------------

        resultados_envio = []

        if enviar:

            for i in range(
                quantidade
            ):

                resultado = (
                    enviar_telegram(
                        produto
                    )
                )

                resultados_envio.append({
                    "numero": i + 1,
                    "ok": True,
                })

                if i < quantidade - 1:

                    time.sleep(
                        intervalo
                    )

        return jsonify({
            "ok": True,
            "message": (
                "Produto encontrado com sucesso."
                if not enviar
                else "Produto processado e enviado."
            ),
            "produto": produto,
            "url_original": link,
            "url_resolvida": url_final,
            "shop_id": shop_id,
            "item_id": item_id,
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
# TESTE TELEGRAM
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
            "message": (
                "Teste enviado ao Telegram."
            ),
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
# ERROS
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
        "error": (
            "Método HTTP não permitido "
            "para esta rota."
        ),
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
