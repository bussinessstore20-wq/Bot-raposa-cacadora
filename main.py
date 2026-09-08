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
# CONFIGURAÇÕES
# ============================================================

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    ""
).strip()

CHAT_ID = os.getenv(
    "CHAT_ID",
    "@raposacacadora"
).strip()

WEBAPP_URL = os.getenv(
    "WEBAPP_URL",
    "https://bot-raposa-cacadora.vercel.app"
).strip().rstrip("/")


# ============================================================
# MERCADO LIVRE
# ============================================================

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


# Estes dois NÃO precisam existir antes do primeiro OAuth.
#
# Depois que o OAuth funcionar, você poderá colocar os tokens
# nas Environment Variables do Render.
#
ML_ACCESS_TOKEN = os.getenv(
    "ML_ACCESS_TOKEN",
    ""
).strip()

ML_REFRESH_TOKEN = os.getenv(
    "ML_REFRESH_TOKEN",
    ""
).strip()


# ============================================================
# CONFIGURAÇÕES GERAIS
# ============================================================

INIT_DATA_MAX_AGE = 86400

TELEGRAM_API = (
    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
)


# ============================================================
# LOG
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(
    "raposa-cacadora"
)


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
    CORS do Mini App.

    IMPORTANTE:
    O teste anterior comprovou que:
    
    Vercel
       ↓
    Render
    
    está funcionando quando o POST é aceito.

    Aqui mantemos explicitamente o domínio do Mini App.
    """

    origin = request.headers.get(
        "Origin"
    )

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
    """
    Valida Telegram WebApp initData.

    Retorna:

        True, dados

    ou:

        False, motivo
    """

    if not init_data:

        return False, "initData ausente"

    if not TELEGRAM_TOKEN:

        logger.error(
            "❌ TELEGRAM_TOKEN não configurado."
        )

        return False, (
            "TELEGRAM_TOKEN não configurado"
        )

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

            return False, (
                "hash ausente no initData"
            )

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

                    return False, (
                        "auth_date inválido"
                    )

                if idade > INIT_DATA_MAX_AGE:

                    return False, (
                        "initData expirado"
                    )

            except ValueError:

                return False, (
                    "auth_date inválido"
                )

        return True, dados

    except Exception as e:

        logger.exception(
            "❌ Erro validando initData."
        )

        return False, str(e)


# ============================================================
# VERIFICAÇÃO DA CONFIGURAÇÃO MERCADO LIVRE
# ============================================================

def mercado_livre_configurado():

    return bool(
        ML_CLIENT_ID
        and ML_CLIENT_SECRET
        and ML_REDIRECT_URI
    )


# ============================================================
# URL DE AUTORIZAÇÃO MERCADO LIVRE
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
            "❌ Configuração Mercado Livre incompleta."
        )

        logger.error(
            "ML_CLIENT_ID configurado: %s",
            bool(ML_CLIENT_ID)
        )

        logger.error(
            "ML_CLIENT_SECRET configurado: %s",
            bool(ML_CLIENT_SECRET)
        )

        logger.error(
            "ML_REDIRECT_URI configurado: %s",
            bool(ML_REDIRECT_URI)
        )

        return jsonify({
            "ok": False,
            "error": (
                "Configuração do Mercado Livre "
                "incompleta."
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
        "➡️ Redirecionando para autorização Mercado Livre."
    )

    return redirect(url)


# ============================================================
# TROCAR CODE POR TOKEN
# ============================================================

def trocar_code_por_token(code):

    logger.info(
        "🔑 Iniciando troca authorization code → token."
    )

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
            "Authorization code vazio."
        )

    # --------------------------------------------------------
    # IMPORTANTE:
    #
    # Sua aplicação está configurada sem PKCE.
    #
    # Portanto NÃO enviamos code_verifier.
    #
    # A documentação do Mercado Livre indica que
    # code_verifier é usado quando PKCE está habilitado.
    # --------------------------------------------------------

    payload = {
        "grant_type": "authorization_code",
        "client_id": ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
        "code": code,
        "redirect_uri": ML_REDIRECT_URI
    }

    logger.info(
        "🌐 Endpoint OAuth:"
    )

    logger.info(
        "https://api.mercadolibre.com/oauth/token"
    )

    logger.info(
        "🆔 Client ID presente: %s",
        bool(ML_CLIENT_ID)
    )

    logger.info(
        "🔐 Client Secret presente: %s",
        bool(ML_CLIENT_SECRET)
    )

    logger.info(
        "🎫 Authorization code presente: %s",
        bool(code)
    )

    logger.info(
        "↩️ Redirect URI: %s",
        ML_REDIRECT_URI
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
            "❌ Falha de conexão com Mercado Livre:"
        )

        logger.error(
            "%s",
            e
        )

        raise

    logger.info(
        "📡 Mercado Livre OAuth HTTP: %s",
        response.status_code
    )

    # --------------------------------------------------------
    # SUCESSO
    # --------------------------------------------------------

    if response.ok:

        try:

            dados = response.json()

        except ValueError:

            logger.error(
                "❌ Mercado Livre retornou resposta "
                "que não é JSON."
            )

            raise RuntimeError(
                "Resposta OAuth inválida."
            )

        logger.info(
            "✅ TOKEN OBTIDO COM SUCESSO."
        )

        logger.info(
            "👤 user_id recebido: %s",
            dados.get("user_id")
        )

        logger.info(
            "⏱️ expires_in: %s",
            dados.get("expires_in")
        )

        logger.info(
            "🔐 scope recebido: %s",
            dados.get("scope")
        )

        # NÃO mostrar tokens no log.
        logger.info(
            "🔑 access_token recebido: SIM"
        )

        logger.info(
            "♻️ refresh_token recebido: %s",
            bool(dados.get("refresh_token"))
        )

        return dados

    # --------------------------------------------------------
    # ERRO
    # --------------------------------------------------------

    logger.error(
        "❌ MERCADO LIVRE RECUSOU O OAUTH."
    )

    logger.error(
        "HTTP: %s",
        response.status_code
    )

    # O corpo é justamente o que precisamos para descobrir
    # a causa do 403.
    #
    # NÃO exibimos client_secret, access_token ou
    # refresh_token.
    logger.error(
        "📄 Corpo da resposta:"
    )

    logger.error(
        "%s",
        response.text[:4000]
    )

    if response.status_code == 403:

        logger.error(
            "⚠️ HTTP 403: acesso proibido."
        )

        logger.error(
            "Possíveis causas documentadas pelo Mercado Livre:"
        )

        logger.error(
            "- aplicação sem grant com o usuário"
        )

        logger.error(
            "- scopes/permissões insuficientes"
        )

        logger.error(
            "- IP bloqueado"
        )

        logger.error(
            "- conta/usuário sem permissão"
        )

        logger.error(
            "- problema com domínio/país"
        )

    if response.status_code == 401:

        logger.error(
            "⚠️ HTTP 401: credenciais inválidas "
            "ou não autorizadas."
        )

    if response.status_code == 429:

        logger.error(
            "⚠️ HTTP 429: rate limit."
        )

    response.raise_for_status()

    raise RuntimeError(
        "Falha desconhecida no OAuth."
    )


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

    code = request.args.get(
        "code"
    )

    # Não registramos o code no log.
    logger.info(
        "🎫 Authorization code recebido: %s",
        bool(code)
    )

    if not code:

        logger.error(
            "❌ Authorization code não recebido."
        )

        return jsonify({
            "ok": False,
            "error": (
                "Authorization code não recebido."
            )
        }), 400

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

        if not access_token:

            logger.error(
                "❌ access_token não veio na resposta."
            )

            return jsonify({
                "ok": False,
                "error": (
                    "Mercado Livre não retornou "
                    "access_token."
                )
            }), 502

        logger.info(
            "=========================================="
        )

        logger.info(
            "✅ OAUTH CONCLUÍDO COM SUCESSO"
        )

        logger.info(
            "=========================================="
        )

        logger.info(
            "👤 user_id: %s",
            token_data.get("user_id")
        )

        logger.info(
            "⏱️ expires_in: %s",
            token_data.get("expires_in")
        )

        logger.info(
            "🔐 scope: %s",
            token_data.get("scope")
        )

        logger.info(
            "🔑 access_token: recebido"
        )

        logger.info(
            "♻️ refresh_token: %s",
            bool(refresh_token)
        )

        # ----------------------------------------------------
        # IMPORTANTE
        # ----------------------------------------------------
        #
        # NÃO mostramos os valores dos tokens.
        #
        # O Render não deve receber esses valores através
        # do código-fonte.
        #
        # Neste primeiro teste, você deverá copiá-los da
        # resposta apenas para configurar as Environment
        # Variables do Render.
        #
        # NUNCA envie os tokens para mim.
        # ----------------------------------------------------

        return """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Mercado Livre</title>
<style>
body {
    font-family: Arial, sans-serif;
    background: #f5f5f5;
    padding: 40px;
}

.box {
    max-width: 600px;
    margin: auto;
    background: white;
    padding: 30px;
    border-radius: 12px;
    box-shadow: 0 2px 12px rgba(0,0,0,.1);
}

.ok {
    color: #16803c;
}

.warning {
    color: #8a5a00;
}

code {
    background: #eee;
    padding: 4px 8px;
    border-radius: 5px;
}
</style>
</head>

<body>

<div class="box">

<h1 class="ok">
✅ Mercado Livre autorizado
</h1>

<p>
A autorização foi concluída e o Mercado Livre
retornou os tokens.
</p>

<p>
Agora configure no Render:
</p>

<ul>
<li><code>ML_ACCESS_TOKEN</code></li>
<li><code>ML_REFRESH_TOKEN</code></li>
</ul>

<p class="warning">
⚠️ Nunca coloque esses tokens no GitHub
e nunca envie os valores para outra pessoa.
</p>

<p>
Depois disso, será possível testar a conexão
com a API oficial.
</p>

</div>

</body>
</html>
"""

    except requests.HTTPError as e:

        logger.exception(
            "❌ HTTP ERROR durante OAuth."
        )

        return jsonify({
            "ok": False,
            "error": (
                "Falha ao trocar authorization code."
            ),
            "details": str(e)
        }), 502

    except Exception as e:

        logger.exception(
            "💥 ERRO durante callback OAuth."
        )

        return jsonify({
            "ok": False,
            "error": "Erro interno no OAuth.",
            "details": str(e)
        }), 500


# ============================================================
# REFRESH TOKEN
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
            "❌ Falha de conexão durante refresh."
        )

        raise

    logger.info(
        "📡 Refresh HTTP: %s",
        response.status_code
    )

    if not response.ok:

        logger.error(
            "❌ Erro renovando token:"
        )

        logger.error(
            "%s",
            response.text[:4000]
        )

        response.raise_for_status()

    dados = response.json()

    logger.info(
        "✅ Novo access token recebido."
    )

    logger.info(
        "♻️ Novo refresh token recebido: %s",
        bool(dados.get("refresh_token"))
    )

    return dados


# ============================================================
# GET API MERCADO LIVRE
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

    logger.info(
        "🌐 GET Mercado Livre: %s",
        endpoint
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
            "❌ Erro de conexão Mercado Livre."
        )

        raise

    logger.info(
        "📡 Mercado Livre HTTP: %s",
        response.status_code
    )

    if response.status_code == 401:

        logger.warning(
            "⚠️ Access token expirado ou inválido."
        )

        raise PermissionError(
            "Access token Mercado Livre inválido."
        )

    if response.status_code == 429:

        logger.warning(
            "⚠️ Mercado Livre rate limit 429."
        )

        retry_after = response.headers.get(
            "Retry-After",
            "10"
        )

        try:

            segundos = int(
                retry_after
            )

        except ValueError:

            segundos = 10

        segundos = min(
            segundos,
            60
        )

        logger.info(
            "⏳ Aguardando %s segundos.",
            segundos
        )

        time.sleep(
            segundos
        )

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
            "❌ Erro API Mercado Livre:"
        )

        logger.error(
            "%s",
            response.text[:4000]
        )

        response.raise_for_status()

    return response.json()


# ============================================================
# TESTE /users/me
# ============================================================

@app.route(
    "/mercadolivre/teste",
    methods=["GET"]
)
def mercado_livre_teste():

    logger.info(
        "🧪 TESTANDO /users/me"
    )

    if not ML_ACCESS_TOKEN:

        return jsonify({
            "ok": False,
            "error": (
                "ML_ACCESS_TOKEN não configurado "
                "no Render."
            )
        }), 400

    try:

        dados = mercado_livre_get(
            "/users/me"
        )

        return jsonify({
            "ok": True,
            "mercado_livre": {
                "id": dados.get("id"),
                "nickname": dados.get(
                    "nickname"
                ),
                "country_id": dados.get(
                    "country_id"
                ),
                "site_id": dados.get(
                    "site_id"
                )
            }
        })

    except PermissionError as e:

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 401

    except Exception as e:

        logger.exception(
            "❌ Falha no teste /users/me."
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

        "mercado_livre_configurado": (
            mercado_livre_configurado()
        ),

        "ml_access_token_configurado": bool(
            ML_ACCESS_TOKEN
        ),

        "ml_refresh_token_configurado": bool(
            ML_REFRESH_TOKEN
        ),

        "webapp_url": WEBAPP_URL
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
            "mercadolivre_teste":
                "/mercadolivre/teste"
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
    # TELEGRAM INIT DATA
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

    logger.info(
        "🔐 Telegram initData recebido: %s",
        bool(init_data)
    )

    # --------------------------------------------------------
    # VALIDAÇÃO TELEGRAM
    # --------------------------------------------------------

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
            "error": (
                "Telegram initData inválido"
            ),
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
        "📦 JSON recebido."
    )

    # Não precisamos registrar initData,
    # token ou informações sensíveis.

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
            "error": (
                "Link da vitrine não informado."
            )
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
        "🔗 Link recebido: %s",
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
    # IMPORTANTE
    # --------------------------------------------------------
    #
    # Por enquanto NÃO iniciamos scraping do meli.la.
    #
    # Primeiro precisamos concluir a autorização oficial
    # do Mercado Livre.
    # --------------------------------------------------------

    logger.info(
        "✅ Configuração recebida corretamente."
    )

    return jsonify({
        "ok": True,
        "message": (
            "Configuração recebida "
            "corretamente pelo Render."
        ),
        "link": link,
        "quantidade": quantidade,
        "intervalo": intervalo
    }), 200


# ============================================================
# 404
# ============================================================

@app.errorhandler(404)
def erro_404(error):

    return jsonify({
        "ok": False,
        "error": "Rota não encontrada."
    }), 404


# ============================================================
# 405
# ============================================================

@app.errorhandler(405)
def erro_405(error):

    return jsonify({
        "ok": False,
        "error": (
            "Método HTTP não permitido."
        )
    }), 405


# ============================================================
# 500
# ============================================================

@app.errorhandler(500)
def erro_500(error):

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
        "=========================================="
    )

    logger.info(
        "🦊 BOT RAPOSA CAÇADORA"
    )

    logger.info(
        "=========================================="
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
        "🤖 Telegram configurado: %s",
        bool(TELEGRAM_TOKEN)
    )

    logger.info(
        "🛒 Mercado Livre configurado: %s",
        mercado_livre_configurado()
    )

    logger.info(
        "🔑 ML access token configurado: %s",
        bool(ML_ACCESS_TOKEN)
    )

    logger.info(
        "♻️ ML refresh token configurado: %s",
        bool(ML_REFRESH_TOKEN)
    )

    logger.info(
        "=========================================="
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
