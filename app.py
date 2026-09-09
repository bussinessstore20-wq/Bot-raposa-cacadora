import os
import hashlib
import json
import threading
import time
import uuid
import re

from urllib.parse import (
    urlparse,
    parse_qs,
    unquote
)

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
    "https://open-api.affiliate.shopee.com.br/graphql"
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
        + ("*" * (len(valor) - 4))
        + valor[-2:]
    )


def debug_variavel(nome):

    valor = os.environ.get(
        nome,
        ""
    ).strip()

    return {
        "existe": bool(valor),
        "tamanho": len(valor),
        "mascara": mascara_valor(valor)
    }


def atualizar_tarefa(task_id, **dados):

    with tarefas_lock:

        if task_id in tarefas:

            tarefas[task_id].update(
                dados
            )


def telegram_api_url(metodo):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    return (
        f"https://api.telegram.org/"
        f"bot{token}/{metodo}"
    )


def limpar_html_texto(texto):

    if not texto:
        return ""

    texto = re.sub(
        r"<[^>]+>",
        " ",
        texto
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def normalizar_url(url):

    if not url:
        return ""

    return unquote(
        str(url).strip()
    )


def url_eh_shopee(url):

    try:

        host = (
            urlparse(url)
            .netloc
            .lower()
            .split(":")[0]
        )

        return (
            host == "shopee.com.br"
            or host.endswith(".shopee.com.br")
            or host == "s.shopee.com.br"
        )

    except Exception:

        return False


# ============================================================
# TELEGRAM
# ============================================================

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

        try:
            return resposta.json()

        except Exception:

            return {
                "ok": False,
                "erro": resposta.text[:1000],
                "http_status": resposta.status_code
            }

    except Exception as erro:

        return {
            "ok": False,
            "erro": str(erro)
        }


def telegram_enviar_mensagem(texto):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    canal = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()

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
                "erro": resposta.text[:1000],
                "http_status": resposta.status_code
            }

        print(
            "[TELEGRAM] sendMessage:",
            json.dumps(
                dados,
                ensure_ascii=False
            )
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


def telegram_enviar_foto(
    imagem_url,
    legenda
):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    canal = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()

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

    if not imagem_url:

        return {
            "ok": False,
            "erro": "Imagem vazia."
        }

    try:

        resposta = requests.post(
            telegram_api_url("sendPhoto"),
            json={
                "chat_id": canal,
                "photo": imagem_url,
                "caption": legenda,
                "disable_notification": False
            },
            timeout=40
        )

        try:

            dados = resposta.json()

        except Exception:

            dados = {
                "ok": False,
                "erro": resposta.text[:1000],
                "http_status": resposta.status_code
            }

        print(
            "[TELEGRAM] sendPhoto:",
            json.dumps(
                dados,
                ensure_ascii=False
            )
        )

        return dados

    except Exception as erro:

        print(
            "[TELEGRAM] Erro sendPhoto:",
            erro
        )

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# SHOPEE GRAPHQL
# ============================================================

def shopee_assinatura(payload):

    timestamp = int(
        time.time()
    )

    base = (
        str(SHOPEE_APP_ID)
        + str(timestamp)
        + payload
        + str(SHOPEE_SECRET)
    )

    assinatura = hashlib.sha256(
        base.encode("utf-8")
    ).hexdigest()

    return timestamp, assinatura


def shopee_graphql(
    query,
    variables=None,
    operation_name=None
):

    if not SHOPEE_API_URL:

        return {
            "ok": False,
            "erro": "SHOPEE_API_URL não configurada."
        }

    if not SHOPEE_APP_ID:

        return {
            "ok": False,
            "erro": "SHOPEE_APP_ID não configurado."
        }

    if not SHOPEE_SECRET:

        return {
            "ok": False,
            "erro": "SHOPEE_SECRET não configurado."
        }

    payload_obj = {
        "query": query
    }

    if operation_name:

        payload_obj["operationName"] = (
            operation_name
        )

    if variables is not None:

        payload_obj["variables"] = variables

    payload = json.dumps(
        payload_obj,
        ensure_ascii=False,
        separators=(",", ":")
    )

    timestamp, assinatura = (
        shopee_assinatura(
            payload
        )
    )

    signature_header = (
        f"SHA256 Credential={SHOPEE_APP_ID},"
        f"Timestamp={timestamp},"
        f"Signature={assinatura}"
    )

    headers = {

        "Content-Type":
            "application/json",

        "Accept":
            "application/json",

        "Authorization":
            signature_header,

        "User-Agent":
            "Raposa-Cacadora/3.0"
    }

    print("=" * 70)
    print("[SHOPEE API] GraphQL")
    print("[SHOPEE API] URL:", SHOPEE_API_URL)
    print(
        "[SHOPEE API] AppID:",
        mascara_valor(SHOPEE_APP_ID)
    )
    print(
        "[SHOPEE API] Operation:",
        operation_name
    )
    print(
        "[SHOPEE API] Variables:",
        json.dumps(
            variables,
            ensure_ascii=False
        )
        if variables is not None
        else None
    )
    print("=" * 70)

    try:

        resposta = requests.post(
            SHOPEE_API_URL,
            headers=headers,
            data=payload.encode("utf-8"),
            timeout=40
        )

        print(
            "[SHOPEE API] HTTP:",
            resposta.status_code
        )

        print(
            "[SHOPEE API] Resposta:",
            resposta.text[:10000]
        )

        try:

            dados = resposta.json()

        except Exception:

            return {
                "ok": False,
                "http_status":
                    resposta.status_code,
                "erro":
                    "Resposta da Shopee não é JSON.",
                "texto":
                    resposta.text[:5000]
            }

        if resposta.status_code != 200:

            return {
                "ok": False,
                "http_status":
                    resposta.status_code,
                "erro":
                    "HTTP diferente de 200.",
                "dados":
                    dados
            }

        if dados.get("errors"):

            return {
                "ok": False,
                "http_status":
                    resposta.status_code,
                "erro":
                    dados.get("errors"),
                "dados":
                    dados
            }

        return {
            "ok": True,
            "http_status":
                resposta.status_code,
            "dados":
                dados
        }

    except Exception as erro:

        print(
            "[SHOPEE API] EXCEÇÃO:",
            erro
        )

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# RESOLVER LINK SHOPEE
# ============================================================

def criar_sessao_shopee():

    session = requests.Session()

    session.headers.update({

        "User-Agent": (
            "Mozilla/5.0 "
            "(Linux; Android 15) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0.0.0 "
            "Mobile Safari/537.36"
        ),

        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "image/avif,"
            "image/webp,"
            "*/*;q=0.8"
        ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8",

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache"
    })

    return session


def resolver_url_shopee(link):

    print("=" * 70)
    print("[SHOPEE] RESOLVENDO LINK")
    print(link)
    print("=" * 70)

    session = criar_sessao_shopee()

    try:

        resposta = session.get(
            link,
            timeout=30,
            allow_redirects=True
        )

        url_final = (
            resposta.url
            or link
        )

        html = (
            resposta.text
            or ""
        )

        historico = []

        for r in resposta.history:

            historico.append({

                "status":
                    r.status_code,

                "url":
                    r.url,

                "location":
                    r.headers.get(
                        "Location"
                    )
            })

        print(
            "[SHOPEE] HTTP:",
            resposta.status_code
        )

        print(
            "[SHOPEE] URL FINAL:",
            url_final
        )

        print(
            "[SHOPEE] HISTÓRICO:",
            historico
        )

        print(
            "[SHOPEE] HTML:",
            len(html),
            "bytes"
        )

        return {

            "ok":
                resposta.ok,

            "url":
                url_final,

            "html":
                html,

            "headers":
                dict(resposta.headers),

            "cookies":
                session.cookies.get_dict(),

            "history":
                historico
        }

    except Exception as erro:

        print(
            "[SHOPEE] ERRO AO RESOLVER:",
            erro
        )

        return {

            "ok":
                False,

            "url":
                link,

            "html":
                "",

            "headers":
                {},

            "cookies":
                {},

            "history":
                [],

            "erro":
                str(erro)
        }


# ============================================================
# EXTRAIR SHOP ID / ITEM ID
# ============================================================

def extrair_ids_shopee(url):

    print(
        "[SHOPEE] Extraindo IDs de:",
        url
    )

    if not url:

        return None, None

    url = normalizar_url(
        url
    )

    shop_id = None
    item_id = None

    # --------------------------------------------------------
    # /product/SHOP/ITEM
    # --------------------------------------------------------

    padroes = [

        r"/product/"
        r"(\d+)"
        r"/"
        r"(\d+)",

        # ----------------------------------------------------
        # /opaanlp/SHOP/ITEM
        # ----------------------------------------------------

        r"/opaanlp/"
        r"(\d+)"
        r"/"
        r"(\d+)",

        # ----------------------------------------------------
        # produto-i.SHOP.ITEM
        # ----------------------------------------------------

        r"-i\."
        r"(\d+)"
        r"\."
        r"(\d+)",

        # ----------------------------------------------------
        # /SHOP/ITEM
        # ----------------------------------------------------

        r"/"
        r"(\d{5,})"
        r"/"
        r"(\d{5,})"
        r"(?:[/?#]|$)"
    ]

    for padrao in padroes:

        match = re.search(
            padrao,
            url,
            re.IGNORECASE
        )

        if match:

            shop_id = (
                match.group(1)
            )

            item_id = (
                match.group(2)
            )

            print(
                "[SHOPEE] IDs encontrados pela URL:",
                shop_id,
                item_id
            )

            return shop_id, item_id

    # --------------------------------------------------------
    # Query string
    # --------------------------------------------------------

    try:

        parsed = urlparse(
            url
        )

        params = parse_qs(
            parsed.query
        )

        shop_chaves = [
            "shopid",
            "shopId",
            "shop_id"
        ]

        item_chaves = [
            "itemid",
            "itemId",
            "item_id"
        ]

        for chave in shop_chaves:

            if (
                chave in params
                and
                params[chave]
            ):

                shop_id = str(
                    params[chave][0]
                )

                break

        for chave in item_chaves:

            if (
                chave in params
                and
                params[chave]
            ):

                item_id = str(
                    params[chave][0]
                )

                break

    except Exception as erro:

        print(
            "[SHOPEE] Erro query IDs:",
            erro
        )

    print(
        "[SHOPEE] IDs finais:",
        shop_id,
        item_id
    )

    return shop_id, item_id


# ============================================================
# PRODUCT OFFER V2 POR SHOP + ITEM
# ============================================================

def shopee_buscar_produto_por_ids(
    shop_id,
    item_id
):

    if not shop_id or not item_id:

        return {
            "ok": False,
            "erro":
                "shopId ou itemId ausente."
        }

    print("=" * 70)
    print("[SHOPEE] BUSCANDO PRODUTO POR IDs")
    print("[SHOPEE] shopId:", shop_id)
    print("[SHOPEE] itemId:", item_id)
    print("=" * 70)

    # A API Affiliate suporta filtros shopId/itemId
    # no productOfferV2.

    query = """
query ProductOfferByIds(
  $shopId: Int64
  $itemId: Int64
  $page: Int
  $limit: Int
) {
  productOfferV2(
    shopId: $shopId
    itemId: $itemId
    page: $page
    limit: $limit
  ) {
    nodes {
      itemId
      productName
      price
      priceMin
      priceMax
      priceDiscountRate
      commissionRate
      commission
      imageUrl
      offerLink
      productLink
      shopId
      shopName
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

        "shopId":
            int(shop_id),

        "itemId":
            int(item_id),

        "page":
            1,

        "limit":
            10
    }

    resultado = shopee_graphql(
        query=query,
        variables=variables,
        operation_name="ProductOfferByIds"
    )

    if not resultado.get("ok"):

        print(
            "[SHOPEE] Busca por IDs falhou."
        )

        return {
            "ok": False,
            "erro":
                resultado.get("erro"),
            "dados":
                resultado.get("dados")
        }

    try:

        nodes = (
            resultado
            ["dados"]
            ["data"]
            ["productOfferV2"]
            ["nodes"]
        )

    except Exception:

        nodes = []

    if not nodes:

        print(
            "[SHOPEE] Nenhum produto retornado "
            "para os IDs."
        )

        return {
            "ok": False,
            "erro":
                "A API Affiliate não retornou "
                "oferta para esse shopId/itemId.",
            "dados":
                resultado.get("dados")
        }

    # Preferimos correspondência exata.

    produto = None

    for node in nodes:

        node_shop = str(
            node.get("shopId", "")
        )

        node_item = str(
            node.get("itemId", "")
        )

        if (
            node_shop == str(shop_id)
            and
            node_item == str(item_id)
        ):

            produto = node
            break

    if produto is None:

        produto = nodes[0]

    print(
        "[SHOPEE] PRODUTO ENCONTRADO:"
    )

    print(
        json.dumps(
            produto,
            ensure_ascii=False
        )
    )

    return {
        "ok": True,
        "produto":
            produto
    }


# ============================================================
# GERAR SHORT LINK
# ============================================================

def shopee_generate_short_link(
    origin_url
):

    if not origin_url:

        return {
            "ok": False,
            "erro":
                "originUrl vazio."
        }

    query = """
mutation GenerateShortLink(
  $input: ShortLinkInput!
) {
  generateShortLink(
    input: $input
  ) {
    shortLink
  }
}
"""

    variables = {

        "input": {

            "originUrl":
                origin_url
        }
    }

    resultado = shopee_graphql(
        query=query,
        variables=variables,
        operation_name="GenerateShortLink"
    )

    if not resultado.get("ok"):

        return {
            "ok": False,
            "erro":
                resultado.get("erro"),
            "dados":
                resultado.get("dados")
        }

    try:

        short_link = (
            resultado
            ["dados"]
            ["data"]
            ["generateShortLink"]
            ["shortLink"]
        )

    except Exception:

        return {
            "ok": False,
            "erro":
                "A Shopee não retornou shortLink.",
            "dados":
                resultado.get("dados")
        }

    print(
        "[SHOPEE] SHORT LINK:",
        short_link
    )

    return {
        "ok": True,
        "shortLink":
            short_link
    }


# ============================================================
# EXTRAIR META TAG
# ============================================================

def extrair_meta(
    html,
    propriedade
):

    if not html:

        return ""

    padroes = [

        rf'<meta[^>]+property=["\']'
        rf'{re.escape(propriedade)}'
        rf'["\'][^>]+content=["\']'
        rf'(.*?)["\']',

        rf'<meta[^>]+name=["\']'
        rf'{re.escape(propriedade)}'
        rf'["\'][^>]+content=["\']'
        rf'(.*?)["\']'
    ]

    for padrao in padroes:

        match = re.search(
            padrao,
            html,
            re.IGNORECASE |
            re.DOTALL
        )

        if match:

            return unquote(
                match.group(1).strip()
            )

    return ""


# ============================================================
# EXTRAIR JSON-LD
# ============================================================

def extrair_produto_jsonld(
    html
):

    if not html:

        return None

    blocos = re.findall(

        r'<script[^>]+type=["\']'
        r'application/ld\+json'
        r'["\'][^>]*>'
        r'(.*?)'
        r'</script>',

        html,

        re.IGNORECASE |
        re.DOTALL
    )

    for bloco in blocos:

        try:

            dados = json.loads(
                bloco.strip()
            )

        except Exception:

            continue

        objetos = []

        if isinstance(
            dados,
            list
        ):

            objetos = dados

        elif isinstance(
            dados,
            dict
        ):

            objetos = [
                dados
            ]

        for obj in objetos:

            if not isinstance(
                obj,
                dict
            ):

                continue

            tipo = obj.get(
                "@type"
            )

            eh_produto = (

                tipo == "Product"

                or

                (
                    isinstance(
                        tipo,
                        list
                    )
                    and
                    "Product" in tipo
                )
            )

            if not eh_produto:

                continue

            nome = obj.get(
                "name"
            )

            imagem = obj.get(
                "image"
            )

            preco = ""

            offers = obj.get(
                "offers"
            )

            if isinstance(
                offers,
                dict
            ):

                preco = (
                    offers.get("price")
                    or
                    offers.get("lowPrice")
                    or
                    ""
                )

            elif isinstance(
                offers,
                list
            ) and offers:

                preco = (
                    offers[0].get("price")
                    or
                    offers[0].get("lowPrice")
                    or
                    ""
                )

            if isinstance(
                imagem,
                list
            ):

                imagem = (
                    imagem[0]
                    if imagem
                    else ""
                )

            return {

                "productName":
                    nome or "",

                "price":
                    preco or "",

                "imageUrl":
                    imagem or ""
            }

    return None


# ============================================================
# EXTRAIR DADOS DO HTML
# ============================================================

def extrair_produto_html(
    html
):

    if not html:

        return None

    titulo = extrair_meta(
        html,
        "og:title"
    )

    imagem = extrair_meta(
        html,
        "og:image"
    )

    descricao = extrair_meta(
        html,
        "og:description"
    )

    preco = ""

    jsonld = (
        extrair_produto_jsonld(
            html
        )
    )

    if jsonld:

        titulo = (
            jsonld.get(
                "productName"
            )
            or
            titulo
        )

        imagem = (
            jsonld.get(
                "imageUrl"
            )
            or
            imagem
        )

        preco = (
            jsonld.get(
                "price"
            )
            or
            preco
        )

    # --------------------------------------------------------
    # Título HTML
    # --------------------------------------------------------

    if not titulo:

        match = re.search(

            r"<title[^>]*>"
            r"(.*?)"
            r"</title>",

            html,

            re.IGNORECASE |
            re.DOTALL
        )

        if match:

            titulo = limpar_html_texto(
                match.group(1)
            )

    # --------------------------------------------------------
    # Preço
    # --------------------------------------------------------

    if not preco:

        padroes_preco = [

            r'"price"\s*:\s*"([^"]+)"',

            r'"price"\s*:\s*'
            r'([0-9]+(?:\.[0-9]+)?)',

            r'"priceMin"\s*:\s*"([^"]+)"',

            r'"priceMin"\s*:\s*'
            r'([0-9]+(?:\.[0-9]+)?)',

            r'"price_max"\s*:\s*"([^"]+)"',

            r'"price_max"\s*:\s*'
            r'([0-9]+(?:\.[0-9]+)?)'
        ]

        for padrao in padroes_preco:

            match = re.search(
                padrao,
                html,
                re.IGNORECASE
            )

            if match:

                preco = (
                    match.group(1)
                    .strip()
                )

                break

    titulo = limpar_html_texto(
        titulo
    )

    if not titulo:

        return None

    if len(titulo) < 3:

        return None

    titulo_lower = titulo.lower()

    termos_genericos = [

        "shopee brasil",
        "ofertas incríveis",
        "ofertas incriveis",
        "compras online"
    ]

    if any(
        termo in titulo_lower
        for termo in termos_genericos
    ):

        # Só rejeita se parecer realmente
        # uma página genérica.

        if len(titulo) < 80:

            return None

    return {

        "productName":
            titulo,

        "price":
            preco or "",

        "priceMin":
            preco or "",

        "priceMax":
            preco or "",

        "imageUrl":
            imagem or "",

        "description":
            descricao or ""
    }


# ============================================================
# OBTER PRODUTO
# ============================================================

def obter_produto(link):

    print("=" * 70)
    print("[PRODUTO] INICIANDO")
    print("[PRODUTO] LINK:", link)
    print("=" * 70)

    if not url_eh_shopee(
        link
    ):

        return {

            "ok": False,

            "erro":
                "O link não parece ser uma URL válida da Shopee."
        }

    # --------------------------------------------------------
    # 1. Resolver short-link
    # --------------------------------------------------------

    resolucao = resolver_url_shopee(
        link
    )

    url_final = (
        resolucao.get(
            "url"
        )
        or
        link
    )

    html = (
        resolucao.get(
            "html"
        )
        or
        ""
    )

    print(
        "[PRODUTO] URL FINAL:",
        url_final
    )

    # --------------------------------------------------------
    # 2. Extrair IDs
    # --------------------------------------------------------

    shop_id, item_id = (
        extrair_ids_shopee(
            url_final
        )
    )

    # --------------------------------------------------------
    # 3. Se não encontrou na URL final,
    #    procurar no Location do histórico
    # --------------------------------------------------------

    if not (
        shop_id
        and
        item_id
    ):

        for evento in (
            resolucao.get(
                "history",
                []
            )
        ):

            location = evento.get(
                "location"
            )

            if not location:

                continue

            shop_tmp, item_tmp = (
                extrair_ids_shopee(
                    location
                )
            )

            if shop_tmp and item_tmp:

                shop_id = shop_tmp
                item_id = item_tmp

                print(
                    "[PRODUTO] IDs encontrados "
                    "no redirect Location."
                )

                break

    print(
        "[PRODUTO] shopId:",
        shop_id
    )

    print(
        "[PRODUTO] itemId:",
        item_id
    )

    # --------------------------------------------------------
    # 4. PRINCIPAL:
    #    buscar produto diretamente na Affiliate API
    # --------------------------------------------------------

    if shop_id and item_id:

        resultado_api = (
            shopee_buscar_produto_por_ids(
                shop_id,
                item_id
            )
        )

        if resultado_api.get(
            "ok"
        ):

            produto = (
                resultado_api[
                    "produto"
                ]
            )

            # ------------------------------------------------
            # Montar dados normalizados
            # ------------------------------------------------

            produto_normalizado = {

                "productName":
                    produto.get(
                        "productName"
                    )
                    or
                    "Oferta Shopee",

                "price":
                    produto.get(
                        "price"
                    )
                    or
                    produto.get(
                        "priceMin"
                    )
                    or
                    "",

                "priceMin":
                    produto.get(
                        "priceMin"
                    )
                    or
                    "",

                "priceMax":
                    produto.get(
                        "priceMax"
                    )
                    or
                    "",

                "imageUrl":
                    produto.get(
                        "imageUrl"
                    )
                    or
                    "",

                "description":
                    "",

                "offerLink":
                    produto.get(
                        "offerLink"
                    )
                    or
                    "",

                "productLink":
                    produto.get(
                        "productLink"
                    )
                    or
                    url_final,

                "shopId":
                    produto.get(
                        "shopId"
                    )
                    or
                    shop_id,

                "shopName":
                    produto.get(
                        "shopName"
                    )
                    or
                    "",

                "itemId":
                    produto.get(
                        "itemId"
                    )
                    or
                    item_id,

                "priceDiscountRate":
                    produto.get(
                        "priceDiscountRate"
                    )
                    or
                    0
            }

            # ------------------------------------------------
            # Se API não retornou offerLink,
            # tentar gerar short-link afiliado.
            # ------------------------------------------------

            short_link = (
                produto_normalizado[
                    "offerLink"
                ]
            )

            if not short_link:

                canonical = (
                    produto_normalizado[
                        "productLink"
                    ]
                    or
                    url_final
                )

                short_result = (
                    shopee_generate_short_link(
                        canonical
                    )
                )

                if short_result.get(
                    "ok"
                ):

                    short_link = (
                        short_result.get(
                            "shortLink"
                        )
                    )

                    produto_normalizado[
                        "offerLink"
                    ] = short_link

            return {

                "ok": True,

                "produto":
                    produto_normalizado,

                "url_final":
                    (
                        produto_normalizado[
                            "productLink"
                        ]
                        or
                        url_final
                    ),

                "shortLink":
                    short_link,

                "metodo":
                    "AffiliateAPI-shopId-itemId"
            }

        print(
            "[PRODUTO] API não encontrou "
            "a oferta por IDs."
        )

    # --------------------------------------------------------
    # 5. Fallback HTML
    # --------------------------------------------------------

    produto_html = (
        extrair_produto_html(
            html
        )
    )

    if produto_html:

        produto_html[
            "shopId"
        ] = shop_id

        produto_html[
            "itemId"
        ] = item_id

        produto_html[
            "productLink"
        ] = url_final

        short_result = (
            shopee_generate_short_link(
                url_final
            )
        )

        if short_result.get(
            "ok"
        ):

            produto_html[
                "offerLink"
            ] = short_result.get(
                "shortLink"
            )

            short_link = (
                short_result.get(
                    "shortLink"
                )
            )

        else:

            produto_html[
                "offerLink"
            ] = url_final

            short_link = None

        return {

            "ok": True,

            "produto":
                produto_html,

            "url_final":
                url_final,

            "shortLink":
                short_link,

            "metodo":
                "HTML-Fallback"
        }

    # --------------------------------------------------------
    # 6. Erro detalhado
    # --------------------------------------------------------

    erro = (
        "Não foi possível obter os dados do produto."
    )

    if not shop_id:

        erro += (
            " shopId não foi identificado."
        )

    if not item_id:

        erro += (
            " itemId não foi identificado."
        )

    if shop_id and item_id:

        erro += (
            " Os IDs foram identificados, "
            "mas a Affiliate API não retornou "
            "uma oferta para esse produto."
        )

    return {

        "ok": False,

        "erro":
            erro,

        "url_final":
            url_final,

        "shopId":
            shop_id,

        "itemId":
            item_id,

        "html_bytes":
            len(html)
    }


# ============================================================
# FORMATAR PREÇO
# ============================================================

def formatar_preco(valor):

    if valor is None:

        return ""

    texto = str(
        valor
    ).strip()

    if not texto:

        return ""

    if texto.upper().startswith(
        "R$"
    ):

        return texto

    try:

        numero = float(
            texto.replace(
                ",",
                "."
            )
        )

        return (
            "R$ "
            + f"{numero:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except Exception:

        return texto


# ============================================================
# FORMATAR OFERTA
# ============================================================

def formatar_oferta(
    produto,
    link
):

    nome = (
        produto.get(
            "productName"
        )
        or
        produto.get(
            "name"
        )
        or
        "Oferta Shopee"
    )

    preco = (
        produto.get(
            "price"
        )
        or
        produto.get(
            "priceMin"
        )
        or
        produto.get(
            "priceMax"
        )
        or
        ""
    )

    imagem = (
        produto.get(
            "imageUrl"
        )
        or
        ""
    )

    offer_link = (
        produto.get(
            "offerLink"
        )
        or
        link
    )

    preco_formatado = (
        formatar_preco(
            preco
        )
    )

    linhas = [

        "🦊🔥 OFERTA SHOPEE",

        "",

        f"🛍️ {nome}"
    ]

    if preco_formatado:

        linhas.extend([

            "",

            f"💰 {preco_formatado}"
        ])

    linhas.extend([

        "",

        f"🔗 {offer_link}",

        "",

        "⚡ Raposa Caçadora"
    ])

    return {

        "texto":
            "\n".join(
                linhas
            ),

        "imagem":
            imagem,

        "link":
            offer_link
    }


# ============================================================
# PROCESSAR PRODUTO
# ============================================================

def processar_produto(
    link,
    task_id,
    numero,
    total
):

    print("=" * 70)
    print(
        f"[TASK] PRODUTO {numero}/{total}"
    )
    print(
        "[TASK] LINK:",
        link
    )
    print("=" * 70)

    resultado = obter_produto(
        link
    )

    if not resultado.get(
        "ok"
    ):

        print(
            "[PRODUTO] FALHA:",
            resultado.get(
                "erro"
            )
        )

        return {

            "ok": False,

            "erro":
                resultado.get(
                    "erro"
                ),

            "link":
                link,

            "url_final":
                resultado.get(
                    "url_final"
                ),

            "shopId":
                resultado.get(
                    "shopId"
                ),

            "itemId":
                resultado.get(
                    "itemId"
                ),

            "shortLink":
                resultado.get(
                    "shortLink"
                )
        }

    produto = (
        resultado[
            "produto"
        ]
    )

    oferta = formatar_oferta(
        produto,
        link
    )

    print(
        "[TELEGRAM] PRODUTO:",
        produto.get(
            "productName"
        )
    )

    print(
        "[TELEGRAM] PREÇO:",
        produto.get(
            "price"
        )
    )

    print(
        "[TELEGRAM] IMAGEM:",
        oferta.get(
            "imagem"
        )
    )

    print(
        "[TELEGRAM] LINK:",
        oferta.get(
            "link"
        )
    )

    # --------------------------------------------------------
    # Primeiro tenta foto
    # --------------------------------------------------------

    if oferta.get(
        "imagem"
    ):

        print(
            "[TELEGRAM] Tentando enviar FOTO..."
        )

        telegram_result = (
            telegram_enviar_foto(
                oferta["imagem"],
                oferta["texto"]
            )
        )

        if telegram_result.get(
            "ok"
        ):

            print(
                "[TELEGRAM] FOTO ENVIADA COM SUCESSO."
            )

            return {

                "ok": True,

                "produto":
                    produto,

                "shortLink":
                    resultado.get(
                        "shortLink"
                    ),

                "metodo":
                    resultado.get(
                        "metodo"
                    ),

                "telegram":
                    telegram_result
            }

        print(
            "[TELEGRAM] FOTO FALHOU:",
            telegram_result
        )

    # --------------------------------------------------------
    # Fallback texto
    # --------------------------------------------------------

    print(
        "[TELEGRAM] Tentando enviar TEXTO..."
    )

    telegram_result = (
        telegram_enviar_mensagem(
            oferta["texto"]
        )
    )

    if telegram_result.get(
        "ok"
    ):

        print(
            "[TELEGRAM] TEXTO ENVIADO COM SUCESSO."
        )

        return {

            "ok": True,

            "produto":
                produto,

            "shortLink":
                resultado.get(
                    "shortLink"
                ),

            "metodo":
                resultado.get(
                    "metodo"
                ),

            "telegram":
                telegram_result,

            "observacao":
                "Imagem falhou; mensagem enviada como texto."
        }

    return {

        "ok": False,

        "erro":
            "Produto encontrado, mas "
            "Telegram recusou a publicação.",

        "produto":
            produto,

        "shortLink":
            resultado.get(
                "shortLink"
            ),

        "telegram":
            telegram_result
    }


# ============================================================
# THREAD DA TAREFA
# ============================================================

def executar_tarefa(
    task_id,
    links,
    intervalo,
    quantidade
):

    print("=" * 70)
    print(
        "[TASK] INICIANDO:",
        task_id
    )
    print("=" * 70)

    resultados = []

    try:

        total = min(
            quantidade,
            len(links)
        )

        atualizar_tarefa(

            task_id,

            status="processando",

            total=total,

            processados=0
        )

        for indice in range(
            total
        ):

            link = links[
                indice
            ]

            resultado = (
                processar_produto(

                    link=link,

                    task_id=task_id,

                    numero=indice + 1,

                    total=total
                )
            )

            resultados.append(
                resultado
            )

            atualizar_tarefa(

                task_id,

                processados=
                    indice + 1,

                ultimo_resultado=
                    resultado
            )

            if (
                indice + 1 < total
                and
                intervalo > 0
            ):

                print(
                    f"[TASK] Aguardando "
                    f"{intervalo}s..."
                )

                time.sleep(
                    intervalo
                )

        sucessos = sum(

            1

            for resultado
            in resultados

            if resultado.get(
                "ok"
            )
        )

        falhas = (
            len(resultados)
            - sucessos
        )

        atualizar_tarefa(

            task_id,

            status="concluida",

            sucessos=
                sucessos,

            falhas=
                falhas,

            resultados=
                resultados,

            finalizada_em=
                int(time.time())
        )

        print(
            "[TASK] FINALIZADA:",
            task_id
        )

    except Exception as erro:

        print(
            "[TASK] ERRO:",
            repr(erro)
        )

        atualizar_tarefa(

            task_id,

            status="erro",

            erro=
                str(erro),

            resultados=
                resultados,

            finalizada_em=
                int(time.time())
        )


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

    resultado = (
        telegram_get_me()
    )

    bot = None

    if resultado.get(
        "ok"
    ):

        bot = resultado.get(
            "result"
        )

    return jsonify({

        "BOT_TOKEN": {

            "existe":
                bool(token),

            "tamanho":
                len(token),

            "mascara":
                mascara_valor(token)
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
                if bot
                else None,

            "is_bot":
                bot.get("is_bot")
                if bot
                else None,

            "first_name":
                bot.get("first_name")
                if bot
                else None,

            "username":
                bot.get("username")
                if bot
                else None
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

    return jsonify({

        "configuracao": {

            "SHOPEE_API_URL": {

                "existe":
                    bool(
                        SHOPEE_API_URL
                    ),

                "tamanho":
                    len(
                        SHOPEE_API_URL
                    ),

                "valor":
                    SHOPEE_API_URL
            },

            "SHOPEE_APP_ID":
                debug_variavel(
                    "SHOPEE_APP_ID"
                ),

            "SHOPEE_SECRET":
                debug_variavel(
                    "SHOPEE_SECRET"
                )
        },

        "validacao": {

            "api_url_configurada":
                bool(
                    SHOPEE_API_URL
                ),

            "app_id_configurado":
                bool(
                    SHOPEE_APP_ID
                ),

            "secret_configurado":
                bool(
                    SHOPEE_SECRET
                ),

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
            int(time.time())
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
      itemId
      productName
      price
      priceMin
      priceMax
      imageUrl
      offerLink
      productLink
      shopId
      shopName
    }
  }
}
"""

    resultado = shopee_graphql(
        query=query,
        operation_name=None
    )

    if resultado.get(
        "ok"
    ):

        return jsonify({

            "sucesso":
                True,

            "http_status":
                resultado.get(
                    "http_status"
                ),

            "dados":
                resultado.get(
                    "dados"
                )
        })

    return jsonify({

        "sucesso":
            False,

        "http_status":
            resultado.get(
                "http_status"
            ),

        "erro":
            resultado.get(
                "erro"
            ),

        "dados":
            resultado.get(
                "dados"
            )
    })


# ============================================================
# DEBUG PRODUTO
# ============================================================

@app.route(
    "/debug-produto",
    methods=["GET"]
)
def debug_produto():

    link = (

        request.args.get(
            "link"
        )

        or

        request.args.get(
            "url"
        )

        or

        ""
    ).strip()

    if not link:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "Informe ?link=https://..."
        }), 400

    print(
        "[DEBUG PRODUTO] LINK:",
        link
    )

    resultado = obter_produto(
        link
    )

    return jsonify({

        "sucesso":
            resultado.get(
                "ok",
                False
            ),

        "erro":
            resultado.get(
                "erro"
            ),

        "produto":
            resultado.get(
                "produto"
            ),

        "url_final":
            resultado.get(
                "url_final"
            ),

        "shortLink":
            resultado.get(
                "shortLink"
            ),

        "metodo":
            resultado.get(
                "metodo"
            ),

        "shopId":
            resultado.get(
                "shopId"
            ),

        "itemId":
            resultado.get(
                "itemId"
            ),

        "html_bytes":
            resultado.get(
                "html_bytes"
            )
    })


# ============================================================
# DEBUG RESOLUÇÃO
# ============================================================

@app.route(
    "/debug-resolver",
    methods=["GET"]
)
def debug_resolver():

    link = (

        request.args.get(
            "link"
        )

        or

        request.args.get(
            "url"
        )

        or

        ""
    ).strip()

    if not link:

        return jsonify({

            "sucesso":
                False,

            "erro":
                "Informe ?link=https://..."
        }), 400

    resultado = (
        resolver_url_shopee(
            link
        )
    )

    shop_id, item_id = (
        extrair_ids_shopee(
            resultado.get(
                "url"
            )
        )
    )

    return jsonify({

        "sucesso":
            resultado.get(
                "ok",
                False
            ),

        "url_original":
            link,

        "url_final":
            resultado.get(
                "url"
            ),

        "shopId":
            shop_id,

        "itemId":
            item_id,

        "html_bytes":
            len(
                resultado.get(
                    "html",
                    ""
                )
            ),

        "content_type":
            resultado.get(
                "headers",
                {}
            ).get(
                "Content-Type"
            ),

        "cookies":
            resultado.get(
                "cookies",
                {}
            ),

        "historico":
            resultado.get(
                "history",
                []
            )
    })


# ============================================================
# DEBUG TELEGRAM PUBLICAÇÃO
# ============================================================

@app.route(
    "/debug-telegram-publicar",
    methods=["GET"]
)
def debug_telegram_publicar():

    resultado = (
        telegram_enviar_mensagem(

            "🦊 TESTE — Raposa Caçadora\n\n"
            "O bot conseguiu publicar uma "
            "mensagem no canal configurado."
        )
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

        "telegram": {

            "configurado":
                bool(
                    BOT_TOKEN
                ),

            "canal_configurado":
                bool(
                    CHANNEL_USERNAME
                )
        },

        "shopee": {

            "api_url_configurada":
                bool(
                    SHOPEE_API_URL
                ),

            "app_id_configurado":
                bool(
                    SHOPEE_APP_ID
                ),

            "secret_configurado":
                bool(
                    SHOPEE_SECRET
                ),

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
                BOT_TOKEN
            ),

        "shopee_configurada":
            bool(
                SHOPEE_APP_ID
                and
                SHOPEE_SECRET
            ),

        "timestamp":
            int(time.time())
    })


# ============================================================
# CONFIGURAR AUTOMAÇÃO
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    print("=" * 70)
    print("[API] POST /api/configurar")
    print("=" * 70)

    try:

        dados = request.get_json(
            silent=True
        )

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

        if not isinstance(
            links,
            list
        ):

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "O campo links deve ser uma lista."
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

        if intervalo not in (
            INTERVALOS_PERMITIDOS
        ):

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "Intervalo inválido."
            }), 400

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

        if quantidade > len(
            links
        ):

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "A quantidade não pode ser maior "
                    "que o número de links."
            }), 400

        if quantidade > MAX_LINKS:

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "Máximo de 20 postagens."
            }), 400

        # ----------------------------------------------------
        # Validação antecipada
        # ----------------------------------------------------

        if not BOT_TOKEN:

            print(
                "[API] AVISO: BOT_TOKEN não configurado."
            )

        if not CHANNEL_USERNAME:

            print(
                "[API] AVISO: CHANNEL_USERNAME não configurado."
            )

        if not SHOPEE_APP_ID:

            print(
                "[API] AVISO: SHOPEE_APP_ID não configurado."
            )

        if not SHOPEE_SECRET:

            print(
                "[API] AVISO: SHOPEE_SECRET não configurado."
            )

        task_id = str(
            uuid.uuid4()
        )

        with tarefas_lock:

            tarefas[task_id] = {

                "task_id":
                    task_id,

                "status":
                    "iniciando",

                "links":
                    links,

                "intervalo":
                    intervalo,

                "quantidade":
                    quantidade,

                "usuario":
                    usuario,

                "criada_em":
                    int(
                        time.time()
                    )
            }

        thread = threading.Thread(

            target=
                executar_tarefa,

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
            "[API] TASK CRIADA:",
            task_id
        )

        return jsonify({

            "sucesso":
                True,

            "mensagem":
                "Automação iniciada.",

            "task_id":
                task_id
        })

    except Exception as erro:

        print(
            "[API] ERRO:",
            repr(erro)
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
