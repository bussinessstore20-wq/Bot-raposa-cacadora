import os
import time
import hmac
import hashlib
import logging
import threading
from urllib.parse import parse_qsl, urlencode

import requests
from flask import Flask, request, jsonify, redirect


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
# ENVIRONMENT VARIABLES
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()

CHAT_ID = os.getenv(
    "CHAT_ID",
    "@raposacacadora"
).strip()

WEBAPP_URL = os.getenv(
    "WEBAPP_URL",
    "https://bot-raposa-cacadora.vercel.app"
).strip().rstrip("/")


# Mercado Livre

ML_CLIENT_ID = os.getenv(
    "ML_CLIENT_ID",
    ""
).strip()

ML_CLIENT_SECRET = os.getenv(
    "ML_CLIENT_SECRET",
    ""
).strip()

ML_REDIRECT_URI = os.getenv(
    "ML_REDIRECT_URI",
    "https://bot-raposa-cacadora.onrender.com/oauth/callback"
).strip()


# Tokens.
#
# Eles NÃO são obrigatórios para iniciar o OAuth.
#
# Depois que o OAuth funcionar, poderão ser configurados
# como Environment Variables no Render.

ML_ACCESS_TOKEN = os.getenv(
    "ML_ACCESS_TOKEN",
    ""
).strip()

ML_REFRESH_TOKEN = os.getenv(
    "ML_REFRESH_TOKEN",
    ""
).strip()


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_API = (
    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
)


# ============================================================
# CONSTANTES
# ============================================================

INIT_DATA_MAX_AGE = 86400


# ============================================================
# CORS
# ============================================================

@app.after_request
def adicionar_cors(response):

    origin = request.headers.get("Origin")

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
        ] = "GET, POST, OPTIONS"

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

        auth_date = dados.get("auth_date")

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
# CONFIGURAÇÃO MERCADO LIVRE
# ============================================================

def mercado_livre_configurado():

    return bool(
        ML_CLIENT_ID
        and ML_CLIENT_SECRET
        and ML_REDIRECT_URI
    )


# ============================================================
# URL OAUTH
# ============================================================

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


# ============================================================
# INICIAR OAUTH
# ============================================================

@app.route(
    "/oauth/mercadolivre",
    methods=["GET"]
)
def oauth_mercadolivre():

    logger.info(
        "=========================================="
    )

    logger.info(
        "🔐 INICIANDO OAUTH MERCADO LIVRE"
    )

    logger.info(
        "=========================================="
    )

    if not mercado_livre_configurado():

        logger.error(
            "❌ Mercado Livre não está configurado."
        )

        return jsonify({
            "ok": False,
            "error": (
                "Configure ML_CLIENT_ID, "
                "ML_CLIENT_SECRET e "
                "ML_REDIRECT_URI no Render."
            )
        }), 500

    logger.info(
        "🆔 Client ID configurado: %s",
        bool(ML_CLIENT_ID)
    )

    logger.info(
        "🔐 Client Secret configurado: %s",
        bool(ML_CLIENT_SECRET)
    )

    logger.info(
        "↩️ Redirect URI: %s",
        ML_REDIRECT_URI
    )

    url = gerar_url_oauth()

    logger.info(
        "➡️ Redirecionando para:"
    )

    logger.info(
        "https://auth.mercadolivre.com.br/authorization"
    )

    return redirect(url)


# ============================================================
# TROCAR CODE POR TOKEN
# ============================================================

def trocar_code_por_token(code):

    if not ML_CLIENT_ID:

        raise RuntimeError(
            "ML_CLIENT_ID não configurado."
        )

    if not ML_CLIENT_SECRET:

        raise RuntimeError(
            "ML_CLIENT_SECRET não configurado."
        )

    if not ML_REDIRECT_URI:

        raise RuntimeError(
            "ML_REDIRECT_URI não configurado."
        )

    if not code:

        raise RuntimeError(
            "Authorization code não recebido."
        )

    logger.info(
        "=========================================="
    )

    logger.info(
        "🔑 TROCANDO AUTHORIZATION CODE POR TOKEN"
    )

    logger.info(
        "=========================================="
    )

    # ========================================================
    # ATENÇÃO
    #
    # A aplicação informada anteriormente está SEM PKCE.
    #
    # Portanto não enviamos code_verifier.
    #
    # ========================================================

    payload = {
        "grant_type": "authorization_code",
        "client_id": ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
        "code": code,
        "redirect_uri": ML_REDIRECT_URI
    }

    headers = {
        "Accept": "application/json",
        "Content-Type":
            "application/x-www-form-urlencoded"
    }

    logger.info(
        "🌐 POST https://api.mercadolibre.com/oauth/token"
    )

    logger.info(
        "grant_type: authorization_code"
    )

    logger.info(
        "client_id presente: %s",
        bool(ML_CLIENT_ID)
    )

    logger.info(
        "client_secret presente: %s",
        bool(ML_CLIENT_SECRET)
    )

    logger.info(
        "code presente: %s",
        bool(code)
    )

    logger.info(
        "redirect_uri: %s",
        ML_REDIRECT_URI
    )

    try:

        response = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            data=payload,
            headers=headers,
            timeout=30
        )

    except requests.RequestException as e:

        logger.error(
            "❌ Falha de conexão com Mercado Livre."
        )

        logger.error(
            "%s",
            e
        )

        raise RuntimeError(
            f"Falha de conexão com Mercado Livre: {e}"
        )

    logger.info(
        "📡 HTTP Mercado Livre: %s",
        response.status_code
    )

    # ========================================================
    # SUCESSO
    # ========================================================

    if response.ok:

        try:

            dados = response.json()

        except ValueError:

            logger.error(
                "❌ Mercado Livre retornou JSON inválido."
            )

            raise RuntimeError(
                "Resposta inválida do Mercado Livre."
            )

        logger.info(
            "=========================================="
        )

        logger.info(
            "✅ ACCESS TOKEN OBTIDO"
        )

        logger.info(
            "=========================================="
        )

        logger.info(
            "user_id: %s",
            dados.get("user_id")
        )

        logger.info(
            "expires_in: %s",
            dados.get("expires_in")
        )

        logger.info(
            "scope: %s",
            dados.get("scope")
        )

        logger.info(
            "access_token recebido: %s",
            bool(dados.get("access_token"))
        )

        logger.info(
            "refresh_token recebido: %s",
            bool(dados.get("refresh_token"))
        )

        # NUNCA imprimir os tokens.

        return dados

    # ========================================================
    # ERRO
    # ========================================================

    logger.error(
        "=========================================="
    )

    logger.error(
        "❌ ERRO ORIGINAL DO MERCADO LIVRE"
    )

    logger.error(
        "=========================================="
    )

    logger.error(
        "HTTP: %s",
        response.status_code
    )

    logger.error(
        "Content-Type: %s",
        response.headers.get("Content-Type")
    )

    # IMPORTANTE:
    #
    # Aqui mostramos somente a resposta enviada pelo
    # Mercado Livre.
    #
    # Não mostramos nosso client_secret.
    # Não mostramos access_token.
    # Não mostramos refresh_token.

    texto = response.text[:4000]

    logger.error(
        "Resposta Mercado Livre:"
    )

    logger.error(
        "%s",
        texto
    )

    logger.error(
        "=========================================="
    )

    # Não usamos raise_for_status() imediatamente,
    # porque precisamos devolver o corpo original.

    return {
        "oauth_error": True,
        "status_code": response.status_code,
        "response_text": texto
    }


# ============================================================
# CALLBACK
# ============================================================

@app.route(
    "/oauth/callback",
    methods=["GET"]
)
def oauth_callback():

    logger.info(
        "=========================================="
    )

    logger.info(
        "↩️ CALLBACK MERCADO LIVRE"
    )

    logger.info(
        "=========================================="
    )

    # --------------------------------------------------------
    # ERRO DEVOLVIDO PELO MERCADO LIVRE
    # --------------------------------------------------------

    erro = request.args.get(
        "error"
    )

    if erro:

        descricao = request.args.get(
            "error_description",
            ""
        )

        logger.error(
            "❌ Mercado Livre recusou autorização."
        )

        logger.error(
            "error=%s",
            erro
        )

        logger.error(
            "error_description=%s",
            descricao
        )

        return jsonify({
            "ok": False,
            "error": erro,
            "description": descricao
        }), 400

    # --------------------------------------------------------
    # CODE
    # --------------------------------------------------------

    code = request.args.get(
        "code"
    )

    logger.info(
        "🎫 Authorization code recebido: %s",
        bool(code)
    )

    if not code:

        logger.error(
            "❌ Nenhum authorization code recebido."
        )

        return jsonify({
            "ok": False,
            "error": (
                "Authorization code não recebido."
            )
        }), 400

    # --------------------------------------------------------
    # TROCA
    # --------------------------------------------------------

    try:

        token_data = trocar_code_por_token(
            code
        )

        # ----------------------------------------------------
        # ERRO ORIGINAL
        # ----------------------------------------------------

        if token_data.get(
            "oauth_error"
        ):

            status = token_data.get(
                "status_code",
                502
            )

            resposta = token_data.get(
                "response_text",
                ""
            )

            logger.error(
                "❌ Falha na troca do authorization code."
            )

            return jsonify({
                "ok": False,
                "error": (
                    "Mercado Livre recusou "
                    "a troca do authorization code."
                ),
                "status": status,
                "mercado_livre": resposta
            }), 502

        # ----------------------------------------------------
        # SUCESSO
        # ----------------------------------------------------

        access_token = token_data.get(
            "access_token"
        )

        refresh_token = token_data.get(
            "refresh_token"
        )

        if not access_token:

            logger.error(
                "❌ Mercado Livre não retornou access_token."
            )

            return jsonify({
                "ok": False,
                "error": (
                    "access_token não recebido."
                )
            }), 502

        logger.info(
            "=========================================="
        )

        logger.info(
            "🎉 OAUTH CONCLUÍDO"
        )

        logger.info(
            "=========================================="
        )

        logger.info(
            "user_id: %s",
            token_data.get("user_id")
        )

        logger.info(
            "expires_in: %s",
            token_data.get("expires_in")
        )

        logger.info(
            "scope: %s",
            token_data.get("scope")
        )

        logger.info(
            "access_token: recebido"
        )

        logger.info(
            "refresh_token: %s",
            bool(refresh_token)
        )

        # ----------------------------------------------------
        # NÃO MOSTRAR OS TOKENS NA TELA.
        #
        # Para o primeiro teste, vamos apenas informar que
        # foram recebidos.
        # ----------------------------------------------------

        return """
<!DOCTYPE html>
<html lang="pt-BR">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>Mercado Livre autorizado</title>

<style>

body {
    font-family: Arial, sans-serif;
    background: #f5f5f5;
    padding: 30px;
}

.box {
    max-width: 600px;
    margin: 50px auto;
    background: white;
    padding: 30px;
    border-radius: 15px;
    box-shadow: 0 5px 25px rgba(0,0,0,.1);
}

.ok {
    color: #16803c;
}

.warning {
    color: #9a6700;
}

</style>

</head>

<body>

<div class="box">

<h1 class="ok">
✅ Mercado Livre autorizado
</h1>

<p>
O Mercado Livre autorizou a aplicação
e o backend recebeu o access token.
</p>

<p>
O próximo passo será configurar o armazenamento
seguro dos tokens e testar a API oficial.
</p>

<p class="warning">
⚠️ Não envie seus tokens para ninguém.
</p>

</div>

</body>

</html>
"""

    except Exception as e:

        logger.exception(
            "💥 Erro inesperado no callback."
        )

        return jsonify({
            "ok": False,
            "error": "Erro interno no OAuth.",
            "details": str(e)
        }), 500


# ============================================================
# RENOVAÇÃO DO ACCESS TOKEN
# ============================================================

def renovar_access_token():

    if not ML_REFRESH_TOKEN:

        raise RuntimeError(
            "ML_REFRESH_TOKEN não configurado."
        )

    if not ML_CLIENT_ID:

        raise RuntimeError(
            "ML_CLIENT_ID não configurado."
        )

    if not ML_CLIENT_SECRET:

        raise RuntimeError(
            "ML_CLIENT_SECRET não configurado."
        )

    payload = {
        "grant_type": "refresh_token",
        "client_id": ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
        "refresh_token": ML_REFRESH_TOKEN
    }

    logger.info(
        "♻️ Renovando access token Mercado Livre..."
    )

    try:

        response = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type":
                    "application/x-www-form-urlencoded"
            },
            timeout=30
        )

    except requests.RequestException as e:

        logger.error(
            "❌ Erro de conexão durante refresh."
        )

        raise RuntimeError(
            str(e)
        )

    logger.info(
        "📡 Refresh HTTP: %s",
        response.status_code
    )

    if not response.ok:

        logger.error(
            "❌ Erro no refresh."
        )

        logger.error(
            "Resposta: %s",
            response.text[:4000]
        )

        raise RuntimeError(
            "Falha ao renovar access token."
        )

    dados = response.json()

    logger.info(
        "✅ Access token renovado."
    )

    return dados


# ============================================================
# API MERCADO LIVRE
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

    try:

        response = requests.get(
            url,
            headers={
                "Authorization":
                    f"Bearer {token}",
                "Accept":
                    "application/json"
            },
            timeout=30
        )

    except requests.RequestException as e:

        logger.error(
            "❌ Erro de conexão com API Mercado Livre."
        )

        raise RuntimeError(
            str(e)
        )

    logger.info(
        "📡 GET %s → HTTP %s",
        endpoint,
        response.status_code
    )

    if response.status_code == 401:

        raise PermissionError(
            "Access token inválido ou expirado."
        )

    if response.status_code == 429:

        retry_after = response.headers.get(
            "Retry-After",
            "10"
        )

        try:
            segundos = int(retry_after)
        except ValueError:
            segundos = 10

        segundos = min(
            segundos,
            60
        )

        logger.warning(
            "⚠️ Rate limit. Aguardando %s segundos.",
            segundos
        )

        time.sleep(segundos)

        response = requests.get(
            url,
            headers={
                "Authorization":
                    f"Bearer {token}",
                "Accept":
                    "application/json"
            },
            timeout=30
        )

    if not response.ok:

        logger.error(
            "❌ API Mercado Livre respondeu HTTP %s",
            response.status_code
        )

        logger.error(
            "Resposta: %s",
            response.text[:4000]
        )

        raise RuntimeError(
            f"Mercado Livre HTTP {response.status_code}"
        )

    return response.json()


# ============================================================
# TESTE DA CONTA MERCADO LIVRE
# ============================================================

@app.route(
    "/mercadolivre/teste",
    methods=["GET"]
)
def teste_mercado_livre():

    logger.info(
        "🧪 TESTE /users/me"
    )

    if not ML_ACCESS_TOKEN:

        return jsonify({
            "ok": False,
            "error": (
                "ML_ACCESS_TOKEN não configurado."
            )
        }), 400

    try:

        dados = mercado_livre_get(
            "/users/me"
        )

        return jsonify({
            "ok": True,
            "usuario": {
                "id": dados.get("id"),
                "nickname": dados.get("nickname"),
                "site_id": dados.get("site_id"),
                "country_id": dados.get("country_id")
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

        "service":
            "Bot Raposa Caçadora",

        "status":
            "online",

        "telegram_configurado":
            bool(TELEGRAM_TOKEN),

        "mercado_livre_configurado":
            mercado_livre_configurado(),

        "ml_access_token_configurado":
            bool(ML_ACCESS_TOKEN),

        "ml_refresh_token_configurado":
            bool(ML_REFRESH_TOKEN),

        "webapp_url":
            WEBAPP_URL,

        "redirect_uri":
            ML_REDIRECT_URI

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

        "service":
            "Bot Raposa Caçadora",

        "status":
            "online",

        "endpoints": {

            "health":
                "/health",

            "oauth":
                "/oauth/mercadolivre",

            "callback":
                "/oauth/callback",

            "teste_ml":
                "/mercadolivre/teste",

            "configurar":
                "/api/configurar"

        }

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
        "=========================================="
    )

    logger.info(
        "📥 POST /api/configurar"
    )

    logger.info(
        "Origin: %s",
        request.headers.get("Origin")
    )

    # --------------------------------------------------------
    # INIT DATA
    # --------------------------------------------------------

    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        ""
    )

    if not init_data:

        init_data = request.headers.get(
            "Telegram-Init-Data",
            ""
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

    # --------------------------------------------------------
    # LINK
    # --------------------------------------------------------

    link = str(
        dados.get(
            "link",
            ""
        )
    ).strip()

    if not link:

        return jsonify({
            "ok": False,
            "error":
                "Link não informado."
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
            "error":
                "Quantidade inválida."
        }), 400

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
            "error":
                "Intervalo inválido."
        }), 400

    quantidade = max(
        1,
        min(
            quantidade,
            100
        )
    )

    intervalo = max(
        0,
        min(
            intervalo,
            1440
        )
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
        "⏱️ Intervalo: %s minuto(s)",
        intervalo
    )

    # --------------------------------------------------------
    # POR ENQUANTO:
    #
    # NÃO FAZEMOS SCRAPING DO MELI.LA.
    #
    # Primeiro resolvemos a autorização oficial.
    # --------------------------------------------------------

    logger.info(
        "✅ Configuração recebida."
    )

    return jsonify({

        "ok": True,

        "message":
            "POST chegou ao Render!",

        "dados": {
            "link":
                link,

            "quantidade":
                quantidade,

            "intervalo":
                intervalo
        }

    }), 200


# ============================================================
# ERRO 404
# ============================================================

@app.errorhandler(404)
def erro_404(error):

    return jsonify({
        "ok": False,
        "error":
            "Rota não encontrada."
    }), 404


# ============================================================
# ERRO 405
# ============================================================

@app.errorhandler(405)
def erro_405(error):

    return jsonify({
        "ok": False,
        "error":
            "Método HTTP não permitido."
    }), 405


# ============================================================
# ERRO 500
# ============================================================

@app.errorhandler(500)
def erro_500(error):

    logger.exception(
        "💥 Erro interno."
    )

    return jsonify({
        "ok": False,
        "error":
            "Erro interno do servidor."
    }), 500


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    logger.info(
        "=========================================="
    )

    logger.info(
        "🦊 BOT RAPOSA CAÇADORA"
    )

    logger.info(
        "=========================================="
    )

    logger.info(
        "Porta: %s",
        port
    )

    logger.info(
        "Telegram configurado: %s",
        bool(TELEGRAM_TOKEN)
    )

    logger.info(
        "Mercado Livre configurado: %s",
        mercado_livre_configurado()
    )

    logger.info(
        "=========================================="
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
