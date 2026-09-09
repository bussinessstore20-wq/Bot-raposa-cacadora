import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re

from urllib.parse import urlparse, parse_qsl

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

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "").strip()

SHOPEE_API_URL = os.environ.get("SHOPEE_API_URL", "").strip()
SHOPEE_APP_ID = os.environ.get("SHOPEE_APP_ID", "").strip()
SHOPEE_SECRET = os.environ.get("SHOPEE_SECRET", "").strip()

MAX_LINKS = 20

INTERVALOS_PERMITIDOS = {
    10,
    60,
    300,
    600
}

tarefas = {}
tarefas_lock = threading.Lock()


# ============================================================
# LOG
# ============================================================

def log(msg):
    print(msg, flush=True)


# ============================================================
# MÁSCARA
# ============================================================

def mascara_valor(valor):
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
    valor = os.environ.get(nome, "").strip()

    return {
        "existe": bool(valor),
        "tamanho": len(valor),
        "mascara": mascara_valor(valor)
    }


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api_url(metodo):
    token = os.environ.get("BOT_TOKEN", "").strip()

    return f"https://api.telegram.org/bot{token}/{metodo}"


def telegram_get_me():

    token = os.environ.get("BOT_TOKEN", "").strip()

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


def telegram_enviar_mensagem(texto):

    token = os.environ.get("BOT_TOKEN", "").strip()
    canal = os.environ.get("CHANNEL_USERNAME", "").strip()

    if not token:
        return {
            "ok": False,
            "erro": "BOT_TOKEN não configurado."
        }

    if not canal:
        return {
            "ok": False,
            "erro": "CHANNEL_USERNAME não configurado."
        }

    try:

        resposta = requests.post(
            telegram_api_url("sendMessage"),
            json={
                "chat_id": canal,
                "text": texto,
                "disable_web_page_preview": False
            },
            timeout=30
        )

        try:
            dados = resposta.json()
        except Exception:
            dados = {
                "ok": False,
                "texto": resposta.text[:1000]
            }

        return dados

    except Exception as erro:

        return {
            "ok": False,
            "erro": str(erro)
        }


def telegram_enviar_foto(imagem, legenda):

    token = os.environ.get("BOT_TOKEN", "").strip()
    canal = os.environ.get("CHANNEL_USERNAME", "").strip()

    if not token:
        return {
            "ok": False,
            "erro": "BOT_TOKEN não configurado."
        }

    if not canal:
        return {
            "ok": False,
            "erro": "CHANNEL_USERNAME não configurado."
        }

    if not imagem:
        return telegram_enviar_mensagem(legenda)

    try:

        log("[TELEGRAM] Baixando imagem:")
        log(imagem)

        imagem_resposta = requests.get(
            imagem,
            timeout=30,
            headers={
                "User-Agent":
                    "Mozilla/5.0"
            }
        )

        log(
            f"[TELEGRAM] HTTP imagem: "
            f"{imagem_resposta.status_code}"
        )

        if imagem_resposta.status_code != 200:
            return telegram_enviar_mensagem(legenda)

        arquivos = {
            "photo": (
                "produto.jpg",
                imagem_resposta.content,
                imagem_resposta.headers.get(
                    "Content-Type",
                    "image/jpeg"
                )
            )
        }

        dados = {
            "chat_id": canal,
            "caption": legenda
        }

        resposta = requests.post(
            telegram_api_url("sendPhoto"),
            data=dados,
            files=arquivos,
            timeout=60
        )

        try:
            return resposta.json()
        except Exception:
            return {
                "ok": False,
                "texto": resposta.text[:1000]
            }

    except Exception as erro:

        log(
            f"[TELEGRAM] Erro ao enviar foto: {erro}"
        )

        return telegram_enviar_mensagem(legenda)


# ============================================================
# DEBUG ENV
# ============================================================

@app.route("/debug-env", methods=["GET"])
def debug_env():

    return jsonify({

        "status": "ok",

        "telegram": {

            "BOT_TOKEN":
                debug_variavel("BOT_TOKEN"),

            "CHANNEL_USERNAME":
                debug_variavel("CHANNEL_USERNAME")
        },

        "shopee": {

            "SHOPEE_API_URL":
                debug_variavel("SHOPEE_API_URL"),

            "SHOPEE_APP_ID":
                debug_variavel("SHOPEE_APP_ID"),

            "SHOPEE_SECRET":
                debug_variavel("SHOPEE_SECRET")
        },

        "ambiente": {

            "PORT":
                os.environ.get("PORT", ""),

            "PYTHON_VERSION":
                os.environ.get(
                    "PYTHON_VERSION",
                    ""
                )
        },

        "timestamp":
            int(time.time())
    })


# ============================================================
# DEBUG TELEGRAM
# ============================================================

@app.route("/debug-telegram", methods=["GET"])
def debug_telegram():

    token = os.environ.get("BOT_TOKEN", "").strip()
    canal = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()

    resultado = telegram_get_me()

    bot = None

    if resultado.get("ok"):
        bot = resultado.get("result")

    return jsonify({

        "BOT_TOKEN": {
            "existe": bool(token),
            "tamanho": len(token)
        },

        "CHANNEL_USERNAME": {
            "existe": bool(canal),
            "valor": canal
        },

        "telegram_api_ok":
            resultado.get("ok", False),

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
            resultado.get("erro")
            or resultado.get("description")
    })


# ============================================================
# DEBUG SHOPEE
# ============================================================

@app.route("/debug-shopee", methods=["GET"])
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

    return jsonify({

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
                    mascara_valor(app_id)
            },

            "SHOPEE_SECRET": {

                "existe":
                    bool(secret),

                "tamanho":
                    len(secret),

                "mascara":
                    mascara_valor(secret)
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
                    and app_id
                    and secret
                )
        },

        "timestamp":
            int(time.time())
    })


# ============================================================
# TESTE DE CONEXÃO SHOPEE
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

            "sucesso": False,

            "erro":
                "SHOPEE_API_URL não configurada."
        }), 500

    try:

        log(
            "[DEBUG SHOPEE] Testando conexão:"
        )

        log(api_url)

        resposta = requests.get(
            api_url,
            timeout=20
        )

        return jsonify({

            "sucesso": True,

            "http_status":
                resposta.status_code,

            "content_type":
                resposta.headers.get(
                    "Content-Type",
                    ""
                ),

            "tamanho_resposta":
                len(resposta.content),

            "url_final":
                resposta.url
        })

    except Exception as erro:

        return jsonify({

            "sucesso": False,

            "erro": str(erro)
        }), 500


# ============================================================
# RESOLVER LINK SHOPEE
# ============================================================

def resolver_link_shopee(url):

    log("========================================")
    log("[SHOPEE] Tentando resolver URL:")
    log(url)

    headers = {
        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Linux; Android 15) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 "
                "Mobile Safari/537.36"
            ),
        "Accept":
            (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8"
    }

    try:

        resposta = requests.get(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=30
        )

        log(
            f"[SHOPEE] HTTP: "
            f"{resposta.status_code}"
        )

        log(
            "[SHOPEE] URL final HTTP:"
        )

        log(resposta.url)

        return {
            "url_final": resposta.url,
            "html": resposta.text,
            "status": resposta.status_code
        }

    except Exception as erro:

        log(
            f"[SHOPEE] Erro ao resolver URL: "
            f"{erro}"
        )

        return {
            "url_final": url,
            "html": "",
            "status": 0,
            "erro": str(erro)
        }


# ============================================================
# EXTRAIR IDS DE URL DE PRODUTO
# ============================================================

def extrair_ids_produto(url):

    if not url:
        return None, None

    # --------------------------------------------------------
    # Formato:
    #
    # shopee.com.br/LOJA/ITEM
    #
    # Exemplo:
    #
    # /opaanlp/217896078/58202483323
    # --------------------------------------------------------

    padroes = [

        r"shopee\.com\.br/[^/?#]+/(\d+)/(\d+)",

        r"shopee\.com/[^/?#]+/(\d+)/(\d+)",

        r"/product/(\d+)/(\d+)",

        r"shop[_-]?id[=/](\d+).*item[_-]?id[=/](\d+)"
    ]

    for padrao in padroes:

        encontrado = re.search(
            padrao,
            url,
            flags=re.IGNORECASE
        )

        if encontrado:

            shop_id = encontrado.group(1)
            item_id = encontrado.group(2)

            log(
                "[SHOPEE] IDs encontrados:"
            )

            log(
                f"[SHOPEE] shopId: {shop_id}"
            )

            log(
                f"[SHOPEE] itemId: {item_id}"
            )

            return shop_id, item_id

    # --------------------------------------------------------
    # Tenta procurar no HTML
    # --------------------------------------------------------

    return None, None


# ============================================================
# EXTRAIR DADOS DO HTML
# ============================================================

def extrair_dados_html(html, url):

    if not html:
        return {}

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    titulo = ""
    imagem = ""
    preco_atual = ""
    preco_antigo = ""

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    meta_title = soup.find(
        "meta",
        attrs={
            "property":
                "og:title"
        }
    )

    if meta_title:

        titulo = (
            meta_title.get("content")
            or ""
        ).strip()

    if not titulo:

        title = soup.find("title")

        if title:

            titulo = (
                title.get_text(
                    " ",
                    strip=True
                )
            )

    # --------------------------------------------------------
    # OG IMAGE
    # --------------------------------------------------------

    meta_image = soup.find(
        "meta",
        attrs={
            "property":
                "og:image"
        }
    )

    if meta_image:

        imagem = (
            meta_image.get("content")
            or ""
        ).strip()

    # --------------------------------------------------------
    # OG DESCRIPTION
    # --------------------------------------------------------

    meta_description = soup.find(
        "meta",
        attrs={
            "property":
                "og:description"
        }
    )

    descricao = ""

    if meta_description:

        descricao = (
            meta_description.get("content")
            or ""
        ).strip()

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    scripts = soup.find_all(
        "script",
        attrs={
            "type":
                "application/ld+json"
        }
    )

    for script in scripts:

        texto = script.string

        if not texto:
            continue

        try:

            dados = json.loads(texto)

            if isinstance(
                dados,
                dict
            ):

                if not titulo:

                    titulo = str(
                        dados.get(
                            "name",
                            ""
                        )
                    ).strip()

                if not imagem:

                    imagem_valor = dados.get(
                        "image",
                        ""
                    )

                    if isinstance(
                        imagem_valor,
                        list
                    ):

                        imagem_valor = (
                            imagem_valor[0]
                            if imagem_valor
                            else ""
                        )

                    imagem = str(
                        imagem_valor
                    ).strip()

                offers = dados.get(
                    "offers"
                )

                if isinstance(
                    offers,
                    dict
                ):

                    preco = offers.get(
                        "price"
                    )

                    if preco:

                        preco_atual = str(
                            preco
                        )

        except Exception:
            pass

    # --------------------------------------------------------
    # Meta de preço
    # --------------------------------------------------------

    metas_preco = [

        "product:price:amount",

        "og:price:amount"
    ]

    for propriedade in metas_preco:

        meta = soup.find(
            "meta",
            attrs={
                "property":
                    propriedade
            }
        )

        if meta and not preco_atual:

            preco_atual = (
                meta.get("content")
                or ""
            ).strip()

    # --------------------------------------------------------
    # Busca simples por preço
    # --------------------------------------------------------

    if not preco_atual:

        texto = soup.get_text(
            " ",
            strip=True
        )

        encontrados = re.findall(
            r"R\$\s?[\d\.,]+",
            texto
        )

        if encontrados:

            preco_atual = encontrados[0]

    return {

        "titulo":
            titulo,

        "descricao":
            descricao,

        "imagem":
            imagem,

        "preco_atual":
            preco_atual,

        "preco_antigo":
            preco_antigo
    }


# ============================================================
# ASSINATURA SHOPEE
# ============================================================

def gerar_assinatura(path, body):

    app_id = os.environ.get(
        "SHOPEE_APP_ID",
        ""
    ).strip()

    secret = os.environ.get(
        "SHOPEE_SECRET",
        ""
    ).strip()

    if not app_id:
        raise RuntimeError(
            "SHOPEE_APP_ID não configurado."
        )

    if not secret:
        raise RuntimeError(
            "SHOPEE_SECRET não configurado."
        )

    timestamp = int(time.time())

    # --------------------------------------------------------
    # Assinatura usada pela Open Platform da Shopee:
    #
    # HMAC-SHA256(
    #     appId + path + timestamp + body,
    #     secret
    # )
    # --------------------------------------------------------

    mensagem = (
        str(app_id)
        + str(path)
        + str(timestamp)
        + str(body)
    )

    assinatura = hmac.new(
        secret.encode("utf-8"),
        mensagem.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return assinatura, timestamp


# ============================================================
# API GRAPHQL SHOPEE
# ============================================================

def consultar_shopee_api(
    shop_id,
    item_id
):

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

    log("========================================")
    log("[SHOPEE API] Iniciando consulta")
    log(
        f"[SHOPEE API] shopId={shop_id}"
    )
    log(
        f"[SHOPEE API] itemId={item_id}"
    )

    if not api_url:

        log(
            "[SHOPEE API] ERRO: "
            "SHOPEE_API_URL não configurada."
        )

        return {}

    if not app_id:

        log(
            "[SHOPEE API] ERRO: "
            "SHOPEE_APP_ID não configurado."
        )

        return {}

    if not secret:

        log(
            "[SHOPEE API] ERRO: "
            "SHOPEE_SECRET não configurado."
        )

        return {}

    # --------------------------------------------------------
    # IMPORTANTE:
    #
    # O endpoint configurado no Render deve ser o endpoint
    # oficial da API GraphQL fornecido no painel da Shopee.
    # --------------------------------------------------------

    query = """
    query GetItem($shopId: Int!, $itemId: Int!) {
        item(
            shopId: $shopId,
            itemId: $itemId
        ) {
            itemId
            shopId
            title
            image
            price
            originalPrice
            description
            url
        }
    }
    """

    variables = {

        "shopId":
            int(shop_id),

        "itemId":
            int(item_id)
    }

    payload = {

        "query":
            query,

        "variables":
            variables
    }

    body = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False
    )

    # --------------------------------------------------------
    # Descobre o path da URL
    # --------------------------------------------------------

    parsed = urlparse(api_url)

    path = parsed.path or "/"

    # --------------------------------------------------------
    # Assinatura
    # --------------------------------------------------------

    try:

        assinatura, timestamp = (
            gerar_assinatura(
                path,
                body
            )
        )

    except Exception as erro:

        log(
            f"[SHOPEE API] ERRO assinatura: "
            f"{erro}"
        )

        return {}

    # --------------------------------------------------------
    # Headers
    # --------------------------------------------------------

    headers = {

        "Content-Type":
            "application/json",

        "Authorization":
            assinatura,

        "X-Shopee-App-Id":
            str(app_id),

        "X-Shopee-Timestamp":
            str(timestamp)
    }

    # --------------------------------------------------------
    # NÃO imprime Secret nem assinatura completa.
    # --------------------------------------------------------

    log(
        "[SHOPEE API] Enviando GraphQL..."
    )

    log(
        f"[SHOPEE API] URL: {api_url}"
    )

    log(
        f"[SHOPEE API] AppID: "
        f"{mascara_valor(app_id)}"
    )

    log(
        f"[SHOPEE API] Timestamp: "
        f"{timestamp}"
    )

    try:

        resposta = requests.post(
            api_url,
            headers=headers,
            data=body.encode("utf-8"),
            timeout=30
        )

        log(
            f"[SHOPEE API] HTTP: "
            f"{resposta.status_code}"
        )

        log(
            "[SHOPEE API] Content-Type: "
            + resposta.headers.get(
                "Content-Type",
                ""
            )
        )

        texto_resposta = resposta.text

        # ----------------------------------------------------
        # Tenta JSON
        # ----------------------------------------------------

        try:

            dados = resposta.json()

        except Exception:

            log(
                "[SHOPEE API] Resposta não é JSON."
            )

            log(
                texto_resposta[:2000]
            )

            return {}

        # ----------------------------------------------------
        # DEBUG seguro da resposta
        # ----------------------------------------------------

        if dados.get("errors"):

            log(
                "[SHOPEE API] GraphQL retornou erros:"
            )

            log(
                json.dumps(
                    dados.get("errors"),
                    ensure_ascii=False
                )[:5000]
            )

        if dados.get("data"):

            log(
                "[SHOPEE API] Campo data recebido."
            )

        # ----------------------------------------------------
        # Extrai item
        # ----------------------------------------------------

        data = dados.get(
            "data",
            {}
        )

        if not isinstance(
            data,
            dict
        ):
            data = {}

        item = data.get(
            "item"
        )

        if not item:

            # Algumas APIs podem devolver
            # estruturas diferentes. Mantemos
            # o corpo para diagnóstico.

            log(
                "[SHOPEE API] Nenhum item "
                "encontrado no campo data.item."
            )

            log(
                "[SHOPEE API] Resposta:"
            )

            log(
                json.dumps(
                    dados,
                    ensure_ascii=False
                )[:5000]
            )

            return {}

        log(
            "[SHOPEE API] Produto encontrado:"
        )

        log(
            str(
                item.get(
                    "title",
                    ""
                )
            )
        )

        return {

            "titulo":
                item.get(
                    "title",
                    ""
                ),

            "imagem":
                item.get(
                    "image",
                    ""
                ),

            "preco_atual":
                item.get(
                    "price",
                    ""
                ),

            "preco_antigo":
                item.get(
                    "originalPrice",
                    ""
                ),

            "descricao":
                item.get(
                    "description",
                    ""
                ),

            "url":
                item.get(
                    "url",
                    ""
                ),

            "shop_id":
                item.get(
                    "shopId",
                    shop_id
                ),

            "item_id":
                item.get(
                    "itemId",
                    item_id
                )
        }

    except Exception as erro:

        log(
            "[SHOPEE API] EXCEÇÃO:"
        )

        log(
            str(erro)
        )

        return {}


# ============================================================
# FORMATAR PREÇO
# ============================================================

def formatar_preco(valor):

    if valor is None:
        return ""

    if isinstance(
        valor,
        (int, float)
    ):

        return (
            "R$ "
            + f"{float(valor):,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    valor = str(valor).strip()

    if not valor:
        return ""

    if valor.startswith("R$"):
        return valor

    return "R$ " + valor


# ============================================================
# MONTAR PUBLICAÇÃO
# ============================================================

def montar_publicacao(
    produto,
    link_original
):

    titulo = (
        produto.get(
            "titulo",
            ""
        )
        or "Oferta Imperdível"
    ).strip()

    preco = formatar_preco(
        produto.get(
            "preco_atual",
            ""
        )
    )

    preco_antigo = formatar_preco(
        produto.get(
            "preco_antigo",
            ""
        )
    )

    linhas = []

    linhas.append(
        "🔥 OFERTA IMPERDÍVEL! 🔥"
    )

    linhas.append("")

    linhas.append(
        f"📦 {titulo}"
    )

    if preco:

        linhas.append("")

        if preco_antigo:

            linhas.append(
                f"💸 De: {preco_antigo}"
            )

        linhas.append(
            f"💰 Por: {preco}"
        )

    linhas.append("")

    linhas.append(
        "🚨 Corre porque essa oferta "
        "pode acabar a qualquer momento!"
    )

    linhas.append("")

    linhas.append(
        "👇 APROVEITE AGORA!"
    )

    linhas.append(
        link_original
    )

    linhas.append("")

    linhas.append(
        "🦊 Raposa Caçadora"
    )

    return "\n".join(linhas)


# ============================================================
# PROCESSAR PRODUTO
# ============================================================

def processar_produto(link):

    log("========================================")
    log("[PRODUTO] Abrindo link:")
    log(link)
    log("========================================")

    # --------------------------------------------------------
    # 1. Resolver URL
    # --------------------------------------------------------

    resolvido = resolver_link_shopee(
        link
    )

    url_final = resolvido.get(
        "url_final",
        link
    )

    html = resolvido.get(
        "html",
        ""
    )

    # --------------------------------------------------------
    # 2. NÃO usar o código curto como shopId/itemId
    # --------------------------------------------------------

    shop_id, item_id = (
        extrair_ids_produto(
            url_final
        )
    )

    # --------------------------------------------------------
    # 3. Se não encontrou na URL, tenta HTML
    # --------------------------------------------------------

    if (
        (not shop_id or not item_id)
        and html
    ):

        padroes_html = [

            r'"shopid"\s*:\s*(\d+).*?"itemid"\s*:\s*(\d+)',

            r'"shop_id"\s*:\s*(\d+).*?"item_id"\s*:\s*(\d+)',

            r'"shopId"\s*:\s*(\d+).*?"itemId"\s*:\s*(\d+)'
        ]

        for padrao in padroes_html:

            encontrado = re.search(
                padrao,
                html,
                flags=re.IGNORECASE
                | re.DOTALL
            )

            if encontrado:

                shop_id = (
                    encontrado.group(1)
                )

                item_id = (
                    encontrado.group(2)
                )

                log(
                    "[SHOPEE] IDs encontrados "
                    "no HTML:"
                )

                log(
                    f"[SHOPEE] shopId: "
                    f"{shop_id}"
                )

                log(
                    f"[SHOPEE] itemId: "
                    f"{item_id}"
                )

                break

    # --------------------------------------------------------
    # 4. Consultar API somente com IDs reais
    # --------------------------------------------------------

    produto_api = {}

    if shop_id and item_id:

        produto_api = consultar_shopee_api(
            shop_id,
            item_id
        )

    else:

        log(
            "[SHOPEE] Não foi possível obter "
            "shopId/itemId reais."
        )

        log(
            "[SHOPEE] A API não será chamada "
            "com IDs inventados."
        )

    # --------------------------------------------------------
    # 5. Fallback HTML
    # --------------------------------------------------------

    produto_html = {}

    if html:

        log(
            "[PRODUTO] HTML recebido: "
            f"{len(html)} bytes"
        )

        produto_html = extrair_dados_html(
            html,
            url_final
        )

    # --------------------------------------------------------
    # 6. API tem prioridade
    # --------------------------------------------------------

    produto = {

        "titulo":
            produto_api.get(
                "titulo"
            )
            or produto_html.get(
                "titulo",
                ""
            ),

        "imagem":
            produto_api.get(
                "imagem"
            )
            or produto_html.get(
                "imagem",
                ""
            ),

        "preco_atual":
            produto_api.get(
                "preco_atual"
            )
            or produto_html.get(
                "preco_atual",
                ""
            ),

        "preco_antigo":
            produto_api.get(
                "preco_antigo"
            )
            or produto_html.get(
                "preco_antigo",
                ""
            ),

        "descricao":
            produto_api.get(
                "descricao"
            )
            or produto_html.get(
                "descricao",
                ""
            ),

        "url":
            produto_api.get(
                "url"
            )
            or url_final
    }

    # --------------------------------------------------------
    # 7. Log final
    # --------------------------------------------------------

    log("========================================")
    log("[PRODUTO] Resultado final")
    log(
        f"[PRODUTO] Título: "
        f"{produto.get('titulo', '')}"
    )
    log(
        f"[PRODUTO] Preço atual: "
        f"{produto.get('preco_atual', '')}"
    )
    log(
        f"[PRODUTO] Preço antigo: "
        f"{produto.get('preco_antigo', '')}"
    )
    log(
        f"[PRODUTO] Imagem: "
        f"{produto.get('imagem', '')}"
    )
    log("========================================")

    return produto


# ============================================================
# TASK
# ============================================================

def executar_tarefa(
    task_id,
    link
):

    try:

        with tarefas_lock:

            tarefas[task_id] = {
                "status": "processando",
                "mensagem":
                    "Processando produto..."
            }

        log(
            f"[TASK] Iniciando {task_id}"
        )

        produto = processar_produto(
            link
        )

        legenda = montar_publicacao(
            produto,
            link
        )

        imagem = produto.get(
            "imagem",
            ""
        )

        if imagem:

            resultado_telegram = (
                telegram_enviar_foto(
                    imagem,
                    legenda
                )
            )

        else:

            log(
                "[TELEGRAM] Produto sem imagem. "
                "Enviando mensagem."
            )

            resultado_telegram = (
                telegram_enviar_mensagem(
                    legenda
                )
            )

        if resultado_telegram.get(
            "ok"
        ):

            log(
                "[TELEGRAM] Produto publicado."
            )

            with tarefas_lock:

                tarefas[task_id] = {

                    "status":
                        "concluido",

                    "mensagem":
                        "Produto publicado.",

                    "produto":
                        produto,

                    "telegram":
                        {
                            "ok":
                                True
                        }
                }

        else:

            erro = (
                resultado_telegram.get(
                    "erro"
                )
                or resultado_telegram.get(
                    "description"
                )
                or "Erro desconhecido no Telegram."
            )

            log(
                "[TELEGRAM] ERRO: "
                + str(erro)
            )

            with tarefas_lock:

                tarefas[task_id] = {

                    "status":
                        "erro",

                    "mensagem":
                        str(erro),

                    "produto":
                        produto,

                    "telegram":
                        resultado_telegram
                }

        log(
            f"[TASK] Finalizada {task_id}"
        )

    except Exception as erro:

        log(
            f"[TASK] ERRO {task_id}: "
            f"{erro}"
        )

        with tarefas_lock:

            tarefas[task_id] = {

                "status":
                    "erro",

                "mensagem":
                    str(erro)
            }


# ============================================================
# CONFIGURAR / PROCESSAR
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    try:

        dados = request.get_json(
            silent=True
        ) or {}

        link = (
            dados.get("link")
            or dados.get("url")
            or ""
        ).strip()

        if not link:

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "Informe um link da Shopee."
            }), 400

        # ----------------------------------------------------
        # Aceita também lista de links
        # ----------------------------------------------------

        links = dados.get(
            "links"
        )

        if isinstance(
            links,
            list
        ):

            links = [

                str(x).strip()

                for x in links

                if str(x).strip()
            ]

        else:

            links = [link]

        if len(links) > MAX_LINKS:

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    f"Máximo de {MAX_LINKS} links."
            }), 400

        task_ids = []

        for item_link in links:

            task_id = str(
                uuid.uuid4()
            )

            with tarefas_lock:

                tarefas[task_id] = {

                    "status":
                        "fila",

                    "mensagem":
                        "Aguardando processamento.",

                    "link":
                        item_link
                }

            thread = threading.Thread(
                target=executar_tarefa,
                args=(
                    task_id,
                    item_link
                ),
                daemon=True
            )

            thread.start()

            task_ids.append(
                task_id
            )

        # ----------------------------------------------------
        # Compatibilidade com frontend antigo
        # ----------------------------------------------------

        return jsonify({

            "sucesso":
                True,

            "status":
                "processando",

            "task_id":
                task_ids[0],

            "task_ids":
                task_ids,

            "mensagem":
                "Produto enviado para processamento."
        })

    except Exception as erro:

        log(
            "[API] Erro /api/configurar:"
        )

        log(
            str(erro)
        )

        return jsonify({

            "sucesso":
                False,

            "erro":
                str(erro)
        }), 500


# ============================================================
# STATUS
# ============================================================

@app.route(
    "/api/status/<task_id>",
    methods=["GET"]
)
def status_tarefa(task_id):

    with tarefas_lock:

        tarefa = tarefas.get(
            task_id
        )

    if not tarefa:

        return jsonify({

            "status":
                "nao_encontrado",

            "mensagem":
                "Tarefa não encontrada."
        }), 404

    return jsonify(
        tarefa
    )


# ============================================================
# TESTE MANUAL SHOPEE
# ============================================================

@app.route(
    "/debug-shopee-produto",
    methods=["GET"]
)
def debug_shopee_produto():

    link = (
        request.args.get(
            "url"
        )
        or request.args.get(
            "link"
        )
        or ""
    ).strip()

    if not link:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "Use ?url=LINK_DA_SHOPEE"
        }), 400

    produto = processar_produto(
        link
    )

    return jsonify({

        "sucesso":
            True,

        "produto":
            produto,

        "link_original":
            link,

        "timestamp":
            int(time.time())
    })


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
# TESTE
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
                and
                os.environ.get(
                    "SHOPEE_API_URL",
                    ""
                ).strip()
            ),

        "timestamp":
            int(time.time())
    })


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
