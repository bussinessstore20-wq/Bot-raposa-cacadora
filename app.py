import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re

from urllib.parse import (
    urlparse,
    parse_qs,
    unquote,
    urljoin
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
        )

        return (
            host == "shopee.com.br"
            or
            host.endswith(
                ".shopee.com.br"
            )
            or
            host == "s.shopee.com.br"
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

        return resposta.json()

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
            telegram_api_url(
                "sendMessage"
            ),
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
                "erro": resposta.text[:1000]
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

    try:

        resposta = requests.post(
            telegram_api_url(
                "sendPhoto"
            ),
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
                "erro": resposta.text[:1000]
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

        payload_obj[
            "operationName"
        ] = operation_name

    if variables is not None:

        payload_obj[
            "variables"
        ] = variables

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

        "Authorization":
            signature_header,

        "User-Agent":
            "Raposa-Cacadora/2.0"
    }

    print("=" * 60)
    print("[SHOPEE API] GraphQL")
    print(
        "[SHOPEE API] URL:",
        SHOPEE_API_URL
    )
    print(
        "[SHOPEE API] AppID:",
        mascara_valor(
            SHOPEE_APP_ID
        )
    )
    print(
        "[SHOPEE API] Timestamp:",
        timestamp
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
    print(
        "[SHOPEE API] Signature:",
        mascara_valor(
            assinatura
        )
    )
    print("=" * 60)

    try:

        resposta = requests.post(
            SHOPEE_API_URL,
            headers=headers,
            data=payload.encode(
                "utf-8"
            ),
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
                    "Resposta não é JSON.",
                "texto":
                    resposta.text[:5000]
            }

        if resposta.status_code != 200:

            return {
                "ok": False,
                "http_status":
                    resposta.status_code,
                "dados":
                    dados,
                "erro":
                    "HTTP diferente de 200."
            }

        if dados.get("errors"):

            return {
                "ok": False,
                "http_status":
                    resposta.status_code,
                "dados":
                    dados,
                "erro":
                    dados["errors"]
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
# GERAR SHORT LINK
# ============================================================

def shopee_generate_short_link(
    origin_url
):

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

    if not resultado.get("ok"):

        return {
            "ok": False,
            "erro":
                resultado.get(
                    "erro"
                ),
            "dados":
                resultado.get(
                    "dados"
                )
        }

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
            "ok": False,
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
        "ok": True,
        "shortLink":
            short_link,
        "dados":
            dados
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
            "pt-BR,pt;q=0.9",

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache"
    })

    return session


def resolver_url_shopee(link):

    print("=" * 60)
    print(
        "[SHOPEE] Tentando resolver URL:"
    )
    print(link)
    print("=" * 60)

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

        print(
            "[SHOPEE] HTTP:",
            resposta.status_code
        )

        print(
            "[SHOPEE] URL final:",
            url_final
        )

        print(
            "[SHOPEE] Histórico:",
            [
                {
                    "status":
                        r.status_code,
                    "url":
                        r.url,
                    "location":
                        r.headers.get(
                            "Location"
                        )
                }
                for r in resposta.history
            ]
        )

        print(
            "[SHOPEE] Content-Type:",
            resposta.headers.get(
                "Content-Type"
            )
        )

        print(
            "[SHOPEE] HTML recebido:",
            len(html),
            "bytes"
        )

        # ----------------------------------------------------
        # Procura URLs de produto dentro da própria resposta.
        # ----------------------------------------------------

        urls_encontradas = []

        padroes_url = [

            r'https?://[^"\']*shopee\.com\.br/[^"\']+',

            r'["\']([^"\']*shopee\.com\.br/[^"\']+)["\']',

            r'productLink["\']?\s*[:=]\s*["\']([^"\']+)["\']',

            r'canonical["\']?\s*[:=]\s*["\']([^"\']+)["\']'
        ]

        for padrao in padroes_url:

            try:

                encontrados = re.findall(
                    padrao,
                    html,
                    re.IGNORECASE
                )

                if isinstance(
                    encontrados,
                    list
                ):

                    for url in encontrados:

                        if isinstance(
                            url,
                            tuple
                        ):
                            url = url[0]

                        url = (
                            str(url)
                            .replace(
                                "\\/",
                                "/"
                            )
                            .replace(
                                "\\u002F",
                                "/"
                            )
                        )

                        if (
                            "shopee.com.br"
                            in url.lower()
                        ):

                            urls_encontradas.append(
                                url
                            )

            except Exception:
                pass

        # Remove duplicados.
        urls_limpos = []

        for url in urls_encontradas:

            url = normalizar_url(
                url
            )

            if url not in urls_limpos:

                urls_limpos.append(
                    url
                )

        print(
            "[SHOPEE] URLs encontradas no HTML:",
            len(urls_limpos)
        )

        return {
            "ok": resposta.ok,
            "url": url_final,
            "html": html,
            "headers":
                dict(resposta.headers),
            "cookies":
                session.cookies.get_dict(),
            "urls_html":
                urls_limpos,
            "history":
                resposta.history
        }

    except Exception as erro:

        print(
            "[SHOPEE] Erro ao resolver:",
            erro
        )

        return {
            "ok": False,
            "url": link,
            "html": "",
            "headers": {},
            "cookies": {},
            "urls_html": [],
            "history": [],
            "erro": str(erro)
        }


# ============================================================
# EXTRAÇÃO DE IDS
# ============================================================

def extrair_ids_shopee(url):

    print(
        "[SHOPEE] Extraindo IDs de:",
        url
    )

    if not url:
        return None, None

    shop_id = None
    item_id = None

    url = normalizar_url(
        url
    )

    # --------------------------------------------------------
    # Formato:
    # /product/123/456
    # --------------------------------------------------------

    padroes = [

        r"/product/"
        r"(\d+)"
        r"/"
        r"(\d+)",

        # Formato tradicional:
        # ...-i.123456.789012

        r"-i\.(\d+)\.(\d+)",

        # Algumas URLs:
        # /123456/789012

        r"/(\d{5,})/(\d{5,})(?:[/?#]|$)"
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

            break

    # --------------------------------------------------------
    # Query string
    # --------------------------------------------------------

    if not shop_id or not item_id:

        try:

            parsed = urlparse(
                url
            )

            params = parse_qs(
                parsed.query
            )

            possiveis_shop = [
                "shopid",
                "shopId",
                "shop_id"
            ]

            possiveis_item = [
                "itemid",
                "itemId",
                "item_id"
            ]

            for chave in possiveis_shop:

                if (
                    chave in params
                    and
                    params[chave]
                ):

                    shop_id = (
                        params[chave][0]
                    )
                    break

            for chave in possiveis_item:

                if (
                    chave in params
                    and
                    params[chave]
                ):

                    item_id = (
                        params[chave][0]
                    )
                    break

        except Exception:
            pass

    if shop_id or item_id:

        print(
            "[SHOPEE] IDs encontrados:",
            shop_id,
            item_id
        )

    else:

        print(
            "[SHOPEE] Nenhum shopId/itemId encontrado."
        )

    return shop_id, item_id


# ============================================================
# EXTRAIR METADADOS HTML
# ============================================================

def extrair_meta(html, propriedade):

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

            if (
                tipo != "Product"
                and
                not (
                    isinstance(
                        tipo,
                        list
                    )
                    and
                    "Product" in tipo
                )
            ):
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
                    offers.get(
                        "price"
                    )
                    or
                    offers.get(
                        "lowPrice"
                    )
                    or
                    ""
                )

            elif isinstance(
                offers,
                list
            ):

                if offers:

                    preco = (
                        offers[0].get(
                            "price"
                        )
                        or
                        offers[0].get(
                            "lowPrice"
                        )
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
# EXTRAIR PRODUTO DO HTML
# ============================================================

def extrair_produto_html(
    html,
    url_final,
    short_link=None
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

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    produto_jsonld = (
        extrair_produto_jsonld(
            html
        )
    )

    if produto_jsonld:

        if produto_jsonld.get(
            "productName"
        ):

            titulo = (
                produto_jsonld.get(
                    "productName"
                )
                or titulo
            )

        imagem = (
            produto_jsonld.get(
                "imageUrl"
            )
            or imagem
        )

        preco = (
            produto_jsonld.get(
                "price"
            )
            or ""
        )

    else:

        preco = ""

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

    # --------------------------------------------------------
    # Detecta homepage / página genérica
    # --------------------------------------------------------

    titulo_lower = (
        titulo.lower()
        if titulo
        else ""
    )

    pagina_generica = False

    termos_genericos = [

        "shopee brasil | ofertas incríveis",
        "shopee brasil | ofertas incriveis",
        "shopee brasil",
        "ofertas incríveis. melhores preços",
        "ofertas incriveis. melhores preços"
    ]

    for termo in termos_genericos:

        if termo in titulo_lower:

            pagina_generica = True
            break

    if pagina_generica:

        print(
            "[PRODUTO] HTML corresponde à "
            "página genérica da Shopee."
        )

        return None

    # --------------------------------------------------------
    # Validação mínima
    # --------------------------------------------------------

    if not titulo:

        return None

    # Evita aceitar textos claramente inválidos.

    if len(titulo) < 3:

        return None

    produto = {

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
            descricao or "",

        "offerLink":
            short_link or url_final,

        "productLink":
            url_final,

        "shopId":
            None,

        "shopName":
            ""
    }

    print(
        "[PRODUTO] Produto extraído do HTML:"
    )

    print(
        "[PRODUTO] Título:",
        titulo
    )

    print(
        "[PRODUTO] Preço:",
        preco
    )

    print(
        "[PRODUTO] Imagem:",
        imagem
    )

    return produto


# ============================================================
# PRODUCT OFFER V2
# ============================================================

def shopee_buscar_por_keyword(
    keyword
):

    if not keyword:
        return []

    query = """
query SearchProducts($keyword: String!) {
  productOfferV2(
    keyword: $keyword
    sortType: 1
    page: 1
    limit: 10
  ) {
    nodes {
      productName
      price
      priceMin
      priceMax
      commissionRate
      commission
      imageUrl
      offerLink
      shopId
      shopName
      productLink
    }
  }
}
"""

    resultado = shopee_graphql(
        query=query,
        variables={
            "keyword": keyword
        },
        operation_name="SearchProducts"
    )

    if not resultado.get(
        "ok"
    ):

        return []

    try:

        return (
            resultado
            ["dados"]
            ["data"]
            ["productOfferV2"]
            ["nodes"]
        )

    except Exception:

        return []


# ============================================================
# BUSCAR POR LINK
# ============================================================

def shopee_buscar_produto_por_link(
    link
):

    """
    IMPORTANTE:

    Não trata mais o código de um short-link
    como keyword de produto.

    Esta função só tenta uma correspondência
    quando o link fornecido já possui dados de
    produto reconhecíveis.
    """

    if not link:
        return {
            "ok": False,
            "erro": "Link vazio."
        }

    shop_id, item_id = (
        extrair_ids_shopee(
            link
        )
    )

    if not (
        shop_id
        and
        item_id
    ):

        return {
            "ok": False,
            "erro":
                "URL não contém shopId/itemId."
        }

    print(
        "[SHOPEE] URL possui IDs:",
        shop_id,
        item_id
    )

    # ProductOfferV2 não deve ser alimentado
    # com o código do short-link.

    return {
        "ok": False,
        "erro":
            "Consulta direta por IDs não "
            "está implementada nesta etapa."
    }


# ============================================================
# OBTER PRODUTO
# ============================================================

def obter_produto(link):

    print("=" * 60)
    print(
        "[PRODUTO] Abrindo link:"
    )
    print(link)
    print("=" * 60)

    # --------------------------------------------------------
    # Validação
    # --------------------------------------------------------

    if not url_eh_shopee(
        link
    ):

        return {
            "ok": False,
            "erro":
                "O link informado não parece ser "
                "uma URL válida da Shopee."
        }

    # --------------------------------------------------------
    # Resolver URL
    # --------------------------------------------------------

    resolucao = resolver_url_shopee(
        link
    )

    url_final = (
        resolucao.get(
            "url"
        )
        or link
    )

    html = (
        resolucao.get(
            "html"
        )
        or ""
    )

    print(
        "[PRODUTO] URL final:",
        url_final
    )

    # --------------------------------------------------------
    # Extrair IDs
    # --------------------------------------------------------

    shop_id, item_id = (
        extrair_ids_shopee(
            url_final
        )
    )

    print(
        "[PRODUTO] shopId:",
        shop_id
    )

    print(
        "[PRODUTO] itemId:",
        item_id
    )

    # --------------------------------------------------------
    # URLs encontradas no HTML
    # --------------------------------------------------------

    urls_html = (
        resolucao.get(
            "urls_html"
        )
        or []
    )

    for url_encontrada in urls_html:

        shop_tmp, item_tmp = (
            extrair_ids_shopee(
                url_encontrada
            )
        )

        if shop_tmp and item_tmp:

            print(
                "[PRODUTO] URL de produto encontrada "
                "dentro do HTML:"
            )

            print(
                url_encontrada
            )

            shop_id = shop_tmp
            item_id = item_tmp

            # Tenta extrair novamente caso
            # o HTML contenha metadados associados
            # ao produto.

            produto_html = (
                extrair_produto_html(
                    html=html,
                    url_final=url_encontrada,
                    short_link=None
                )
            )

            if produto_html:

                produto_html[
                    "shopId"
                ] = shop_id

                return {
                    "ok": True,
                    "produto":
                        produto_html,
                    "url_final":
                        url_encontrada,
                    "shortLink":
                        None,
                    "metodo":
                        "HTML-URL-interna"
                }

    # --------------------------------------------------------
    # Tentar extrair diretamente do HTML
    # --------------------------------------------------------

    produto_html = (
        extrair_produto_html(
            html=html,
            url_final=url_final,
            short_link=None
        )
    )

    if produto_html:

        produto_html[
            "shopId"
        ] = shop_id

        return {
            "ok": True,
            "produto":
                produto_html,
            "url_final":
                url_final,
            "shortLink":
                None,
            "metodo":
                "HTML"
        }

    # --------------------------------------------------------
    # Se temos uma URL de produto reconhecida,
    # podemos gerar o link de afiliado.
    # --------------------------------------------------------

    if shop_id and item_id:

        print(
            "[PRODUTO] Produto possui IDs."
        )

        short_result = (
            shopee_generate_short_link(
                url_final
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

            return {
                "ok": False,
                "erro":
                    "A Shopee confirmou uma URL "
                    "de produto, mas não foi possível "
                    "extrair os dados do produto.",
                "url_final":
                    url_final,
                "shortLink":
                    short_link,
                "shopId":
                    shop_id,
                "itemId":
                    item_id
            }

    # --------------------------------------------------------
    # NÃO fazer mais:
    #
    # ProductOfferV2(keyword="6fh9sJaQiJ")
    #
    # nem:
    #
    # ProductOfferV2(keyword="https://s...")
    #
    # Isso não resolve short-links.
    # --------------------------------------------------------

    return {
        "ok": False,
        "erro":
            "A Shopee não retornou os dados do produto. "
            "O short-link não foi convertido em uma "
            "página de produto pelo servidor.",
        "url_final":
            url_final,
        "shortLink":
            None
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

    # Já está formatado.
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
            .replace(
                ",",
                "X"
            )
            .replace(
                ".",
                ","
            )
            .replace(
                "X",
                "."
            )
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

    print("=" * 60)

    print(
        f"[TASK] Produto "
        f"{numero}/{total}"
    )

    print(
        "[TELEGRAM] Link:",
        link
    )

    print("=" * 60)

    resultado = obter_produto(
        link
    )

    if not resultado.get(
        "ok"
    ):

        print(
            "[PRODUTO] Falha:",
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
        "[TELEGRAM] Publicando:",
        produto.get(
            "productName"
        )
    )

    print(
        "[TELEGRAM] Link:",
        oferta["link"]
    )

    # --------------------------------------------------------
    # COM IMAGEM
    # --------------------------------------------------------

    if oferta["imagem"]:

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
                "[TELEGRAM] Produto "
                "publicado com imagem."
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
            "[TELEGRAM] Falha ao "
            "publicar imagem."
        )

    # --------------------------------------------------------
    # FALLBACK TEXTO
    # --------------------------------------------------------

    telegram_result = (
        telegram_enviar_mensagem(
            oferta["texto"]
        )
    )

    if telegram_result.get(
        "ok"
    ):

        print(
            "[TELEGRAM] Produto "
            "publicado como texto."
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

    return {

        "ok": False,

        "erro":
            "Produto encontrado, "
            "mas não foi possível "
            "publicar no Telegram.",

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

    print("=" * 40)

    print(
        "[TASK] Iniciando",
        task_id
    )

    print("=" * 40)

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
                processados=indice + 1,
                ultimo_resultado=resultado
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
            "[TASK] Finalizada",
            task_id
        )

    except Exception as erro:

        print(
            "[TASK] ERRO:",
            erro
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
                mascara_valor(
                    token
                )
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
                bot.get(
                    "id"
                )
                if bot
                else None,

            "is_bot":
                bot.get(
                    "is_bot"
                )
                if bot
                else None,

            "first_name":
                bot.get(
                    "first_name"
                )
                if bot
                else None,

            "username":
                bot.get(
                    "username"
                )
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
      productName
      price
      imageUrl
      offerLink
      shopId
      shopName
      productLink
    }
  }
}
"""

    resultado = shopee_graphql(
        query=query
    )

    if resultado.get(
        "ok"
    ):

        dados = resultado.get(
            "dados",
            {}
        )

        return jsonify({

            "sucesso":
                True,

            "http_status":
                resultado.get(
                    "http_status"
                ),

            "tem_dados":
                bool(dados),

            "dados":
                dados
        })

    return jsonify({

        "sucesso":
            False,

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
        "[DEBUG PRODUTO] Link:",
        link
    )

    resultado = obter_produto(
        link
    )

    if resultado.get(
        "ok"
    ):

        return jsonify({

            "sucesso":
                True,

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
                )
        })

    return jsonify({

        "sucesso":
            False,

        "erro":
            resultado.get(
                "erro"
            ),

        "url_final":
            resultado.get(
                "url_final"
            ),

        "shortLink":
            resultado.get(
                "shortLink"
            ),

        "shopId":
            resultado.get(
                "shopId"
            ),

        "itemId":
            resultado.get(
                "itemId"
            )
    })


# ============================================================
# DEBUG RESOLUÇÃO SHOPEE
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

    historico = []

    for resposta in (
        resultado.get(
            "history",
            []
        )
    ):

        historico.append({

            "status":
                resposta.status_code,

            "url":
                resposta.url,

            "location":
                resposta.headers.get(
                    "Location"
                )
        })

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
            historico,

        "urls_encontradas_html":
            resultado.get(
                "urls_html",
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

    print("=" * 40)

    print(
        "[API] POST /api/configurar"
    )

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

        print(
            "[API] Links recebidos:",
            len(links)
            if isinstance(
                links,
                list
            )
            else "não é lista"
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
                    "A quantidade não pode ser "
                    "maior que o número de links."
            }), 400

        if quantidade > MAX_LINKS:

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "Máximo de 20 postagens."
            }), 400

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
            mascara_valor(
                SHOPEE_APP_ID
            )
        )

        print(
            "[SHOPEE] Secret configurado:",
            bool(
                SHOPEE_SECRET
            )
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
            "[API] Task criada:",
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
            erro
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
