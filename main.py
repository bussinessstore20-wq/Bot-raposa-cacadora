import os
import json
import time
import hmac
import hashlib
import logging
import threading
from datetime import datetime, timezone
from urllib.parse import parse_qsl

import requests
from flask import Flask, request, jsonify

# ============================================================
# CONFIGURAÇÃO
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "@raposacacadora").strip()

WEBAPP_URL = os.getenv(
    "WEBAPP_URL",
    "https://bot-raposa-cacadora.vercel.app"
).strip().rstrip("/")

TELEGRAM_API = (
    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
)

HISTORICO_FILE = "produtos_postados.txt"

# Tempo máximo permitido para initData do Telegram.
# 86400 = 24 horas.
INIT_DATA_MAX_AGE = 86400

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("raposa-cacadora")

# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


# ============================================================
# CORS
# ============================================================

@app.after_request
def add_cors_headers(response):
    """
    Adiciona os headers CORS somente para o domínio
    autorizado do Mini App.
    """

    origin = request.headers.get("Origin")

    if origin == WEBAPP_URL:
        response.headers["Access-Control-Allow-Origin"] = WEBAPP_URL

        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Telegram-Init-Data"
        )

        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, OPTIONS"
        )

        response.headers["Access-Control-Max-Age"] = "600"

        response.headers["Vary"] = "Origin"

    return response


# ============================================================
# TELEGRAM INIT DATA
# ============================================================

def validar_init_data(init_data: str):
    """
    Valida Telegram WebApp initData usando o token do bot.

    Retorna:
        (True, dados)
    ou
        (False, motivo)
    """

    if not init_data:
        return False, "initData ausente"

    if not TELEGRAM_TOKEN:
        logger.error(
            "❌ TELEGRAM_TOKEN não configurado."
        )
        return False, "TELEGRAM_TOKEN não configurado"

    try:
        dados = dict(parse_qsl(
            init_data,
            keep_blank_values=True
        ))

        recebido_hash = dados.pop("hash", None)

        if not recebido_hash:
            return False, "hash ausente no initData"

        # Telegram exige que os pares sejam ordenados.
        data_check_string = "\n".join(
            f"{chave}={valor}"
            for chave, valor in sorted(dados.items())
        )

        # secret_key = HMAC-SHA256("WebAppData", bot_token)
        secret_key = hmac.new(
            b"WebAppData",
            TELEGRAM_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        calculado_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            calculado_hash,
            recebido_hash
        ):
            return False, "hash inválido"

        # Verificação de idade do auth_date.
        auth_date = dados.get("auth_date")

        if auth_date:
            try:
                auth_timestamp = int(auth_date)

                agora = int(time.time())

                idade = agora - auth_timestamp

                if idade < 0:
                    return False, "auth_date inválido"

                if idade > INIT_DATA_MAX_AGE:
                    return False, "initData expirado"

            except ValueError:
                return False, "auth_date inválido"

        return True, dados

    except Exception as e:
        logger.exception(
            "❌ Erro validando Telegram initData"
        )
        return False, str(e)


# ============================================================
# HISTÓRICO
# ============================================================

historico_lock = threading.Lock()


def carregar_historico():
    """
    Carrega IDs/URLs já publicados.
    """

    if not os.path.exists(HISTORICO_FILE):
        return set()

    try:
        with open(
            HISTORICO_FILE,
            "r",
            encoding="utf-8"
        ) as arquivo:

            return {
                linha.strip()
                for linha in arquivo
                if linha.strip()
            }

    except Exception:
        logger.exception(
            "❌ Erro lendo histórico."
        )
        return set()


def produto_ja_postado(chave):
    """
    Verifica se um produto já foi publicado.
    """

    with historico_lock:
        historico = carregar_historico()

        return chave in historico


def registrar_produto(chave):
    """
    Registra produto depois que o envio foi realizado.
    """

    with historico_lock:
        try:
            with open(
                HISTORICO_FILE,
                "a",
                encoding="utf-8"
            ) as arquivo:

                arquivo.write(
                    chave + "\n"
                )

        except Exception:
            logger.exception(
                "❌ Erro salvando histórico."
            )


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_request(method, payload=None, timeout=30):
    """
    Comunicação genérica com Telegram Bot API.
    """

    if not TELEGRAM_TOKEN:
        raise RuntimeError(
            "TELEGRAM_TOKEN não configurado."
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/{method}"
    )

    try:
        response = requests.post(
            url,
            json=payload or {},
            timeout=timeout
        )

    except requests.RequestException as e:
        logger.error(
            "❌ Falha de conexão com Telegram: %s",
            e
        )
        raise

    if response.status_code == 429:
        try:
            data = response.json()
        except Exception:
            data = {}

        retry_after = (
            data.get("parameters", {})
            .get("retry_after", 10)
        )

        logger.warning(
            "⚠️ Telegram rate limit. "
            "Aguardando %s segundos.",
            retry_after
        )

        time.sleep(int(retry_after))

        response = requests.post(
            url,
            json=payload or {},
            timeout=timeout
        )

    if not response.ok:
        logger.error(
            "❌ Telegram HTTP %s: %s",
            response.status_code,
            response.text[:1000]
        )

        response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(
            f"Telegram API retornou erro: {data}"
        )

    return data


# ============================================================
# ENVIO DE FOTO
# ============================================================

def enviar_produto_telegram(produto):
    """
    Envia uma oferta para o canal.

    Espera um dicionário:

    {
        "id": "...",
        "titulo": "...",
        "imagem": "...",
        "preco_atual": "...",
        "preco_anterior": "...",
        "cupom": "...",
        "url": "..."
    }
    """

    titulo = (
        produto.get("titulo")
        or "Produto"
    )

    imagem = produto.get("imagem")

    preco_atual = (
        produto.get("preco_atual")
        or ""
    )

    preco_anterior = (
        produto.get("preco_anterior")
        or ""
    )

    cupom = (
        produto.get("cupom")
        or ""
    )

    url = (
        produto.get("url")
        or ""
    )

    if not url:
        raise ValueError(
            "Produto sem URL."
        )

    # --------------------------------------------------------
    # MENSAGEM
    # --------------------------------------------------------

    linhas = [
        "🚨 OFERTA RELÂMPAGO DO DIA 🚨",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📦 {titulo}",
        ""
    ]

    if preco_anterior:
        linhas.extend([
            f"❌ De: {preco_anterior}",
        ])

    if preco_atual:
        linhas.extend([
            f"🔥 POR APENAS: {preco_atual}",
        ])

    if cupom:
        linhas.extend([
            "",
            f"🎟️ CUPOM EXTRA: {cupom}",
        ])

    linhas.extend([
        "",
        "🚚 Frete Rápido & Compra 100% Segura",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "👇 GARANTA O SEU ANTES QUE ACABE:",
        "",
        "📌 Canal Oficial @raposacacadora"
    ])

    texto = "\n".join(linhas)

    # --------------------------------------------------------
    # BOTÃO
    # --------------------------------------------------------

    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "🛒 COMPRAR AGORA",
                    "url": url
                }
            ]
        ]
    }

    # --------------------------------------------------------
    # FOTO
    # --------------------------------------------------------

    if imagem:

        payload = {
            "chat_id": CHAT_ID,
            "photo": imagem,
            "caption": texto,
            "reply_markup": json.dumps(
                reply_markup,
                ensure_ascii=False
            )
        }

        try:
            resultado = telegram_request(
                "sendPhoto",
                payload
            )

            logger.info(
                "📸 Produto enviado com imagem: %s",
                titulo
            )

            return resultado

        except Exception:
            logger.exception(
                "⚠️ Falha enviando imagem. "
                "Tentando enviar somente texto."
            )

    # --------------------------------------------------------
    # TEXTO
    # --------------------------------------------------------

    payload = {
        "chat_id": CHAT_ID,
        "text": texto,
        "reply_markup": json.dumps(
            reply_markup,
            ensure_ascii=False
        ),
        "disable_web_page_preview": False
    }

    resultado = telegram_request(
        "sendMessage",
        payload
    )

    logger.info(
        "📝 Produto enviado somente texto: %s",
        titulo
    )

    return resultado


# ============================================================
# MERCADO LIVRE
# ============================================================

def obter_produtos_mercado_livre(link_vitrine, quantidade):
    """
    PONTO DE INTEGRAÇÃO DO MERCADO LIVRE.

    IMPORTANTE:

    Esta função NÃO tenta contornar o bloqueio 403 do meli.la.

    O link meli.la é um link de redirecionamento/afiliado.
    O HTML da página não deve ser tratado como API oficial.

    A integração oficial deverá ser implementada aqui após
    determinar, pela documentação do Mercado Livre, qual
    recurso autorizado fornece os produtos relacionados à
    conta/afiliado.

    Por enquanto retornamos lista vazia em vez de tentar
    fazer scraping/bypass do Mercado Livre.
    """

    logger.info(
        "🦊 RAPOSA CAÇADORA"
    )

    logger.info(
        "🔗 Vitrine: %s",
        link_vitrine
    )

    logger.warning(
        "⚠️ Integração oficial de produtos do Mercado Livre "
        "ainda não configurada."
    )

    logger.warning(
        "⚠️ Não será realizado scraping ou tentativa de "
        "contornar HTTP 403 do meli.la."
    )

    return []


# ============================================================
# PROCESSAMENTO EM SEGUNDO PLANO
# ============================================================

def executar_automacao(
    link,
    quantidade,
    intervalo
):
    """
    Executa a automação em background.
    """

    logger.info(
        "🚀 INICIANDO AUTOMAÇÃO EM SEGUNDO PLANO"
    )

    logger.info(
        "🔗 Link: %s",
        link
    )

    logger.info(
        "📦 Quantidade solicitada: %s",
        quantidade
    )

    logger.info(
        "⏱️ Intervalo: %s minuto(s)",
        intervalo
    )

    try:

        produtos = obter_produtos_mercado_livre(
            link,
            quantidade
        )

        logger.info(
            "📊 Produtos encontrados: %s",
            len(produtos)
        )

        if not produtos:
            logger.warning(
                "❌ NENHUM PRODUTO FOI ENCONTRADO."
            )

            return

        enviados = 0

        for produto in produtos:

            if enviados >= quantidade:
                break

            # ------------------------------------------------
            # IDENTIFICADOR
            # ------------------------------------------------

            produto_id = (
                str(produto.get("id"))
                if produto.get("id")
                else produto.get("url")
            )

            if not produto_id:
                logger.warning(
                    "⚠️ Produto ignorado: sem ID/URL."
                )
                continue

            # ------------------------------------------------
            # DUPLICIDADE
            # ------------------------------------------------

            if produto_ja_postado(
                produto_id
            ):
                logger.info(
                    "♻️ Produto já publicado: %s",
                    produto_id
                )
                continue

            # ------------------------------------------------
            # ENVIO
            # ------------------------------------------------

            try:

                enviar_produto_telegram(
                    produto
                )

                registrar_produto(
                    produto_id
                )

                enviados += 1

                logger.info(
                    "✅ Oferta %s/%s publicada.",
                    enviados,
                    quantidade
                )

            except Exception:

                logger.exception(
                    "❌ Erro publicando produto: %s",
                    produto_id
                )

            # ------------------------------------------------
            # INTERVALO
            # ------------------------------------------------

            if (
                enviados < quantidade
                and intervalo > 0
            ):

                segundos = intervalo * 60

                logger.info(
                    "⏳ Aguardando %s segundos...",
                    segundos
                )

                time.sleep(segundos)

        logger.info(
            "🏁 AUTOMAÇÃO FINALIZADA. "
            "Produtos enviados: %s",
            enviados
        )

    except Exception:

        logger.exception(
            "💥 ERRO FATAL NA AUTOMAÇÃO."
        )


# ============================================================
# HOME
# ============================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "ok": True,
        "service": "Bot Raposa Caçadora",
        "status": "online",
        "time": datetime.now(
            timezone.utc
        ).isoformat()
    })


# ============================================================
# HEALTH
# ============================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "ok": True,
        "status": "online",
        "service": "bot-raposa-cacadora",
        "telegram_configurado": bool(
            TELEGRAM_TOKEN
        ),
        "chat_id": CHAT_ID,
        "webapp_url": WEBAPP_URL
    })


# ============================================================
# OPTIONS /api/configurar
# ============================================================

@app.route(
    "/api/configurar",
    methods=["OPTIONS"]
)
def configurar_options():

    logger.info(
        "🌐 OPTIONS /api/configurar"
    )

    return "", 204


# ============================================================
# POST /api/configurar
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    logger.info(
        "📥 NOVA CONFIGURAÇÃO"
    )

    # --------------------------------------------------------
    # INIT DATA
    # --------------------------------------------------------

    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        ""
    )

    # Também aceita o header padrão usado por algumas
    # implementações.
    if not init_data:
        init_data = request.headers.get(
            "Telegram-Init-Data",
            ""
        )

    logger.info(
        "🔐 Telegram initData recebido: %s",
        bool(init_data)
    )

    valido, resultado = validar_init_data(
        init_data
    )

    if not valido:

        logger.warning(
            "❌ Telegram initData inválido: %s",
            resultado
        )

        return jsonify({
            "ok": False,
            "error": "Telegram initData inválido",
            "details": resultado
        }), 401

    logger.info(
        "✅ Telegram initData válido."
    )

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    dados = request.get_json(
        silent=True
    )

    if not dados:

        logger.warning(
            "❌ JSON não recebido."
        )

        return jsonify({
            "ok": False,
            "error": "JSON não recebido."
        }), 400

    logger.info(
        "📦 JSON recebido: %s",
        dados
    )

    # --------------------------------------------------------
    # LINK
    # --------------------------------------------------------

    link = str(
        dados.get("link", "")
    ).strip()

    if not link:

        return jsonify({
            "ok": False,
            "error": "Link da vitrine não informado."
        }), 400

    # --------------------------------------------------------
    # QUANTIDADE
    # --------------------------------------------------------

    try:

        quantidade = int(
            dados.get(
                "quantidade",
                1
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return jsonify({
            "ok": False,
            "error": "Quantidade inválida."
        }), 400

    if quantidade < 1:
        quantidade = 1

    if quantidade > 100:
        quantidade = 100

    # --------------------------------------------------------
    # INTERVALO
    # --------------------------------------------------------

    try:

        intervalo = float(
            dados.get(
                "intervalo",
                1
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return jsonify({
            "ok": False,
            "error": "Intervalo inválido."
        }), 400

    if intervalo < 0:
        intervalo = 0

    if intervalo > 1440:
        intervalo = 1440

    logger.info(
        "🔗 Link: %s",
        link
    )

    logger.info(
        "📦 Quantidade: %s",
        quantidade
    )

    logger.info(
        "⏱️ Intervalo: %s minuto(s)",
        intervalo
    )

    # --------------------------------------------------------
    # BACKGROUND THREAD
    # --------------------------------------------------------

    worker = threading.Thread(
        target=executar_automacao,
        args=(
            link,
            quantidade,
            intervalo
        ),
        daemon=True
    )

    worker.start()

    logger.info(
        "🚀 Worker iniciado."
    )

    # --------------------------------------------------------
    # RESPONDE IMEDIATAMENTE AO MINI APP
    # --------------------------------------------------------

    return jsonify({
        "ok": True,
        "message": (
            "Configuração recebida. "
            "A automação foi iniciada em segundo plano."
        ),
        "link": link,
        "quantidade": quantidade,
        "intervalo": intervalo
    }), 200


# ============================================================
# ERROS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "ok": False,
        "error": "Rota não encontrada."
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):

    return jsonify({
        "ok": False,
        "error": "Método HTTP não permitido para esta rota."
    }), 405


@app.errorhandler(500)
def internal_error(error):

    logger.exception(
        "💥 Erro interno do servidor."
    )

    return jsonify({
        "ok": False,
        "error": "Erro interno do servidor."
    }), 500


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    logger.info(
        "🦊 Bot Raposa Caçadora iniciando..."
    )

    logger.info(
        "🌐 WEBAPP_URL: %s",
        WEBAPP_URL
    )

    logger.info(
        "📢 CHAT_ID: %s",
        CHAT_ID
    )

    logger.info(
        "🔐 Telegram configurado: %s",
        bool(TELEGRAM_TOKEN)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
