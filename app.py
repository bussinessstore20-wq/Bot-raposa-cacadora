import os
import json
import time
import uuid
import hashlib
import threading
import re

from urllib.parse import urlparse, parse_qs

import requests

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

SHOPEE_API_URL = os.environ.get(
    "SHOPEE_API_URL",
    "https://open-api.affiliate.shopee.com.br/graphql"
).strip()

SHOPEE_APP_ID = os.environ.get("SHOPEE_APP_ID", "").strip()
SHOPEE_SECRET = os.environ.get("SHOPEE_SECRET", "").strip()


MAX_LINKS = 20

INTERVALOS_PERMITIDOS = {
    10,
    60,
    300,
    600
}


# ============================================================
# TAREFAS
# ============================================================

tarefas = {}
tarefas_lock = threading.Lock()


# ============================================================
# UTILITÁRIOS
# ============================================================

def mascara_valor(valor):
    if not valor:
        return ""

    valor = str(valor)

    if len(valor) <= 4:
        return "*" * len(valor)

    return (
        valor[:2]
        + "*" * (len(valor) - 4)
        + valor[-2:]
    )


def agora():
    return int(time.time())


def json_compacto(dados):
    """
    IMPORTANTE:

    A Shopee assina o PAYLOAD JSON.
    Portanto precisamos gerar a string JSON uma única vez
    e usar exatamente essa mesma string na assinatura
    e no POST.
    """

    return json.dumps(
        dados,
        ensure_ascii=False,
        separators=(",", ":")
    )


# ============================================================
# ASSINATURA SHOPEE
# ============================================================

def gerar_assinatura_shopee(
    app_id,
    timestamp,
    payload_string,
    secret
):
    """
    Fórmula:

    SHA256(
        AppID +
        Timestamp +
        Payload +
        Secret
    )
    """

    fator = (
        str(app_id)
        + str(timestamp)
        + payload_string
        + str(secret)
    )

    return hashlib.sha256(
        fator.encode("utf-8")
    ).hexdigest()


def criar_headers_shopee(
    payload_string
):
    timestamp = agora()

    assinatura = gerar_assinatura_shopee(
        SHOPEE_APP_ID,
        timestamp,
        payload_string,
        SHOPEE_SECRET
    )

    authorization = (
        f"SHA256 "
        f"Credential={SHOPEE_APP_ID},"
        f"Timestamp={timestamp},"
        f"Signature={assinatura}"
    )

    return {
        "Authorization": authorization,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


# ============================================================
# CHAMADA GRAPHQL SHOPEE
# ============================================================

def shopee_graphql(
    query,
    variables=None,
    operation_name=None
):
    """
    Faz uma chamada GraphQL para a Shopee.

    O ponto mais importante aqui é:

    1. monta payload;
    2. transforma em JSON string;
    3. assina ESSA string;
    4. envia ESSA MESMA string.
    """

    if not SHOPEE_API_URL:
        return {
            "sucesso": False,
            "erro": "SHOPEE_API_URL não configurada."
        }

    if not SHOPEE_APP_ID:
        return {
            "sucesso": False,
            "erro": "SHOPEE_APP_ID não configurado."
        }

    if not SHOPEE_SECRET:
        return {
            "sucesso": False,
            "erro": "SHOPEE_SECRET não configurado."
        }

    payload = {
        "query": query
    }

    if operation_name is not None:
        payload["operationName"] = operation_name

    if variables is not None:
        payload["variables"] = variables

    # --------------------------------------------------------
    # JSON EXATO
    # --------------------------------------------------------

    payload_string = json_compacto(payload)

    timestamp = agora()

    assinatura = gerar_assinatura_shopee(
        SHOPEE_APP_ID,
        timestamp,
        payload_string,
        SHOPEE_SECRET
    )

    headers = {
        "Authorization":
            f"SHA256 "
            f"Credential={SHOPEE_APP_ID},"
            f"Timestamp={timestamp},"
            f"Signature={assinatura}",

        "Content-Type":
            "application/json",

        "Accept":
            "application/json"
    }

    print("=" * 60)
    print("[SHOPEE API] GraphQL")
    print("[SHOPEE API] URL:", SHOPEE_API_URL)
    print(
        "[SHOPEE API] AppID:",
        mascara_valor(SHOPEE_APP_ID)
    )
    print(
        "[SHOPEE API] Timestamp:",
        timestamp
    )
    print(
        "[SHOPEE API] Payload:",
        payload_string
    )
    print(
        "[SHOPEE API] Signature:",
        mascara_valor(assinatura)
    )
    print("=" * 60)

    try:

        # ----------------------------------------------------
        # ATENÇÃO:
        # NÃO usar json=payload aqui.
        #
        # Enviamos exatamente a string que foi assinada.
        # ----------------------------------------------------

        resposta = requests.post(
            SHOPEE_API_URL,
            data=payload_string.encode("utf-8"),
            headers=headers,
            timeout=30
        )

        print(
            "[SHOPEE API] HTTP:",
            resposta.status_code
        )

        texto = resposta.text

        print(
            "[SHOPEE API] Resposta:",
            texto[:5000]
        )

        try:
            dados = resposta.json()

        except Exception:

            return {
                "sucesso": False,
                "erro":
                    "Shopee retornou resposta que não é JSON.",
                "http_status":
                    resposta.status_code,
                "resposta":
                    texto[:2000]
            }

        if "errors" in dados:

            erros = dados.get(
                "errors",
                []
            )

            mensagem = "Erro desconhecido da Shopee."

            if erros:

                primeiro = erros[0]

                mensagem = (
                    primeiro.get("message")
                    or
                    str(primeiro)
                )

            return {
                "sucesso": False,
                "erro": mensagem,
                "http_status": resposta.status_code,
                "dados": dados
            }

        return {
            "sucesso": True,
            "http_status": resposta.status_code,
            "dados": dados
        }

    except requests.RequestException as erro:

        print(
            "[SHOPEE API] ERRO REQUEST:",
            erro
        )

        return {
            "sucesso": False,
            "erro": str(erro)
        }

    except Exception as erro:

        print(
            "[SHOPEE API] ERRO:",
            erro
        )

        return {
            "sucesso": False,
            "erro": str(erro)
        }


# ============================================================
# GERAR SHORT LINK
# ============================================================

def gerar_short_link(origin_url):

    query = """
mutation GenerateShortLink($input: ShortLinkInput!) {
  generateShortLink(input: $input) {
    shortLink
  }
}
"""

    variables = {
        "input": {
            "originUrl": origin_url
        }
    }

    resultado = shopee_graphql(
        query=query,
        variables=variables,
        operation_name="GenerateShortLink"
    )

    if not resultado.get("sucesso"):
        return resultado

    dados = resultado.get(
        "dados",
        {}
    )

    try:

        short_link = (
            dados
            ["data"]
            ["generateShortLink"]
            ["shortLink"]
        )

    except Exception:

        return {
            "sucesso": False,
            "erro":
                "Shopee não retornou shortLink.",
            "dados":
                dados
        }

    print(
        "[SHOPEE API] ShortLink gerado:",
        short_link
    )

    return {
        "sucesso": True,
        "shortLink": short_link,
        "dados": dados
    }


# ============================================================
# RESOLVER LINK
# ============================================================

def resolver_link_shopee(link):

    print("=" * 40)
    print("[SHOPEE] Tentando resolver URL:")
    print(link)
    print("=" * 40)

    headers = {
        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Linux; Android 10; K) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/130.0 Mobile Safari/537.36"
            ),
        "Accept":
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    try:

        resposta = requests.get(
            link,
            headers=headers,
            timeout=30,
            allow_redirects=True
        )

        print(
            "[SHOPEE] HTTP:",
            resposta.status_code
        )

        print(
            "[SHOPEE] URL final:",
            resposta.url
        )

        url_final = resposta.url

        # ----------------------------------------------------
        # Procurar URL de produto dentro do HTML
        # ----------------------------------------------------

        padroes = [

            r'https://shopee\.com\.br/[^"\']+-i\.\d+\.\d+',

            r'https://www\.shopee\.com\.br/[^"\']+-i\.\d+\.\d+',

            r'https://shopee\.com\.br/product/\d+/\d+',

            r'https://www\.shopee\.com\.br/product/\d+/\d+'

        ]

        for padrao in padroes:

            encontrado = re.search(
                padrao,
                resposta.text,
                re.IGNORECASE
            )

            if encontrado:

                url_encontrada = (
                    encontrado.group(0)
                )

                print(
                    "[SHOPEE] URL encontrada no HTML:",
                    url_encontrada
                )

                return url_encontrada

        return url_final

    except Exception as erro:

        print(
            "[SHOPEE] Erro ao resolver:",
            erro
        )

        return link


# ============================================================
# EXTRAIR SHOP ID / ITEM ID
# ============================================================

def extrair_ids_shopee(link):

    print(
        "[SHOPEE] Extraindo IDs de:",
        link
    )

    # --------------------------------------------------------
    # FORMATO:
    # shopee.com.br/slug-i.SHOPID.ITEMID
    # --------------------------------------------------------

    match = re.search(
        r'-i\.(\d+)\.(\d+)',
        link
    )

    if match:

        shop_id = match.group(1)
        item_id = match.group(2)

        print(
            "[SHOPEE] IDs encontrados:",
            shop_id,
            item_id
        )

        return shop_id, item_id

    # --------------------------------------------------------
    # FORMATO:
    # /product/SHOPID/ITEMID
    # --------------------------------------------------------

    match = re.search(
        r'/product/(\d+)/(\d+)',
        link
    )

    if match:

        shop_id = match.group(1)
        item_id = match.group(2)

        print(
            "[SHOPEE] IDs encontrados:",
            shop_id,
            item_id
        )

        return shop_id, item_id

    # --------------------------------------------------------
    # QUERY PARAMETERS
    # --------------------------------------------------------

    try:

        parsed = urlparse(link)

        query = parse_qs(
            parsed.query
        )

        shop_id = (
            query.get("shopid")
            or query.get("shop_id")
        )

        item_id = (
            query.get("itemid")
            or query.get("item_id")
        )

        if shop_id and item_id:

            return (
                shop_id[0],
                item_id[0]
            )

    except Exception:
        pass

    print(
        "[SHOPEE] Nenhum shopId/itemId encontrado."
    )

    return None, None


# ============================================================
# PRODUCT OFFER V2
# ============================================================

def buscar_product_offer(
    shop_id,
    item_id
):

    if not shop_id or not item_id:

        return {
            "sucesso": False,
            "erro":
                "shopId/itemId não encontrados."
        }

    query = """
query ProductOffer($shopId: Int64!, $itemId: Int64!) {
  productOfferV2(
    itemId: $itemId
    shopId: $shopId
  ) {
    nodes {
      productName
      price
      priceMin
      priceMax
      imageUrl
      offerLink
      shopId
      shopName
      commissionRate
      soldCount
      ratingStar
    }
  }
}
"""

    variables = {
        "shopId": int(shop_id),
        "itemId": int(item_id)
    }

    resultado = shopee_graphql(
        query=query,
        variables=variables,
        operation_name="ProductOffer"
    )

    return resultado


# ============================================================
# EXTRAIR PRODUTO DA RESPOSTA
# ============================================================

def extrair_produto_graphql(dados):

    try:

        nodes = (
            dados
            ["data"]
            ["productOfferV2"]
            ["nodes"]
        )

    except Exception:

        return None

    if not nodes:
        return None

    produto = nodes[0]

    return {

        "titulo":
            produto.get("productName")
            or
            "Oferta Shopee",

        "preco":
            produto.get("price"),

        "preco_min":
            produto.get("priceMin"),

        "preco_max":
            produto.get("priceMax"),

        "imagem":
            produto.get("imageUrl"),

        "offer_link":
            produto.get("offerLink"),

        "shop_id":
            produto.get("shopId"),

        "shop_name":
            produto.get("shopName"),

        "comissao":
            produto.get("commissionRate"),

        "vendidos":
            produto.get("soldCount"),

        "avaliacao":
            produto.get("ratingStar")
    }


# ============================================================
# PROCESSAR PRODUTO
# ============================================================

def processar_produto(link):

    print("=" * 50)
    print("[PRODUTO] Abrindo link:")
    print(link)
    print("=" * 50)

    # --------------------------------------------------------
    # 1. Resolver URL
    # --------------------------------------------------------

    url_final = resolver_link_shopee(
        link
    )

    print(
        "[PRODUTO] URL final:",
        url_final
    )

    # --------------------------------------------------------
    # 2. Extrair IDs
    # --------------------------------------------------------

    shop_id, item_id = extrair_ids_shopee(
        url_final
    )

    print(
        "[PRODUTO] shopId:",
        shop_id
    )

    print(
        "[PRODUTO] itemId:",
        item_id
    )

    produto = None

    # --------------------------------------------------------
    # 3. ProductOfferV2
    # --------------------------------------------------------

    if shop_id and item_id:

        print(
            "[PRODUTO] Consultando ProductOfferV2..."
        )

        resultado = buscar_product_offer(
            shop_id,
            item_id
        )

        if resultado.get("sucesso"):

            produto = extrair_produto_graphql(
                resultado.get("dados", {})
            )

            if produto:

                print(
                    "[PRODUTO] Produto encontrado:"
                )

                print(
                    json.dumps(
                        produto,
                        ensure_ascii=False
                    )
                )

    # --------------------------------------------------------
    # 4. Gerar ShortLink
    # --------------------------------------------------------

    print(
        "[PRODUTO] Gerando link de afiliado..."
    )

    short_resultado = gerar_short_link(
        link
    )

    short_link = None

    if short_resultado.get("sucesso"):

        short_link = (
            short_resultado
            .get("shortLink")
        )

    # --------------------------------------------------------
    # 5. Montar resultado
    # --------------------------------------------------------

    if produto:

        produto["link_original"] = link

        produto["link"] = (
            short_link
            or
            produto.get("offer_link")
            or
            url_final
        )

        return {
            "sucesso": True,
            "produto": produto,
            "shortLink": short_link
        }

    # --------------------------------------------------------
    # Se não conseguiu dados
    # --------------------------------------------------------

    return {

        "sucesso": False,

        "erro":
            "A Shopee não retornou os dados do produto.",

        "link":
            link,

        "url_final":
            url_final,

        "shortLink":
            short_link
    }


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api_url(metodo):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    return (
        f"https://api.telegram.org/"
        f"bot{token}/{metodo}"
    )


def telegram_get_me():

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {
            "ok": False,
            "erro":
                "BOT_TOKEN não configurado."
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


def telegram_enviar_mensagem(
    texto
):

    if not BOT_TOKEN:

        return {
            "ok": False,
            "erro":
                "BOT_TOKEN não configurado."
        }

    if not CHANNEL_USERNAME:

        return {
            "ok": False,
            "erro":
                "CHANNEL_USERNAME não configurado."
        }

    try:

        resposta = requests.post(
            telegram_api_url(
                "sendMessage"
            ),
            json={
                "chat_id":
                    CHANNEL_USERNAME,

                "text":
                    texto,

                "disable_web_page_preview":
                    False
            },
            timeout=30
        )

        dados = resposta.json()

        print(
            "[TELEGRAM] HTTP:",
            resposta.status_code
        )

        print(
            "[TELEGRAM] Resposta:",
            dados
        )

        return dados

    except Exception as erro:

        print(
            "[TELEGRAM] Erro:",
            erro
        )

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# PUBLICAR PRODUTO
# ============================================================

def publicar_produto(
    produto
):

    titulo = (
        produto.get("titulo")
        or
        "Oferta Shopee"
    )

    link = (
        produto.get("link")
        or
        produto.get("offer_link")
    )

    preco = produto.get("preco")

    preco_min = produto.get(
        "preco_min"
    )

    preco_max = produto.get(
        "preco_max"
    )

    texto = (
        "🦊🔥 OFERTA SHOPEE\n\n"
        f"🛍️ {titulo}\n\n"
    )

    if preco:

        try:

            preco_float = (
                float(preco) / 100
            )

            texto += (
                f"💰 R$ {preco_float:.2f}\n\n"
            )

        except Exception:

            texto += (
                f"💰 {preco}\n\n"
            )

    elif preco_min:

        try:

            preco_float = (
                float(preco_min) / 100
            )

            texto += (
                f"💰 A partir de "
                f"R$ {preco_float:.2f}\n\n"
            )

        except Exception:
            pass

    if preco_max:

        try:

            preco_float = (
                float(preco_max) / 100
            )

            texto += (
                f"💵 Até R$ "
                f"{preco_float:.2f}\n\n"
            )

        except Exception:
            pass

    if link:

        texto += (
            "🛒 COMPRAR AGORA:\n"
            f"{link}\n\n"
        )

    texto += (
        "🦊 Raposa Caçadora"
    )

    print(
        "[TELEGRAM] Publicando:",
        titulo
    )

    print(
        "[TELEGRAM] Link:",
        link
    )

    resultado = telegram_enviar_mensagem(
        texto
    )

    return resultado


# ============================================================
# TASK
# ============================================================

def executar_tarefa(
    task_id,
    links,
    intervalo,
    quantidade
):

    print(
        "[TASK] Iniciando",
        task_id
    )

    try:

        with tarefas_lock:

            tarefas[task_id] = {
                "status":
                    "processando",

                "total":
                    len(links),

                "processados":
                    0,

                "publicados":
                    0,

                "erros":
                    0
            }

        for index, link in enumerate(
            links[:quantidade]
        ):

            print("=" * 40)

            print(
                f"[TASK] Produto "
                f"{index + 1}/"
                f"{len(links[:quantidade])}"
            )

            print(
                "[TELEGRAM] Link:",
                link
            )

            try:

                resultado = processar_produto(
                    link
                )

                if resultado.get(
                    "sucesso"
                ):

                    produto = (
                        resultado
                        .get("produto")
                    )

                    telegram_resultado = (
                        publicar_produto(
                            produto
                        )
                    )

                    if telegram_resultado.get(
                        "ok"
                    ):

                        with tarefas_lock:

                            tarefas[
                                task_id
                            ][
                                "publicados"
                            ] += 1

                        print(
                            "[TELEGRAM] Produto publicado."
                        )

                    else:

                        with tarefas_lock:

                            tarefas[
                                task_id
                            ][
                                "erros"
                            ] += 1

                        print(
                            "[TELEGRAM] Falha ao publicar."
                        )

                else:

                    # ------------------------------------------------
                    # Fallback:
                    # mesmo que a Shopee não entregue dados do produto,
                    # não publicamos uma falsa oferta.
                    # ------------------------------------------------

                    with tarefas_lock:

                        tarefas[
                            task_id
                        ][
                            "erros"
                        ] += 1

                    print(
                        "[PRODUTO] Falha:",
                        resultado.get(
                            "erro"
                        )
                    )

            except Exception as erro:

                print(
                    "[TASK] Erro no produto:",
                    erro
                )

                with tarefas_lock:

                    tarefas[
                        task_id
                    ][
                        "erros"
                    ] += 1

            with tarefas_lock:

                tarefas[
                    task_id
                ][
                    "processados"
                ] += 1

            # ----------------------------------------------------
            # Intervalo
            # ----------------------------------------------------

            if index < quantidade - 1:

                print(
                    f"[TASK] Aguardando "
                    f"{intervalo}s..."
                )

                time.sleep(
                    intervalo
                )

        with tarefas_lock:

            tarefas[
                task_id
            ][
                "status"
            ] = "concluida"

        print(
            "[TASK] Finalizada",
            task_id
        )

    except Exception as erro:

        print(
            "[TASK] ERRO FATAL:",
            erro
        )

        with tarefas_lock:

            tarefas[
                task_id
            ] = {

                "status":
                    "erro",

                "erro":
                    str(erro)
            }


# ============================================================
# DEBUG ENV
# ============================================================

@app.route(
    "/debug-env",
    methods=["GET"]
)
def debug_env():

    return jsonify({

        "status":
            "ok",

        "telegram": {

            "BOT_TOKEN":
                {
                    "existe":
                        bool(BOT_TOKEN),

                    "mascara":
                        mascara_valor(BOT_TOKEN),

                    "tamanho":
                        len(BOT_TOKEN)
                },

            "CHANNEL_USERNAME":
                {
                    "existe":
                        bool(CHANNEL_USERNAME),

                    "mascara":
                        mascara_valor(
                            CHANNEL_USERNAME
                        ),

                    "tamanho":
                        len(CHANNEL_USERNAME)
                }
        },

        "shopee": {

            "SHOPEE_API_URL":
                {
                    "existe":
                        bool(SHOPEE_API_URL),

                    "valor":
                        SHOPEE_API_URL,

                    "tamanho":
                        len(SHOPEE_API_URL)
                },

            "SHOPEE_APP_ID":
                {
                    "existe":
                        bool(SHOPEE_APP_ID),

                    "mascara":
                        mascara_valor(
                            SHOPEE_APP_ID
                        ),

                    "tamanho":
                        len(SHOPEE_APP_ID)
                },

            "SHOPEE_SECRET":
                {
                    "existe":
                        bool(SHOPEE_SECRET),

                    "mascara":
                        mascara_valor(
                            SHOPEE_SECRET
                        ),

                    "tamanho":
                        len(SHOPEE_SECRET)
                }
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
            agora()
    })


# ============================================================
# DEBUG TELEGRAM
# ============================================================

@app.route(
    "/debug-telegram",
    methods=["GET"]
)
def debug_telegram():

    resultado = telegram_get_me()

    bot = (
        resultado.get("result")
        if resultado.get("ok")
        else None
    )

    return jsonify({

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

        "canal": {

            "configurado":
                bool(
                    CHANNEL_USERNAME
                ),

            "valor":
                CHANNEL_USERNAME
        },

        "erro":
            resultado.get("erro")
            or
            resultado.get("description")
    })


# ============================================================
# DEBUG SHOPEE
# ============================================================

@app.route(
    "/debug-shopee",
    methods=["GET"]
)
def debug_shopee():

    return jsonify({

        "configuracao": {

            "SHOPEE_API_URL":
                SHOPEE_API_URL,

            "SHOPEE_APP_ID":
                mascara_valor(
                    SHOPEE_APP_ID
                ),

            "SHOPEE_SECRET":
                mascara_valor(
                    SHOPEE_SECRET
                )
        },

        "validacao": {

            "api_url_configurada":
                bool(SHOPEE_API_URL),

            "app_id_configurado":
                bool(SHOPEE_APP_ID),

            "secret_configurado":
                bool(SHOPEE_SECRET),

            "configuracao_completa":
                bool(
                    SHOPEE_API_URL
                    and
                    SHOPEE_APP_ID
                    and
                    SHOPEE_SECRET
                )
        },

        "timestamp":
            agora()
    })


# ============================================================
# DEBUG SHOPEE GRAPHQL
# ============================================================

@app.route(
    "/debug-shopee-graphql",
    methods=["GET"]
)
def debug_shopee_graphql():

    query = """
query {
  productOfferV2(
    keyword: "iphone"
    sortType: 1
    page: 1
    limit: 1
  ) {
    nodes {
      productName
      price
      imageUrl
      offerLink
      shopId
      shopName
    }
  }
}
"""

    resultado = shopee_graphql(
        query=query
    )

    return jsonify({

        "sucesso":
            resultado.get(
                "sucesso",
                False
            ),

        "http_status":
            resultado.get(
                "http_status"
            ),

        "tem_dados":
            bool(
                resultado.get(
                    "dados"
                )
            ),

        "erro":
            resultado.get(
                "erro"
            )
    })


# ============================================================
# DEBUG PRODUTO
#
# USAR:
#
# /debug-produto?link=https://s.shopee.com.br/...
#
# ============================================================

@app.route(
    "/debug-produto",
    methods=["GET"]
)
def debug_produto():

    link = (
        request.args.get(
            "link",
            ""
        )
        .strip()
    )

    # Aceita também ?url= para evitar confusão
    if not link:

        link = (
            request.args.get(
                "url",
                ""
            )
            .strip()
        )

    if not link:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "Informe ?link=https://..."
        }), 400

    print(
        "[DEBUG PRODUTO] Link:",
        link
    )

    resultado = processar_produto(
        link
    )

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

    return jsonify({

        "status":
            "ok",

        "service":
            "raposa-cacadora",

        "telegram":
            bool(BOT_TOKEN),

        "telegram_canal":
            bool(CHANNEL_USERNAME),

        "shopee_api":
            bool(SHOPEE_API_URL),

        "shopee_app_id":
            bool(SHOPEE_APP_ID),

        "shopee_secret":
            bool(SHOPEE_SECRET),

        "shopee_configuracao_completa":
            bool(
                SHOPEE_API_URL
                and
                SHOPEE_APP_ID
                and
                SHOPEE_SECRET
            ),

        "timestamp":
            agora()
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
            bool(BOT_TOKEN),

        "shopee_configurada":
            bool(
                SHOPEE_API_URL
                and
                SHOPEE_APP_ID
                and
                SHOPEE_SECRET
            ),

        "timestamp":
            agora()
    })


# ============================================================
# CONFIGURAR AUTOMAÇÃO
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    print("=" * 40)
    print("[API] POST /api/configurar")

    try:

        dados = request.get_json(
            silent=True
        )

    except Exception:

        dados = None

    if not dados:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "JSON inválido ou ausente."
        }), 400

    links = dados.get(
        "links",
        []
    )

    intervalo = dados.get(
        "intervalo",
        10
    )

    quantidade = dados.get(
        "quantidade",
        1
    )

    usuario = dados.get(
        "user"
    )

    print(
        "[API] Links recebidos:",
        len(links)
        if isinstance(links, list)
        else "inválido"
    )

    print(
        "[TELEGRAM] Usuário:",
        usuario
    )

    print(
        "[TELEGRAM] Canal:",
        CHANNEL_USERNAME
    )

    print(
        "[SHOPEE] API URL:",
        SHOPEE_API_URL
    )

    print(
        "[SHOPEE] AppID:",
        mascara_valor(SHOPEE_APP_ID)
    )

    print(
        "[SHOPEE] Secret configurado:",
        bool(SHOPEE_SECRET)
    )

    # --------------------------------------------------------
    # VALIDAR LINKS
    # --------------------------------------------------------

    if not isinstance(
        links,
        list
    ):

        return jsonify({

            "sucesso":
                False,

            "erro":
                "O campo links precisa ser uma lista."
        }), 400

    links = [
        str(link).strip()
        for link in links
        if str(link).strip()
    ]

    if not links:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "Informe pelo menos um link da Shopee."
        }), 400

    if len(links) > MAX_LINKS:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "Máximo de 20 links."
        }), 400

    # --------------------------------------------------------
    # VALIDAR INTERVALO
    # --------------------------------------------------------

    try:

        intervalo = int(
            intervalo
        )

    except Exception:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "Intervalo inválido."
        }), 400

    if intervalo not in INTERVALOS_PERMITIDOS:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "Intervalo não permitido."
        }), 400

    # --------------------------------------------------------
    # VALIDAR QUANTIDADE
    # --------------------------------------------------------

    try:

        quantidade = int(
            quantidade
        )

    except Exception:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "Quantidade inválida."
        }), 400

    if quantidade < 1:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "Quantidade mínima é 1."
        }), 400

    if quantidade > len(links):

        quantidade = len(
            links
        )

    # --------------------------------------------------------
    # CRIAR TASK
    # --------------------------------------------------------

    task_id = str(
        uuid.uuid4()
    )

    with tarefas_lock:

        tarefas[task_id] = {

            "status":
                "iniciando",

            "total":
                quantidade,

            "processados":
                0,

            "publicados":
                0,

            "erros":
                0
        }

    thread = threading.Thread(
        target=executar_tarefa,
        args=(
            task_id,
            links,
            intervalo,
            quantidade
        ),
        daemon=True
    )

    thread.start()

    print(
        "[TASK] Iniciando",
        task_id
    )

    print(
        "[API] Task criada:",
        task_id
    )

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
            intervalo
    })


# ============================================================
# STATUS
# ============================================================

@app.route(
    "/api/status/<task_id>",
    methods=["GET"]
)
def status_tarefa(
    task_id
):

    with tarefas_lock:

        tarefa = tarefas.get(
            task_id
        )

        if not tarefa:

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "Tarefa não encontrada."
            }), 404

        return jsonify(
            tarefa
        )


# ============================================================
# CANCELAR
# ============================================================

@app.route(
    "/api/cancelar/<task_id>",
    methods=["POST"]
)
def cancelar_tarefa(
    task_id
):

    with tarefas_lock:

        tarefa = tarefas.get(
            task_id
        )

        if not tarefa:

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "Tarefa não encontrada."
            }), 404

        tarefa["status"] = "cancelada"

    return jsonify({

        "sucesso":
            True,

        "mensagem":
            "Tarefa marcada para cancelamento."
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
        port=port,
        debug=False
    )
