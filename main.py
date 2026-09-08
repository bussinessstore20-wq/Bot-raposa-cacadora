import os
import json
import time
import hmac
import hashlib
import logging
import threading
from urllib.parse import parse_qsl, urlencode

import requests
from flask import Flask, request, jsonify, redirect


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "@raposacacadora").strip()

WEBAPP_URL = os.getenv(
    "WEBAPP_URL",
    "https://bot-raposa-cacadora.vercel.app"
).strip().rstrip("/")

ML_CLIENT_ID = os.getenv("ML_CLIENT_ID", "").strip()
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET", "").strip()

ML_REDIRECT_URI = os.getenv(
    "ML_REDIRECT_URI",
    "https://bot-raposa-cacadora.onrender.com/oauth/callback"
).strip()

ML_ACCESS_TOKEN = os.getenv(
    "ML_ACCESS_TOKEN",
    ""
).strip()

ML_REFRESH_TOKEN = os.getenv(
    "ML_REFRESH_TOKEN",
    ""
).strip()


TELEGRAM_API = (
    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
)

HISTORICO_FILE = "produtos_postados.txt"

INIT_DATA_MAX_AGE = 86400


# ============================================================
# LOG
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

    origin = request.headers.get("Origin")

    # Durante o funcionamento normal aceitamos o Vercel.
    if origin == WEBAPP_URL:

        response.headers[
            "Access-Control-Allow-Origin"
        ] = WEBAPP_URL

        response.headers[
            "Access-Control-Allow-Headers"
        ] = (
            "Content-Type, "
            "X-Telegram-Init-Data"
        )

        response.headers[
            "Access-Control-Allow-Methods"
        ] = (
            "GET, POST, OPTIONS"
        )

        response.headers[
            "Access-Control-Max-Age"
        ] = "600"

        response.headers[
            "Vary"
        ] = "Origin"

    return response


# ============================================================
# TELEGRAM INIT DATA
# ============================================================

def validar_init_data(init_data):

    if not init_data:

        return False, "initData ausente"

    if not TELEGRAM_TOKEN:

        logger.error(
            "❌ TELEGRAM_TOKEN não configurado."
        )

        return False, "TELEGRAM_TOKEN não configurado"

    try:

        dados = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        recebido_hash = dados.pop(
            "hash",
            None
        )

        if not recebido_hash:

            return False, "hash ausente"

        data_check_string = "\n".join(
            f"{chave}={valor}"
            for chave, valor
            in sorted(dados.items())
        )

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

        auth_date = dados.get(
            "auth_date"
        )

        if auth_date:

            try:

                idade = (
                    int(time.time())
                    - int(auth_date)
                )

                if idade < 0:

                    return False, "auth_date inválido"

                if idade > INIT_DATA_MAX_AGE:

                    return False, "initData expirado"

            except ValueError:

                return False, "auth_date inválido"

        return True, dados

    except Exception as e:

        logger.exception(
            "❌ Erro validando initData."
        )

        return False, str(e)


# ============================================================
# MERCADO LIVRE — AUTENTICAÇÃO
# ============================================================

def mercado_livre_configurado():

    return bool(
        ML_CLIENT_ID
        and ML_CLIENT_SECRET
        and ML_REDIRECT_URI
    )


def gerar_url_oauth():

    parametros = {
        "response_type": "code",
        "client_id": ML_CLIENT_ID,
        "redirect_uri": ML_REDIRECT_URI
    }

    return (
        "https://auth.mercadolivre.com.br/"
        "authorization?"
        + urlencode(parametros)
    )


@app.route(
    "/oauth/mercadolivre",
    methods=["GET"]
)
def oauth_mercadolivre():

    logger.info(
        "🔐 Iniciando autorização Mercado Livre."
    )

    if not mercado_livre_configurado():

        return jsonify({
            "ok": False,
            "error": (
                "ML_CLIENT_ID, ML_CLIENT_SECRET "
                "ou ML_REDIRECT_URI não configurados."
            )
        }), 500

    url = gerar_url_oauth()

    logger.info(
        "➡️ Redirecionando para Mercado Livre."
    )

    return redirect(url)


# ============================================================
# TROCAR CODE POR TOKEN
# ============================================================

def trocar_code_por_token(code):

    logger.info(
        "🔑 Trocando authorization code por token."
    )

    payload = {
        "grant_type": "authorization_code",
        "client_id": ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
        "code": code,
        "redirect_uri": ML_REDIRECT_URI
    }

    response = requests.post(
        "https://api.mercadolibre.com/oauth/token",
        data=payload,
        headers={
            "Accept": "application/json"
        },
        timeout=30
    )

    logger.info(
        "Mercado Livre OAuth HTTP: %s",
        response.status_code
    )

    if not response.ok:

        logger.error(
            "❌ Erro OAuth: %s",
            response.text[:2000]
        )

        response.raise_for_status()

    return response.json()


# ============================================================
# CALLBACK
# ============================================================

@app.route(
    "/oauth/callback",
    methods=["GET"]
)
def oauth_callback():

    erro = request.args.get(
        "error"
    )

    if erro:

        descricao = request.args.get(
            "error_description",
            ""
        )

        logger.error(
            "❌ Mercado Livre recusou autorização: %s %s",
            erro,
            descricao
        )

        return jsonify({
            "ok": False,
            "error": erro,
            "description": descricao
        }), 400

    code = request.args.get(
        "code"
    )

    if not code:

        return jsonify({
            "ok": False,
            "error": "Código OAuth não recebido."
        }), 400

    logger.info(
        "✅ Authorization code recebido."
    )

    try:

        token_data = trocar_code_por_token(
            code
        )

        access_token = token_data.get(
            "access_token"
        )

        refresh_token = token_data.get(
            "refresh_token"
        )

        expires_in = token_data.get(
            "expires_in"
        )

        user_id = token_data.get(
            "user_id"
        )

        scope = token_data.get(
            "scope"
        )

        if not access_token:

            logger.error(
                "❌ Mercado Livre não retornou access_token."
            )

            return jsonify({
                "ok": False,
                "error": "access_token não recebido",
                "response": token_data
            }), 500

        logger.info(
            "✅ Access token obtido."
        )

        logger.info(
            "👤 Mercado Livre user_id: %s",
            user_id
        )

        logger.info(
            "⏱️ expires_in: %s",
            expires_in
        )

        logger.info(
            "🔐 scope: %s",
            scope
        )

        # ----------------------------------------------------
        # IMPORTANTE
        # ----------------------------------------------------
        #
        # NÃO imprimimos os tokens nos logs.
        #
        # Para o primeiro teste eles precisam ser configurados
        # nas Environment Variables do Render.
        #
        # O Render não fornece automaticamente uma forma segura
        # para este código alterar Environment Variables.
        #
        # Portanto mostramos instruções sem revelar os valores.
        # ----------------------------------------------------

        mensagem = """
Autorização Mercado Livre concluída.

O Mercado Livre forneceu access_token e refresh_token.

Agora configure esses valores nas Environment Variables
do Render:

ML_ACCESS_TOKEN
ML_REFRESH_TOKEN

NÃO publique esses valores no GitHub.
"""

        return (
            "<html>"
            "<head><meta charset='utf-8'></head>"
            "<body>"
            "<h2>✅ Mercado Livre autorizado!</h2>"
            "<p>O código foi trocado por tokens com sucesso.</p>"
            "<p>Agora configure <b>ML_ACCESS_TOKEN</b> e "
            "<b>ML_REFRESH_TOKEN</b> nas Environment Variables "
            "do Render.</p>"
            "<p>Depois podemos testar a API.</p>"
            "</body>"
            "</html>"
        )

    except requests.HTTPError as e:

        logger.exception(
            "❌ HTTP Error no OAuth."
        )

        return jsonify({
            "ok": False,
            "error": "Falha ao trocar authorization code.",
            "details": str(e)
        }), 502

    except Exception as e:

        logger.exception(
            "💥 Erro no callback OAuth."
        )

        return jsonify({
            "ok": False,
            "error": "Erro interno no OAuth.",
            "details": str(e)
        }), 500


# ============================================================
# MERCADO LIVRE — CHAMADA API
# ============================================================

def mercado_livre_get(
    endpoint,
    access_token=None
):

    token = (
        access_token
        or ML_ACCESS_TOKEN
    )

    if not token:

        raise RuntimeError(
            "ML_ACCESS_TOKEN não configurado."
        )

    url = (
        "https://api.mercadolibre.com"
        + endpoint
    )

    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        },
        timeout=30
    )

    if response.status_code == 429:

        logger.warning(
            "⚠️ Mercado Livre respondeu 429."
        )

        retry_after = response.headers.get(
            "Retry-After",
            "10"
        )

        try:
            espera = int(retry_after)
        except ValueError:
            espera = 10

        time.sleep(
            min(espera, 60)
        )

        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            },
            timeout=30
        )

    if response.status_code == 401:

        logger.warning(
            "⚠️ Access token Mercado Livre expirado ou inválido."
        )

        raise PermissionError(
            "ML_ACCESS_TOKEN expirado ou inválido."
        )

    if not response.ok:

        logger.error(
            "❌ Mercado Livre HTTP %s: %s",
            response.status_code,
            response.text[:2000]
        )

        response.raise_for_status()

    return response.json()


# ============================================================
# TESTE USERS/ME
# ============================================================

@app.route(
    "/mercadolivre/teste",
    methods=["GET"]
)
def mercado_livre_teste():

    try:

        dados = mercado_livre_get(
            "/users/me"
        )

        # Não retornamos token.
        return jsonify({
            "ok": True,
            "mercado_livre": {
                "id": dados.get("id"),
                "nickname": dados.get("nickname"),
                "country_id": dados.get("country_id"),
                "site_id": dados.get("site_id")
            }
        })

    except PermissionError as e:

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 401

    except Exception as e:

        logger.exception(
            "❌ Falha no teste Mercado Livre."
        )

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 502


# ============================================================
# HEALTH
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({
        "ok": True,
        "status": "online",
        "service": "bot-raposa-cacadora",
        "telegram_configurado": bool(
            TELEGRAM_TOKEN
        ),
        "mercado_livre_configurado": mercado_livre_configurado(),
        "mercado_livre_token_configurado": bool(
            ML_ACCESS_TOKEN
        )
    })


# ============================================================
# HOME
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify({
        "ok": True,
        "service": "Bot Raposa Caçadora",
        "status": "online",
        "endpoints": {
            "health": "/health",
            "oauth": "/oauth/mercadolivre",
            "oauth_callback": "/oauth/callback",
            "mercado_livre_teste": "/mercadolivre/teste"
        }
    })


# ============================================================
# OPTIONS
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
# API CONFIGURAR
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    logger.info(
        "📥 POST /api/configurar"
    )

    logger.info(
        "Origin: %s",
        request.headers.get("Origin")
    )

    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        ""
    )

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
            "❌ initData inválido: %s",
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

    dados = request.get_json(
        silent=True
    )

    if not dados:

        return jsonify({
            "ok": False,
            "error": "JSON não recebido."
        }), 400

    link = str(
        dados.get("link", "")
    ).strip()

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

    if not link:

        return jsonify({
            "ok": False,
            "error": "Link não informado."
        }), 400

    quantidade = max(
        1,
        min(quantidade, 100)
    )

    intervalo = max(
        0,
        min(intervalo, 1440)
    )

    logger.info(
        "🔗 Link: %s",
        link
    )

    logger.info(
        "📦 Quantidade: %s",
        quantidade
    )

    logger.info(
        "⏱️ Intervalo: %s",
        intervalo
    )

    # Neste momento apenas confirmamos que a configuração
    # chegou corretamente.
    #
    # A busca de produtos será adicionada depois que a
    # autenticação Mercado Livre estiver funcionando.

    return jsonify({
        "ok": True,
        "message": (
            "Configuração recebida. "
            "OAuth Mercado Livre está sendo preparado."
        ),
        "link": link,
        "quantidade": quantidade,
        "intervalo": intervalo
    }), 200


# ============================================================
# ERROS
# ============================================================

@app.errorhandler(404)
def erro_404(error):

    return jsonify({
        "ok": False,
        "error": "Rota não encontrada."
    }), 404


@app.errorhandler(405)
def erro_405(error):

    return jsonify({
        "ok": False,
        "error": "Método não permitido."
    }), 405


@app.errorhandler(500)
def erro_500(error):

    logger.exception(
        "💥 Erro interno."
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
        "🔐 Mercado Livre configurado: %s",
        mercado_livre_configurado()
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
