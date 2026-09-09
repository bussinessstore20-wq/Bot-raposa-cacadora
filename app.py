import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re

from urllib.parse import parse_qsl

import requests
from bs4 import BeautifulSoup

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS


# ============================================================
# APP
# ============================================================

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    }
)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    ""
).strip()

CHANNEL_USERNAME = os.environ.get(
    "CHANNEL_USERNAME",
    ""
).strip()

SHOPEE_API_URL = os.environ.get(
    "SHOPEE_API_URL",
    ""
).strip()

SHOPEE_APP_ID = os.environ.get(
    "SHOPEE_APP_ID",
    ""
).strip()

SHOPEE_SECRET = os.environ.get(
    "SHOPEE_SECRET",
    ""
).strip()


MAX_LINKS = 20

INTERVALOS_PERMITIDOS = {
    10,
    60,
    300,
    600
}


# ============================================================
# ARMAZENAMENTO
# ============================================================

tarefas = {}

tarefas_lock = threading.Lock()


# ============================================================
# FUNÇÕES DE SEGURANÇA PARA DEBUG
# ============================================================

def mascara_valor(valor):
    """
    Nunca mostra o conteúdo completo de uma credencial.
    """

    if not valor:
        return ""

    valor = str(valor)

    if len(valor) <= 4:
        return "*" * len(valor)

    return (
        valor[:2]
        + ("*" * (len(valor) - 4))
        + valor[-2:]
    )


def debug_variavel(nome):
    """
    Retorna apenas informações seguras
    sobre uma variável de ambiente.
    """

    valor = os.environ.get(
        nome,
        ""
    ).strip()

    return {
        "existe": bool(valor),
        "tamanho": len(valor),
        "mascara": mascara_valor(valor)
    }


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_api_url(metodo):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    return (
        f"https://api.telegram.org/bot{token}/{metodo}"
    )


def telegram_get_me():

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {
            "ok": False,
            "erro": "BOT_TOKEN não configurado."
        }

    try:

        resposta = requests.get(
            telegram_api_url("getMe"),
            timeout=20
        )

        return resposta.json()

    except Exception as erro:

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# DEBUG ENV
# ============================================================

@app.route(
    "/debug-env",
    methods=["GET"]
)
def debug_env():

    resultado = {

        "status":
            "ok",

        "telegram": {

            "BOT_TOKEN":
                debug_variavel(
                    "BOT_TOKEN"
                ),

            "CHANNEL_USERNAME":
                debug_variavel(
                    "CHANNEL_USERNAME"
                )
        },

        "shopee": {

            "SHOPEE_API_URL":
                debug_variavel(
                    "SHOPEE_API_URL"
                ),

            "SHOPEE_APP_ID":
                debug_variavel(
                    "SHOPEE_APP_ID"
                ),

            "SHOPEE_SECRET":
                debug_variavel(
                    "SHOPEE_SECRET"
                )
        },

        "ambiente": {

            "PORT":
                os.environ.get(
                    "PORT",
                    ""
                ),

            "PYTHON_VERSION":
                os.environ.get(
                    "PYTHON_VERSION",
                    ""
                )
        },

        "timestamp":
            int(time.time())
    }

    return jsonify(
        resultado
    )


# ============================================================
# DEBUG TELEGRAM
# ============================================================

@app.route(
    "/debug-telegram",
    methods=["GET"]
)
def debug_telegram():

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    canal = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()

    resultado = telegram_get_me()

    bot = None

    if resultado.get("ok"):

        bot = resultado.get(
            "result"
        )

    return jsonify({

        "BOT_TOKEN": {

            "existe":
                bool(token),

            "tamanho":
                len(token)
        },

        "CHANNEL_USERNAME": {

            "existe":
                bool(canal),

            "valor":
                canal
        },

        "telegram_api_ok":
            resultado.get(
                "ok",
                False
            ),

        "bot": {

            "id":
                bot.get("id")
                if bot else None,

            "is_bot":
                bot.get("is_bot")
                if bot else None,

            "first_name":
                bot.get("first_name")
                if bot else None,

            "username":
                bot.get("username")
                if bot else None
        },

        "erro":
            resultado.get(
                "erro"
            )
            or
            resultado.get(
                "description"
            )
    })


# ============================================================
# DEBUG SHOPEE
# ============================================================

@app.route(
    "/debug-shopee",
    methods=["GET"]
)
def debug_shopee():

    api_url = os.environ.get(
        "SHOPEE_API_URL",
        ""
    ).strip()

    app_id = os.environ.get(
        "SHOPEE_APP_ID",
        ""
    ).strip()

    secret = os.environ.get(
        "SHOPEE_SECRET",
        ""
    ).strip()

    resultado = {

        "configuracao": {

            "SHOPEE_API_URL": {

                "existe":
                    bool(api_url),

                "tamanho":
                    len(api_url),

                "valor":
                    api_url
            },

            "SHOPEE_APP_ID": {

                "existe":
                    bool(app_id),

                "tamanho":
                    len(app_id),

                "mascara":
                    mascara_valor(
                        app_id
                    )
            },

            "SHOPEE_SECRET": {

                "existe":
                    bool(secret),

                "tamanho":
                    len(secret),

                "mascara":
                    mascara_valor(
                        secret
                    )
            }
        },

        "validacao": {

            "api_url_configurada":
                bool(api_url),

            "app_id_configurado":
                bool(app_id),

            "secret_configurado":
                bool(secret),

            "configuracao_completa":
                bool(
                    api_url
                    and
                    app_id
                    and
                    secret
                )
        },

        "timestamp":
            int(time.time())
    }

    return jsonify(
        resultado
    )


# ============================================================
# HEALTH
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    canal = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()

    app_id = os.environ.get(
        "SHOPEE_APP_ID",
        ""
    ).strip()

    secret = os.environ.get(
        "SHOPEE_SECRET",
        ""
    ).strip()

    api_url = os.environ.get(
        "SHOPEE_API_URL",
        ""
    ).strip()

    return jsonify({

        "status":
            "ok",

        "service":
            "raposa-cacadora",

        "telegram": {

            "configurado":
                bool(token),

            "canal_configurado":
                bool(canal)
        },

        "shopee": {

            "api_url_configurada":
                bool(api_url),

            "app_id_configurado":
                bool(app_id),

            "secret_configurado":
                bool(secret),

            "configuracao_completa":
                bool(
                    api_url
                    and
                    app_id
                    and
                    secret
                )
        },

        "timestamp":
            int(time.time())
    })


# ============================================================
# TESTE DE CONECTIVIDADE DA API SHOPEE
# ============================================================

@app.route(
    "/debug-shopee-conexao",
    methods=["GET"]
)
def debug_shopee_conexao():

    api_url = os.environ.get(
        "SHOPEE_API_URL",
        ""
    ).strip()

    if not api_url:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "SHOPEE_API_URL não configurada."
        }), 500

    try:

        print(
            "[DEBUG SHOPEE] Testando:",
            api_url
        )

        resposta = requests.get(
            api_url,
            timeout=20
        )

        return jsonify({

            "sucesso":
                True,

            "http_status":
                resposta.status_code,

            "content_type":
                resposta.headers.get(
                    "Content-Type",
                    ""
                ),

            "tamanho_resposta":
                len(
                    resposta.content
                ),

            "url_final":
                resposta.url
        })

    except Exception as erro:

        print(
            "[DEBUG SHOPEE] Erro:",
            erro
        )

        return jsonify({

            "sucesso":
                False,

            "erro":
                str(erro)
        }), 500


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route("/")
def index():

    try:

        return render_template(
            "index.html"
        )

    except Exception:

        return jsonify({

            "service":
                "raposa-cacadora",

            "status":
                "online",

            "mensagem":
                "Servidor funcionando."
        })


# ============================================================
# ROTA DE TESTE
# ============================================================

@app.route(
    "/api/teste",
    methods=["GET"]
)
def teste():

    return jsonify({

        "sucesso":
            True,

        "mensagem":
            "API funcionando corretamente.",

        "telegram_configurado":
            bool(
                os.environ.get(
                    "BOT_TOKEN",
                    ""
                ).strip()
            ),

        "shopee_configurada":
            bool(
                os.environ.get(
                    "SHOPEE_APP_ID",
                    ""
                ).strip()
                and
                os.environ.get(
                    "SHOPEE_SECRET",
                    ""
                ).strip()
            ),

        "timestamp":
            int(time.time())
    })


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
