import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re

from urllib.parse import parse_qsl, urlparse

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

SHOPEE_APP_ID = os.environ.get(
    "SHOPEE_APP_ID",
    ""
).strip()

SHOPEE_SECRET = os.environ.get(
    "SHOPEE_SECRET",
    ""
).strip()

# Endpoint GraphQL da API da Shopee.
# Se a documentação da sua conta fornecer outro endpoint,
# coloque-o em SHOPEE_GRAPHQL_URL no Render.
SHOPEE_GRAPHQL_URL = os.environ.get(
    "SHOPEE_GRAPHQL_URL",
    "https://open-api.shopee.com/graphql"
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
# FUNÇÕES DE TEXTO
# ============================================================

def limpar_texto(texto):

    if not texto:
        return ""

    texto = re.sub(
        r"\s+",
        " ",
        str(texto)
    )

    return texto.strip()


def formatar_preco(valor):

    if valor is None:
        return ""

    valor = str(valor).strip()

    if not valor:
        return ""

    valor = (
        valor
        .replace("R$", "")
        .replace("BRL", "")
        .strip()
    )

    # Caso venha como número brasileiro:
    # 1.234,56
    if "," in valor:

        valor = valor.replace(
            ".",
            ""
        )

        valor = valor.replace(
            ",",
            "."
        )

    try:

        numero = float(valor)

        return (
            "R$ "
            + f"{numero:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except Exception:

        return ""


def converter_preco_float(preco_str):

    if not preco_str:
        return 0.0

    try:

        limpo = (
            str(preco_str)
            .replace("R$", "")
            .replace("BRL", "")
            .replace(" ", "")
        )

        if "," in limpo:

            limpo = (
                limpo
                .replace(".", "")
                .replace(",", ".")
            )

        return float(limpo)

    except Exception:

        return 0.0


# ============================================================
# EXTRAÇÃO JSON-LD
# ============================================================

def extrair_preco_schema(soup):

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        try:

            conteudo = script.string

            if not conteudo:
                continue

            dados = json.loads(
                conteudo
            )

            blocos = []

            if isinstance(
                dados,
                list
            ):

                blocos.extend(
                    dados
                )

            elif isinstance(
                dados,
                dict
            ):

                blocos.append(
                    dados
                )

                if isinstance(
                    dados.get("@graph"),
                    list
                ):

                    blocos.extend(
                        dados["@graph"]
                    )

            for bloco in blocos:

                if not isinstance(
                    bloco,
                    dict
                ):
                    continue

                offers = bloco.get(
                    "offers"
                )

                if isinstance(
                    offers,
                    list
                ):

                    offers = (
                        offers[0]
                        if offers
                        else None
                    )

                if isinstance(
                    offers,
                    dict
                ):

                    preco = (
                        offers.get("price")
                        or
                        offers.get("lowPrice")
                    )

                    if preco:

                        resultado = (
                            formatar_preco(
                                preco
                            )
                        )

                        if resultado:
                            return resultado

        except Exception:

            continue

    return ""


# ============================================================
# EXTRAÇÃO DE IDs SHOPEE
# ============================================================

def extrair_ids_shopee(url):

    """
    Recebe uma URL Shopee, inclusive link curto
    s.shopee.com.br, resolve o redirecionamento e
    tenta encontrar shopId/itemId.

    Retorna:

    {
        "url_original": ...,
        "url_final": ...,
        "shop_id": ...,
        "item_id": ...
    }
    """

    print(
        "[SHOPEE] Tentando resolver URL:"
    )

    print(url)

    headers = {

        "User-Agent":
            "Mozilla/5.0 (Linux; Android 15) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0.0.0 Mobile Safari/537.36",

        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8",

        "Accept-Language":
            "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:

        resposta = requests.get(
            url,
            headers=headers,
            timeout=30,
            allow_redirects=True
        )

        print(
            "[SHOPEE] HTTP:",
            resposta.status_code
        )

        print(
            "[SHOPEE] URL final HTTP:",
            resposta.url
        )

        url_final = resposta.url

        parsed = urlparse(
            url_final
        )

        partes = [
            p
            for p in parsed.path.split("/")
            if p
        ]

        shop_id = ""
        item_id = ""

        # Formato:
        # /loja/item
        #
        # ou:
        # /nome-da-loja/shopId/itemId
        #
        # Exemplo descoberto no seu caso:
        # /opaanlp/217896078/58202483323

        numeros = re.findall(
            r"\d+",
            parsed.path
        )

        if len(numeros) >= 2:

            shop_id = numeros[-2]
            item_id = numeros[-1]

        # Procura também no HTML.
        if (
            not shop_id
            or
            not item_id
        ):

            html = resposta.text

            padroes = [

                r'"shopid"\s*:\s*(\d+).*?"itemid"\s*:\s*(\d+)',

                r'"shopId"\s*:\s*(\d+).*?"itemId"\s*:\s*(\d+)',

                r'"shop_id"\s*:\s*(\d+).*?"item_id"\s*:\s*(\d+)'
            ]

            for padrao in padroes:

                encontrado = re.search(
                    padrao,
                    html,
                    re.I | re.S
                )

                if encontrado:

                    shop_id = (
                        shop_id
                        or
                        encontrado.group(1)
                    )

                    item_id = (
                        item_id
                        or
                        encontrado.group(2)
                    )

                    break

        print(
            "[SHOPEE] IDs encontrados via HTTP:",
            shop_id,
            item_id
        )

        return {

            "sucesso":
                True,

            "url_final":
                url_final,

            "shop_id":
                shop_id,

            "item_id":
                item_id
        }

    except Exception as erro:

        print(
            "[SHOPEE] Erro ao resolver URL:",
            erro
        )

        return {

            "sucesso":
                False,

            "erro":
                str(erro)
        }


# ============================================================
# SHOPEE GRAPHQL
# ============================================================

def shopee_graphql_produto(
    shop_id,
    item_id
):

    """
    Faz a chamada GraphQL para a API da Shopee.

    IMPORTANTE:
    O corpo da resposta é impresso para diagnóstico,
    mas AppID, Secret e assinatura nunca são impressos.
    """

    app_id = os.environ.get(
        "SHOPEE_APP_ID",
        ""
    ).strip()

    secret = os.environ.get(
        "SHOPEE_SECRET",
        ""
    ).strip()

    endpoint = os.environ.get(
        "SHOPEE_GRAPHQL_URL",
        "https://open-api.shopee.com/graphql"
    ).strip()

    if not app_id:

        print(
            "[SHOPEE API] ERRO: SHOPEE_APP_ID não configurado."
        )

        return {

            "sucesso":
                False,

            "erro":
                "SHOPEE_APP_ID não configurado."
        }

    if not secret:

        print(
            "[SHOPEE API] ERRO: SHOPEE_SECRET não configurado."
        )

        return {

            "sucesso":
                False,

            "erro":
                "SHOPEE_SECRET não configurado."
        }

    if not shop_id or not item_id:

        return {

            "sucesso":
                False,

            "erro":
                "shopId ou itemId não encontrados."
        }

    # ========================================================
    # QUERY
    # ========================================================
    #
    # ESTA QUERY É DE DIAGNÓSTICO.
    #
    # A API da Shopee pode utilizar nomes de campos diferentes
    # conforme o produto/API habilitada na conta.
    #
    # Por isso a resposta completa será mostrada no log.
    #

    query = """
    query ProductInfo($shopId: Int!, $itemId: Int!) {
        productOffer(shopId: $shopId, itemId: $itemId) {
            itemId
            shopId
            title
            image
            price
            originalPrice
        }
    }
    """

    variables = {

        "shopId":
            int(shop_id),

        "itemId":
            int(item_id)
    }

    body = {

        "query":
            query,

        "variables":
            variables
    }

    # ========================================================
    # ASSINATURA
    # ========================================================
    #
    # NÃO imprimir secret nem assinatura.
    #

    timestamp = int(
        time.time()
    )

    # Mantemos uma assinatura baseada nos dados enviados.
    # A resposta da API dirá se o endpoint/query precisa
    # de outro esquema de assinatura.
    assinatura_base = (
        f"{app_id}"
        f"{timestamp}"
        f"{json.dumps(body, separators=(',', ':'))}"
    )

    assinatura = hmac.new(

        secret.encode(
            "utf-8"
        ),

        assinatura_base.encode(
            "utf-8"
        ),

        hashlib.sha256

    ).hexdigest()

    headers = {

        "Content-Type":
            "application/json",

        "Accept":
            "application/json",

        "X-Shopee-App-Id":
            app_id,

        "X-Shopee-Timestamp":
            str(timestamp),

        "X-Shopee-Signature":
            assinatura
    }

    print(
        "[SHOPEE API] Enviando GraphQL..."
    )

    print(
        "[SHOPEE API] Endpoint:",
        endpoint
    )

    print(
        "[SHOPEE API] shopId:",
        shop_id
    )

    print(
        "[SHOPEE API] itemId:",
        item_id
    )

    try:

        resposta = requests.post(

            endpoint,

            json=body,

            headers=headers,

            timeout=30
        )

        # ====================================================
        # STATUS HTTP
        # ====================================================

        print(
            "[SHOPEE API] HTTP:",
            resposta.status_code
        )

        # ====================================================
        # RESPOSTA REAL DA SHOPEE
        # ====================================================

        try:

            resposta_json = (
                resposta.json()
            )

            print(
                "[SHOPEE API] RESPOSTA:",
                json.dumps(
                    resposta_json,
                    ensure_ascii=False
                )[:10000]
            )

        except Exception:

            print(
                "[SHOPEE API] RESPOSTA TEXTO:",
                resposta.text[:10000]
            )

            return {

                "sucesso":
                    False,

                "erro":
                    "A Shopee não retornou JSON.",

                "http":
                    resposta.status_code,

                "texto":
                    resposta.text[:10000]
            }

        # ====================================================
        # ERROS GRAPHQL
        # ====================================================

        if resposta_json.get("errors"):

            print(
                "[SHOPEE API] ERROS GRAPHQL:"
            )

            print(
                json.dumps(
                    resposta_json.get(
                        "errors"
                    ),
                    ensure_ascii=False
                )[:10000]
            )

            return {

                "sucesso":
                    False,

                "erro":
                    "A API GraphQL retornou erros.",

                "http":
                    resposta.status_code,

                "errors":
                    resposta_json.get(
                        "errors"
                    ),

                "resposta":
                    resposta_json
            }

        # ====================================================
        # DADOS
        # ====================================================

        dados = resposta_json.get(
            "data"
        )

        if not dados:

            return {

                "sucesso":
                    False,

                "erro":
                    "A API respondeu, mas não retornou data.",

                "http":
                    resposta.status_code,

                "resposta":
                    resposta_json
            }

        produto = (
            dados.get(
                "productOffer"
            )
        )

        if not produto:

            print(
                "[SHOPEE API] Campo productOffer não encontrado."
            )

            return {

                "sucesso":
                    False,

                "erro":
                    "Produto não encontrado no retorno GraphQL.",

                "http":
                    resposta.status_code,

                "resposta":
                    resposta_json
            }

        return {

            "sucesso":
                True,

            "produto":
                produto,

            "resposta":
                resposta_json
        }

    except requests.RequestException as erro:

        print(
            "[SHOPEE API] Erro de conexão:",
            erro
        )

        return {

            "sucesso":
                False,

            "erro":
                str(erro)
        }

    except Exception as erro:

        print(
            "[SHOPEE API] Erro:",
            erro
        )

        return {

            "sucesso":
                False,

            "erro":
                str(erro)
        }


# ============================================================
# EXTRAÇÃO DE PRODUTO
# ============================================================

def extrair_dados_produto(
    link
):

    print(
        "========================================"
    )

    print(
        "[PRODUTO] Abrindo link:"
    )

    print(link)

    print(
        "========================================"
    )

    # ========================================================
    # RESOLVE LINK
    # ========================================================

    ids = extrair_ids_shopee(
        link
    )

    if not ids.get("sucesso"):

        return {

            "sucesso":
                False,

            "erro":
                ids.get(
                    "erro",
                    "Não foi possível resolver o link Shopee."
                )
        }

    url_final = ids.get(
        "url_final",
        link
    )

    shop_id = ids.get(
        "shop_id"
    )

    item_id = ids.get(
        "item_id"
    )

    print(
        "[PRODUTO] URL final:"
    )

    print(url_final)

    print(
        "[PRODUTO] shopId:",
        shop_id
    )

    print(
        "[PRODUTO] itemId:",
        item_id
    )

    # ========================================================
    # API SHOPEE
    # ========================================================

    api_resultado = shopee_graphql_produto(

        shop_id,

        item_id
    )

    if api_resultado.get(
        "sucesso"
    ):

        produto = api_resultado.get(
            "produto",
            {}
        )

        titulo = limpar_texto(
            produto.get(
                "title"
            )
            or
            produto.get(
                "name"
            )
            or
            ""
        )

        preco_atual = formatar_preco(
            produto.get(
                "price"
            )
            or
            produto.get(
                "currentPrice"
            )
            or
            ""
        )

        preco_antigo = formatar_preco(
            produto.get(
                "originalPrice"
            )
            or
            produto.get(
                "oldPrice"
            )
            or
            ""
        )

        imagem = (
            produto.get(
                "image"
            )
            or
            produto.get(
                "imageUrl"
            )
            or
            ""
        )

        # Alguns retornos podem trazer uma lista
        # de imagens.
        if (
            not imagem
            and
            isinstance(
                produto.get("images"),
                list
            )
        ):

            imagens = produto.get(
                "images"
            )

            if imagens:

                imagem = str(
                    imagens[0]
                )

        print(
            "[PRODUTO] Dados retornados pela API:"
        )

        print(
            "[PRODUTO] Título:",
            titulo
        )

        print(
            "[PRODUTO] Preço atual:",
            preco_atual
        )

        print(
            "[PRODUTO] Preço antigo:",
            preco_antigo
        )

        print(
            "[PRODUTO] Imagem:",
            imagem
        )

        if (
            titulo
            or
            preco_atual
            or
            imagem
        ):

            return {

                "sucesso":
                    True,

                "titulo":
                    titulo
                    or
                    "Oferta Imperdível",

                "preco_atual":
                    preco_atual,

                "preco_antigo":
                    preco_antigo,

                "imagem":
                    imagem,

                "link":
                    link,

                "url_final":
                    url_final,

                "shop_id":
                    shop_id,

                "item_id":
                    item_id
            }

    # ========================================================
    # FALLBACK HTTP
    # ========================================================

    print(
        "[PRODUTO] API não forneceu dados completos."
    )

    print(
        "[PRODUTO] Tentando fallback HTML..."
    )

    headers = {

        "User-Agent":
            "Mozilla/5.0 (Linux; Android 15) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0.7922.199 Mobile Safari/537.36",

        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8",

        "Accept-Language":
            "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache"
    }

    try:

        resposta = requests.get(

            url_final,

            headers=headers,

            timeout=30,

            allow_redirects=True
        )

        print(
            "[PRODUTO] HTTP fallback:",
            resposta.status_code
        )

        print(
            "[PRODUTO] HTML recebido:",
            len(resposta.text),
            "bytes"
        )

        soup = BeautifulSoup(
            resposta.text,
            "html.parser"
        )

        # ====================================================
        # TÍTULO
        # ====================================================

        titulo = ""

        elemento = soup.find(
            "h1"
        )

        if elemento:

            titulo = limpar_texto(
                elemento.get_text(
                    " ",
                    strip=True
                )
            )

        if not titulo:

            meta = soup.find(
                "meta",
                property="og:title"
            )

            if meta:

                titulo = limpar_texto(
                    meta.get(
                        "content",
                        ""
                    )
                )

        if not titulo:

            meta = soup.find(
                "meta",
                attrs={
                    "name":
                        "twitter:title"
                }
            )

            if meta:

                titulo = limpar_texto(
                    meta.get(
                        "content",
                        ""
                    )
                )

        # ====================================================
        # IMAGEM
        # ====================================================

        imagem = ""

        meta = soup.find(
            "meta",
            property="og:image"
        )

        if meta:

            imagem = (
                meta.get(
                    "content",
                    ""
                )
                .strip()
            )

        if not imagem:

            meta = soup.find(
                "meta",
                attrs={
                    "name":
                        "twitter:image"
                }
            )

            if meta:

                imagem = (
                    meta.get(
                        "content",
                        ""
                    )
                    .strip()
                )

        # ====================================================
        # PREÇO
        # ====================================================

        preco_atual = (
            extrair_preco_schema(
                soup
            )
        )

        # ====================================================
        # RESULTADO
        # ====================================================

        print(
            "[PRODUTO] ========================================"
        )

        print(
            "[PRODUTO] Título:",
            titulo
        )

        print(
            "[PRODUTO] Preço atual:",
            preco_atual
        )

        print(
            "[PRODUTO] Preço antigo:"
        )

        print(
            "[PRODUTO] Imagem:",
            imagem
        )

        print(
            "[PRODUTO] ========================================"
        )

        return {

            "sucesso":
                True,

            "titulo":
                titulo
                or
                "Oferta Imperdível",

            "preco_atual":
                preco_atual,

            "preco_antigo":
                "",

            "imagem":
                imagem,

            "link":
                link,

            "url_final":
                url_final,

            "shop_id":
                shop_id,

            "item_id":
                item_id
        }

    except Exception as erro:

        print(
            "[PRODUTO] Erro fallback:",
            erro
        )

        return {

            "sucesso":
                False,

            "erro":
                str(erro)
        }


# ============================================================
# SHOPEE VALIDAÇÃO
# ============================================================

def link_shopee_valido(link):

    if not isinstance(
        link,
        str
    ):
        return False

    link = link.strip()

    if not link:
        return False

    link_lower = link.lower()

    if not (
        link_lower.startswith(
            "http://"
        )
        or
        link_lower.startswith(
            "https://"
        )
    ):

        return False

    return (
        "shopee." in link_lower
        or
        "shopee" in link_lower
    )


# ============================================================
# TELEGRAM - MENSAGEM
# ============================================================

def telegram_enviar_mensagem(
    texto,
    canal,
    reply_markup=None
):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {

            "ok":
                False,

            "erro":
                "BOT_TOKEN não está disponível."
        }

    if not canal:

        return {

            "ok":
                False,

            "erro":
                "CHANNEL_USERNAME não configurado."
        }

    try:

        payload = {

            "chat_id":
                canal,

            "text":
                texto,

            "parse_mode":
                "HTML",

            "disable_web_page_preview":
                True
        }

        if reply_markup:

            payload[
                "reply_markup"
            ] = reply_markup

        resposta = requests.post(

            telegram_api_url(
                "sendMessage"
            ),

            json=payload,

            timeout=30
        )

        try:

            return resposta.json()

        except Exception:

            return {

                "ok":
                    False,

                "erro":
                    f"Telegram retornou HTTP "
                    f"{resposta.status_code}"
            }

    except Exception as erro:

        return {

            "ok":
                False,

            "erro":
                str(erro)
        }


# ============================================================
# TELEGRAM - FOTO
# ============================================================

def telegram_enviar_foto(
    foto,
    legenda,
    canal,
    reply_markup=None
):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {

            "ok":
                False,

            "erro":
                "BOT_TOKEN não está disponível."
        }

    try:

        print(
            "[TELEGRAM] Baixando imagem:"
        )

        print(foto)

        imagem_resposta = requests.get(

            foto,

            timeout=30,

            headers={
                "User-Agent":
                    "Mozilla/5.0"
            }
        )

        print(
            "[TELEGRAM] HTTP imagem:",
            imagem_resposta.status_code
        )

        if imagem_resposta.status_code != 200:

            return {

                "ok":
                    False,

                "erro":
                    "Não foi possível baixar a imagem."
            }

        payload = {

            "chat_id":
                canal,

            "caption":
                legenda,

            "parse_mode":
                "HTML"
        }

        if reply_markup:

            payload[
                "reply_markup"
            ] = json.dumps(
                reply_markup
            )

        resposta = requests.post(

            telegram_api_url(
                "sendPhoto"
            ),

            data=payload,

            files={
                "photo":
                    (
                        "produto.jpg",
                        imagem_resposta.content,
                        imagem_resposta.headers.get(
                            "Content-Type",
                            "image/jpeg"
                        )
                    )
            },

            timeout=40
        )

        try:

            return resposta.json()

        except Exception:

            return {

                "ok":
                    False,

                "erro":
                    f"Telegram retornou HTTP "
                    f"{resposta.status_code}"
            }

    except Exception as erro:

        print(
            "[TELEGRAM] Erro ao enviar foto:",
            erro
        )

        return {

            "ok":
                False,

            "erro":
                str(erro)
        }


# ============================================================
# PUBLICAÇÃO
# ============================================================

def publicar_produto(
    link,
    usuario
):

    canal = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()

    if not canal:

        return {

            "sucesso":
                False,

            "mensagem":
                "CHANNEL_USERNAME não configurado."
        }

    print(
        "========================================"
    )

    print(
        "[TELEGRAM] Processando produto"
    )

    print(
        "[TELEGRAM] Usuário:",
        usuario
    )

    print(
        "[TELEGRAM] Canal:",
        canal
    )

    print(
        "[TELEGRAM] Link:",
        link
    )

    print(
        "========================================"
    )

    dados = extrair_dados_produto(
        link
    )

    if not dados.get(
        "sucesso"
    ):

        return {

            "sucesso":
                False,

            "mensagem":
                dados.get(
                    "erro",
                    "Não foi possível obter os dados do produto."
                )
        }

    titulo = dados.get(
        "titulo",
        "Oferta Imperdível"
    )

    preco_atual = dados.get(
        "preco_atual",
        ""
    )

    preco_antigo = dados.get(
        "preco_antigo",
        ""
    )

    foto_url = dados.get(
        "imagem",
        ""
    )

    # ========================================================
    # PREÇO
    # ========================================================

    valor_atual = converter_preco_float(
        preco_atual
    )

    valor_antigo = converter_preco_float(
        preco_antigo
    )

    if (
        preco_antigo
        and
        valor_antigo > valor_atual
        and
        valor_atual > 0
    ):

        bloco_preco = (

            f"💰 <s>De: {preco_antigo}</s>\n"

            f"🔥 <b>POR APENAS: "
            f"{preco_atual}</b>"
        )

    elif preco_atual:

        bloco_preco = (

            f"💰 <b>POR APENAS: "
            f"{preco_atual}</b>"
        )

    else:

        bloco_preco = (
            "💰 <b>Confira o preço da oferta</b>"
        )

    # ========================================================
    # LEGENDA
    # ========================================================

    legenda = (

        "🔥 <b>OFERTA IMPERDÍVEL!</b> 🔥\n\n"

        f"📦 <b>{titulo}</b>\n\n"

        f"{bloco_preco}\n\n"

        "🚨 <b>Corre porque essa oferta "
        "pode acabar a qualquer momento!</b>\n\n"

        "👇 <b>APROVEITE AGORA!</b>\n\n"

        "🦊 <b>Raposa Caçadora</b>"
    )

    # ========================================================
    # BOTÃO
    # ========================================================

    reply_markup = {

        "inline_keyboard": [

            [

                {

                    "text":
                        "🛒 COMPRAR AGORA",

                    "url":
                        link
                }

            ]

        ]
    }

    # ========================================================
    # ENVIA FOTO
    # ========================================================

    if (
        foto_url
        and
        str(foto_url).startswith(
            "http"
        )
    ):

        resultado = telegram_enviar_foto(

            foto=foto_url,

            legenda=legenda,

            canal=canal,

            reply_markup=reply_markup
        )

    else:

        resultado = telegram_enviar_mensagem(

            texto=legenda,

            canal=canal,

            reply_markup=reply_markup
        )

    # ========================================================
    # RESULTADO
    # ========================================================

    if not resultado.get(
        "ok"
    ):

        erro = (

            resultado.get(
                "description"
            )

            or

            resultado.get(
                "erro"
            )

            or

            "Erro desconhecido do Telegram."
        )

        print(
            "[TELEGRAM] ERRO:",
            erro
        )

        return {

            "sucesso":
                False,

            "mensagem":
                erro
        }

    mensagem_telegram = (
        resultado.get(
            "result",
            {}
        )
    )

    message_id = (
        mensagem_telegram.get(
            "message_id"
        )
    )

    print(
        "[TELEGRAM] Produto publicado:",
        message_id
    )

    return {

        "sucesso":
            True,

        "mensagem":
            "Produto publicado no canal.",

        "message_id":
            message_id,

        "titulo":
            titulo,

        "preco_atual":
            preco_atual,

        "preco_antigo":
            preco_antigo,

        "imagem":
            foto_url
    }


# ============================================================
# TAREFA
# ============================================================

def criar_tarefa(
    links,
    intervalo,
    quantidade,
    usuario
):

    task_id = str(
        uuid.uuid4()
    )

    tarefa = {

        "id":
            task_id,

        "usuario":
            usuario,

        "links":
            links,

        "intervalo":
            intervalo,

        "quantidade":
            quantidade,

        "produto_atual":
            0,

        "produto_link":
            "",

        "progresso":
            0,

        "status":
            "iniciando",

        "cancelada":
            False,

        "resultados":
            [],

        "criada_em":
            time.time()
    }

    with tarefas_lock:

        tarefas[
            task_id
        ] = tarefa

    return task_id


# ============================================================
# WORKER
# ============================================================

def executar_tarefa(
    task_id
):

    print(
        f"[TASK] Iniciando {task_id}"
    )

    while True:

        with tarefas_lock:

            tarefa = tarefas.get(
                task_id
            )

            if not tarefa:
                return

            if tarefa[
                "cancelada"
            ]:

                tarefa[
                    "status"
                ] = "cancelada"

                return

            indice = tarefa[
                "produto_atual"
            ]

            links = list(
                tarefa[
                    "links"
                ]
            )

            quantidade = tarefa[
                "quantidade"
            ]

            usuario = tarefa[
                "usuario"
            ]

            intervalo = tarefa[
                "intervalo"
            ]

        if indice >= quantidade:

            with tarefas_lock:

                tarefa = tarefas.get(
                    task_id
                )

                if tarefa:

                    tarefa[
                        "status"
                    ] = "concluida"

                    tarefa[
                        "progresso"
                    ] = 100

                    tarefa[
                        "produto_atual"
                    ] = quantidade

                    tarefa[
                        "produto_link"
                    ] = ""

            return

        link = links[
            indice
        ]

        numero_produto = (
            indice + 1
        )

        with tarefas_lock:

            tarefa = tarefas.get(
                task_id
            )

            if not tarefa:
                return

            tarefa[
                "status"
            ] = "processando"

            tarefa[
                "produto_link"
            ] = link

            tarefa[
                "progresso"
            ] = round(
                (
                    indice
                    /
                    quantidade
                )
                *
                100
            )

        try:

            resultado = publicar_produto(

                link,

                usuario
            )

            sucesso = resultado.get(
                "sucesso",
                False
            )

        except Exception as erro:

            print(
                "[PUBLICAÇÃO] Erro:",
                erro
            )

            sucesso = False

            resultado = {

                "mensagem":
                    str(erro)
            }

        with tarefas_lock:

            tarefa = tarefas.get(
                task_id
            )

            if not tarefa:
                return

            if tarefa[
                "cancelada"
            ]:

                tarefa[
                    "status"
                ] = "cancelada"

                return

            if sucesso:

                tarefa[
                    "resultados"
                ].append({

                    "produto":
                        numero_produto,

                    "link":
                        link,

                    "status":
                        "postado",

                    "message_id":
                        resultado.get(
                            "message_id"
                        ),

                    "titulo":
                        resultado.get(
                            "titulo"
                        ),

                    "preco_atual":
                        resultado.get(
                            "preco_atual"
                        ),

                    "preco_antigo":
                        resultado.get(
                            "preco_antigo"
                        )
                })

                tarefa[
                    "produto_atual"
                ] = numero_produto

                tarefa[
                    "progresso"
                ] = round(
                    (
                        numero_produto
                        /
                        quantidade
                    )
                    *
                    100
                )

                tarefa[
                    "status"
                ] = "aguardando"

            else:

                tarefa[
                    "resultados"
                ].append({

                    "produto":
                        numero_produto,

                    "link":
                        link,

                    "status":
                        "erro",

                    "mensagem":
                        resultado.get(
                            "mensagem",
                            "Erro desconhecido."
                        )
                })

                tarefa[
                    "produto_atual"
                ] = numero_produto

                tarefa[
                    "progresso"
                ] = round(
                    (
                        numero_produto
                        /
                        quantidade
                    )
                    *
                    100
                )

                tarefa[
                    "status"
                ] = "erro"

        if not sucesso:

            time.sleep(
                1
            )

            continue

        if numero_produto >= quantidade:

            with tarefas_lock:

                tarefa = tarefas.get(
                    task_id
                )

                if tarefa:

                    tarefa[
                        "status"
                    ] = "concluida"

                    tarefa[
                        "progresso"
                    ] = 100

                    tarefa[
                        "produto_link"
                    ] = ""

            print(
                f"[TASK] Finalizada {task_id}"
            )

            return

        with tarefas_lock:

            tarefa = tarefas.get(
                task_id
            )

            if tarefa:

                tarefa[
                    "status"
                ] = "aguardando"

        segundos_restantes = intervalo

        while segundos_restantes > 0:

            with tarefas_lock:

                tarefa = tarefas.get(
                    task_id
                )

                if not tarefa:
                    return

                if tarefa[
                    "cancelada"
                ]:

                    tarefa[
                        "status"
                    ] = "cancelada"

                    return

            time.sleep(
                1
            )

            segundos_restantes -= 1


# ============================================================
# PÁGINA
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
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

    channel = os.environ.get(
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

    return jsonify({

        "status":
            "ok",

        "service":
            "raposa-cacadora",

        "telegram_configurado":
            bool(token),

        "canal_configurado":
            bool(channel),

        "shopee_app_id_configurado":
            bool(app_id),

        "shopee_secret_configurado":
            bool(secret),

        "shopee_graphql_configurado":
            bool(
                app_id
                and
                secret
            ),

        "timestamp":
            int(time.time())
    })


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

        "BOT_TOKEN_existe":
            bool(token),

        "BOT_TOKEN_tamanho":
            len(token),

        "CHANNEL_USERNAME":
            canal,

        "CHANNEL_USERNAME_existe":
            bool(canal),

        "telegram_api_ok":
            resultado.get(
                "ok",
                False
            ),

        "bot":
            bot,

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
# DEBUG ENV
# ============================================================

@app.route(
    "/debug-env",
    methods=["GET"]
)
def debug_env():

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    )

    channel = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    )

    app_id = os.environ.get(
        "SHOPEE_APP_ID",
        ""
    )

    secret = os.environ.get(
        "SHOPEE_SECRET",
        ""
    )

    return jsonify({

        "BOT_TOKEN_existe":
            bool(token),

        "BOT_TOKEN_tamanho":
            len(token),

        "CHANNEL_USERNAME_existe":
            bool(channel),

        "CHANNEL_USERNAME":
            channel,

        "SHOPEE_APP_ID_existe":
            bool(app_id),

        "SHOPEE_APP_ID_tamanho":
            len(app_id),

        "SHOPEE_SECRET_existe":
            bool(secret),

        "SHOPEE_SECRET_tamanho":
            len(secret),

        "SHOPEE_GRAPHQL_URL":
            os.environ.get(
                "SHOPEE_GRAPHQL_URL",
                ""
            ),

        "PORT":
            os.environ.get(
                "PORT",
                ""
            )
    })


# ============================================================
# TELEGRAM INIT DATA
# ============================================================

def validar_init_data(
    init_data
):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:
        return False

    if not init_data:
        return False

    try:

        dados = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        hash_recebido = dados.pop(
            "hash",
            None
        )

        if not hash_recebido:
            return False

        data_check_string = "\n".join(

            f"{chave}={valor}"

            for chave, valor
            in sorted(
                dados.items()
            )
        )

        secret_key = hmac.new(

            b"WebAppData",

            token.encode(
                "utf-8"
            ),

            hashlib.sha256

        ).digest()

        hash_calculado = hmac.new(

            secret_key,

            data_check_string.encode(
                "utf-8"
            ),

            hashlib.sha256

        ).hexdigest()

        return hmac.compare_digest(

            hash_calculado,

            hash_recebido
        )

    except Exception as erro:

        print(
            "[TELEGRAM] Erro initData:",
            erro
        )

        return False


def obter_usuario(
    init_data
):

    if not init_data:
        return None

    try:

        dados = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        usuario = dados.get(
            "user"
        )

        if not usuario:
            return None

        return json.loads(
            usuario
        )

    except Exception as erro:

        print(
            "[TELEGRAM] Erro usuário:",
            erro
        )

        return None


# ============================================================
# CONFIGURAR
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    try:

        dados = request.get_json(
            silent=True
        )

        if not dados:

            return jsonify({

                "erro":
                    "JSON inválido."
            }), 400

        token = os.environ.get(
            "BOT_TOKEN",
            ""
        ).strip()

        if not token:

            return jsonify({

                "erro":
                    "BOT_TOKEN não está disponível para o processo."
            }), 500

        canal = os.environ.get(
            "CHANNEL_USERNAME",
            ""
        ).strip()

        if not canal:

            return jsonify({

                "erro":
                    "CHANNEL_USERNAME não está disponível."
            }), 500

        init_data = dados.get(
            "initData",
            ""
        )

        exigir_init_data = os.environ.get(
            "TELEGRAM_INIT_DATA_REQUIRED",
            "false"
        ).strip().lower()

        if exigir_init_data in (
            "1",
            "true",
            "yes",
            "sim"
        ):

            if not validar_init_data(
                init_data
            ):

                return jsonify({

                    "erro":
                        "Sessão do Telegram inválida."
                }), 401

        usuario = obter_usuario(
            init_data
        )

        if not usuario:

            usuario = dados.get(
                "user"
            )

        links = dados.get(
            "links",
            []
        )

        if not isinstance(
            links,
            list
        ):

            return jsonify({

                "erro":
                    "A lista de produtos é inválida."
            }), 400

        links = [

            str(link).strip()

            for link in links

            if str(link).strip()
        ]

        if not links:

            return jsonify({

                "erro":
                    "Adicione pelo menos um produto."
            }), 400

        if len(links) > MAX_LINKS:

            return jsonify({

                "erro":
                    "Máximo de 20 produtos."
            }), 400

        invalidos = [

            link

            for link in links

            if not link_shopee_valido(
                link
            )
        ]

        if invalidos:

            return jsonify({

                "erro":
                    "Um ou mais links não são válidos."
            }), 400

        try:

            quantidade = int(
                dados.get(
                    "quantidade",
                    1
                )
            )

        except Exception:

            return jsonify({

                "erro":
                    "Quantidade inválida."
            }), 400

        if quantidade < 1:

            return jsonify({

                "erro":
                    "A quantidade mínima é 1."
            }), 400

        if quantidade > len(links):

            return jsonify({

                "erro":
                    "A quantidade não pode ser maior que os produtos."
            }), 400

        if quantidade > MAX_LINKS:

            return jsonify({

                "erro":
                    "Máximo de 20 postagens."
            }), 400

        try:

            intervalo = int(
                dados.get(
                    "intervalo",
                    10
                )
            )

        except Exception:

            return jsonify({

                "erro":
                    "Intervalo inválido."
            }), 400

        if intervalo not in INTERVALOS_PERMITIDOS:

            return jsonify({

                "erro":
                    "Intervalo selecionado é inválido."
            }), 400

        links = links[
            :quantidade
        ]

        task_id = criar_tarefa(

            links=links,

            intervalo=intervalo,

            quantidade=quantidade,

            usuario=usuario
        )

        thread = threading.Thread(

            target=executar_tarefa,

            args=(task_id,),

            daemon=True
        )

        thread.start()

        return jsonify({

            "sucesso":
                True,

            "mensagem":
                "Automação iniciada com sucesso.",

            "task_id":
                task_id,

            "quantidade":
                quantidade,

            "intervalo":
                intervalo,

            "canal":
                canal
        })

    except Exception as erro:

        print(
            "Erro /api/configurar:",
            erro
        )

        return jsonify({

            "erro":
                "Erro interno do servidor.",

            "detalhes":
                str(erro)

        }), 500


# ============================================================
# STATUS
# ============================================================

@app.route(
    "/api/status/<task_id>",
    methods=["GET"]
)
def status(
    task_id
):

    with tarefas_lock:

        tarefa = tarefas.get(
            task_id
        )

        if not tarefa:

            return jsonify({

                "erro":
                    "Tarefa não encontrada."
            }), 404

        return jsonify({

            "id":
                tarefa["id"],

            "status":
                tarefa["status"],

            "progresso":
                tarefa["progresso"],

            "produto":
                tarefa["produto_atual"],

            "total":
                tarefa["quantidade"],

            "produto_link":
                tarefa["produto_link"],

            "resultados":
                tarefa["resultados"]
        })


# ============================================================
# PARAR
# ============================================================

@app.route(
    "/api/parar/<task_id>",
    methods=["POST"]
)
def parar(
    task_id
):

    with tarefas_lock:

        tarefa = tarefas.get(
            task_id
        )

        if not tarefa:

            return jsonify({

                "erro":
                    "Tarefa não encontrada."
            }), 404

        tarefa[
            "cancelada"
        ] = True

        tarefa[
            "status"
        ] = "cancelada"

    return jsonify({

        "sucesso":
            True,

        "mensagem":
            "Automação interrompida."
    })


# ============================================================
# EXECUÇÃO
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
