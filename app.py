import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re
import html
from urllib.parse import urlparse, parse_qsl, urlencode

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

tarefas = {}
tarefas_lock = threading.Lock()


# ============================================================
# SESSÃO HTTP
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 15) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 "
        "Mobile Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})


# ============================================================
# DEBUG / SEGURANÇA
# ============================================================

def mascara_valor(valor):
    if not valor:
        return ""

    valor = str(valor)

    if len(valor) <= 4:
        return "*" * len(valor)

    return (
        valor[:2]
        + ("*" * max(0, len(valor) - 4))
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


def telegram_request(metodo, payload=None, files=None):
    token = os.environ.get("BOT_TOKEN", "").strip()

    if not token:
        return {
            "ok": False,
            "description": "BOT_TOKEN não configurado."
        }

    try:
        if files:
            resposta = requests.post(
                telegram_api_url(metodo),
                data=payload or {},
                files=files,
                timeout=30
            )
        else:
            resposta = requests.post(
                telegram_api_url(metodo),
                json=payload or {},
                timeout=30
            )

        try:
            return resposta.json()
        except Exception:
            return {
                "ok": False,
                "description": resposta.text[:1000]
            }

    except Exception as erro:
        return {
            "ok": False,
            "description": str(erro)
        }


def telegram_get_me():

    if not BOT_TOKEN:
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


def telegram_publicar_texto(texto):

    if not BOT_TOKEN:
        print("[TELEGRAM] BOT_TOKEN não configurado.")
        return False

    if not CHANNEL_USERNAME:
        print("[TELEGRAM] CHANNEL_USERNAME não configurado.")
        return False

    print("[TELEGRAM] Publicando mensagem de texto...")

    resultado = telegram_request(
        "sendMessage",
        {
            "chat_id": CHANNEL_USERNAME,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
    )

    print(
        "[TELEGRAM] Resultado:",
        json.dumps(resultado, ensure_ascii=False)[:2000]
    )

    return bool(resultado.get("ok"))


def telegram_publicar_foto(imagem, legenda):

    if not BOT_TOKEN:
        print("[TELEGRAM] BOT_TOKEN não configurado.")
        return False

    if not CHANNEL_USERNAME:
        print("[TELEGRAM] CHANNEL_USERNAME não configurado.")
        return False

    try:
        print("[TELEGRAM] Baixando imagem:")
        print(imagem)

        resposta = session.get(
            imagem,
            timeout=30
        )

        print(
            "[TELEGRAM] HTTP imagem:",
            resposta.status_code
        )

        if resposta.status_code != 200:
            print("[TELEGRAM] Não foi possível baixar a imagem.")
            return False

        content_type = resposta.headers.get(
            "Content-Type",
            ""
        )

        print(
            "[TELEGRAM] Content-Type:",
            content_type
        )

        if not resposta.content:
            print("[TELEGRAM] Imagem vazia.")
            return False

        arquivos = {
            "photo": (
                "produto.jpg",
                resposta.content,
                content_type or "image/jpeg"
            )
        }

        dados = {
            "chat_id": CHANNEL_USERNAME,
            "caption": legenda,
            "parse_mode": "HTML"
        }

        resultado = telegram_request(
            "sendPhoto",
            payload=dados,
            files=arquivos
        )

        print(
            "[TELEGRAM] Resultado foto:",
            json.dumps(resultado, ensure_ascii=False)[:2000]
        )

        return bool(resultado.get("ok"))

    except Exception as erro:

        print(
            "[TELEGRAM] Erro ao publicar foto:",
            repr(erro)
        )

        return False


# ============================================================
# VALIDAÇÃO DE LINK
# ============================================================

def link_shopee_valido(link):

    if not link:
        return False

    try:

        parsed = urlparse(link)

        if parsed.scheme not in ("http", "https"):
            return False

        hostname = (
            parsed.hostname or ""
        ).lower()

        return (
            "shopee" in hostname
        )

    except Exception:
        return False


# ============================================================
# RESOLVER LINK SHOPEE
# ============================================================

def resolver_link_shopee(link):

    print("=" * 40)
    print("[SHOPEE] Tentando resolver URL:")
    print(link)
    print("=" * 40)

    headers = {
        "User-Agent": session.headers["User-Agent"],
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9"
    }

    try:

        resposta = session.get(
            link,
            headers=headers,
            allow_redirects=True,
            timeout=30
        )

        print(
            "[SHOPEE] HTTP:",
            resposta.status_code
        )

        print(
            "[SHOPEE] URL final:",
            resposta.url
        )

        return resposta.url, resposta.text

    except Exception as erro:

        print(
            "[SHOPEE] Erro resolvendo:",
            repr(erro)
        )

        return link, ""


# ============================================================
# EXTRAÇÃO DE IDs
# ============================================================

def extrair_ids_shopee(url, html_text=""):

    print("[SHOPEE] Extraindo IDs...")

    textos = [
        url or "",
        html_text or ""
    ]

    shop_id = None
    item_id = None

    padroes = [

        r'"shopid"\s*:\s*(\d+)',
        r'"shop_id"\s*:\s*(\d+)',
        r'"shopId"\s*:\s*(\d+)',
        r'"shop_id"\s*:\s*"(\d+)"',

    ]

    for texto in textos:

        for padrao in padroes:

            encontrados = re.findall(
                padrao,
                texto,
                re.IGNORECASE
            )

            if encontrados:
                shop_id = encontrados[0]
                break

        if shop_id:
            break

    padroes_item = [

        r'"itemid"\s*:\s*(\d+)',
        r'"item_id"\s*:\s*(\d+)',
        r'"itemId"\s*:\s*(\d+)',
        r'"item_id"\s*:\s*"(\d+)"',

    ]

    for texto in textos:

        for padrao in padroes_item:

            encontrados = re.findall(
                padrao,
                texto,
                re.IGNORECASE
            )

            if encontrados:
                item_id = encontrados[0]
                break

        if item_id:
            break

    # ========================================================
    # TENTATIVA POR URL
    # ========================================================

    try:

        parsed = urlparse(url)

        partes = [
            p for p in parsed.path.split("/")
            if p
        ]

        # Alguns formatos da Shopee aparecem como:
        #
        # produto-nome.i.SHOP_ID.ITEM_ID
        #
        # ou:
        #
        # -i.SHOP_ID.ITEM_ID

        texto_url = parsed.path

        encontrados = re.findall(
            r"(?:i\.|-i\.)(\d+)\.(\d+)",
            texto_url
        )

        if encontrados:

            shop_id = shop_id or encontrados[0][0]
            item_id = item_id or encontrados[0][1]

    except Exception:
        pass

    print(
        "[SHOPEE] shopId:",
        shop_id,
        "| itemId:",
        item_id
    )

    return shop_id, item_id


# ============================================================
# ASSINATURA SHOPEE
# ============================================================

def gerar_assinatura_shopee(payload_json, timestamp):

    """
    A API Affiliate usa assinatura HMAC.

    Mantemos a geração centralizada para facilitar debug.
    """

    if not SHOPEE_SECRET:
        raise RuntimeError(
            "SHOPEE_SECRET não configurado."
        )

    base = (
        f"{SHOPEE_APP_ID}"
        f"{timestamp}"
        f"{payload_json}"
    )

    assinatura = hmac.new(
        SHOPEE_SECRET.encode("utf-8"),
        base.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return assinatura


# ============================================================
# GRAPHQL SHOPEE
# ============================================================

def shopee_graphql(query, variables=None):

    if not SHOPEE_API_URL:
        print(
            "[SHOPEE API] SHOPEE_API_URL não configurada."
        )
        return None

    if not SHOPEE_APP_ID:
        print(
            "[SHOPEE API] SHOPEE_APP_ID não configurado."
        )
        return None

    if not SHOPEE_SECRET:
        print(
            "[SHOPEE API] SHOPEE_SECRET não configurado."
        )
        return None

    payload = {
        "query": query,
        "variables": variables or {}
    }

    payload_json = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False
    )

    timestamp = int(time.time())

    try:

        signature = gerar_assinatura_shopee(
            payload_json,
            timestamp
        )

    except Exception as erro:

        print(
            "[SHOPEE API] Erro assinatura:",
            repr(erro)
        )

        return None

    # ========================================================
    # HEADERS
    # ========================================================

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": (
            f"SHA256 Credential={SHOPEE_APP_ID},"
            f"Timestamp={timestamp},"
            f"Signature={signature}"
        )
    }

    print("=" * 40)
    print("[SHOPEE API] GraphQL")
    print("[SHOPEE API] URL:", SHOPEE_API_URL)
    print("[SHOPEE API] AppID:", mascara_valor(SHOPEE_APP_ID))
    print("[SHOPEE API] Timestamp:", timestamp)

    try:

        resposta = requests.post(
            SHOPEE_API_URL,
            headers=headers,
            data=payload_json.encode("utf-8"),
            timeout=30
        )

        print(
            "[SHOPEE API] HTTP:",
            resposta.status_code
        )

        print(
            "[SHOPEE API] Resposta:",
            resposta.text[:5000]
        )

        if resposta.status_code != 200:
            return None

        try:
            dados = resposta.json()
        except Exception:

            print(
                "[SHOPEE API] Resposta não é JSON."
            )

            return None

        if dados.get("errors"):

            print(
                "[SHOPEE API] GraphQL errors:",
                json.dumps(
                    dados["errors"],
                    ensure_ascii=False
                )[:5000]
            )

        return dados

    except Exception as erro:

        print(
            "[SHOPEE API] Exceção:",
            repr(erro)
        )

        return None


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

    dados = shopee_graphql(
        query,
        {
            "input": {
                "originUrl": origin_url
            }
        }
    )

    if not dados:
        return None

    try:

        short_link = (
            dados
            .get("data", {})
            .get("generateShortLink", {})
            .get("shortLink")
        )

        if short_link:

            print(
                "[SHOPEE API] ShortLink gerado:",
                short_link
            )

            return short_link

    except Exception as erro:

        print(
            "[SHOPEE API] Erro lendo ShortLink:",
            repr(erro)
        )

    return None


# ============================================================
# PRODUCT OFFER
# ============================================================

def consultar_product_offer(shop_id, item_id):

    if not shop_id or not item_id:

        print(
            "[PRODUTO] Não há IDs para consultar ProductOfferV2."
        )

        return None

    query = """
query ProductOffer($itemId: Int!, $shopId: Int!) {
  productOfferV2(
    itemId: $itemId
    shopId: $shopId
  ) {
    nodes {
      itemId
      shopId
      productName
      price
      priceMin
      priceMax
      imageUrl
      productLink
      offerLink
      commissionRate
      commission
      sellerName
    }
  }
}
"""

    print(
        "[PRODUTO] Consultando ProductOfferV2..."
    )

    try:

        resultado = shopee_graphql(
            query,
            {
                "itemId": int(item_id),
                "shopId": int(shop_id)
            }
        )

        if not resultado:
            return None

        if resultado.get("errors"):
            return None

        nodes = (
            resultado
            .get("data", {})
            .get("productOfferV2", {})
            .get("nodes", [])
        )

        if nodes:

            produto = nodes[0]

            print(
                "[PRODUTO] ProductOfferV2 encontrado:"
            )

            print(
                json.dumps(
                    produto,
                    ensure_ascii=False
                )[:5000]
            )

            return produto

    except Exception as erro:

        print(
            "[PRODUTO] Erro ProductOfferV2:",
            repr(erro)
        )

    return None


# ============================================================
# LIMPAR TEXTO
# ============================================================

def limpar_texto(valor):

    if valor is None:
        return ""

    valor = html.unescape(
        str(valor)
    )

    valor = re.sub(
        r"\s+",
        " ",
        valor
    )

    return valor.strip()


# ============================================================
# EXTRAIR JSON-LD
# ============================================================

def extrair_json_ld(soup):

    resultados = []

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        try:

            texto = script.string

            if not texto:
                continue

            dados = json.loads(
                texto
            )

            if isinstance(dados, list):
                resultados.extend(dados)

            else:
                resultados.append(dados)

        except Exception:
            continue

    return resultados


# ============================================================
# EXTRAIR PRODUTO DO HTML
# ============================================================

def extrair_produto_html(url, html_text):

    print("=" * 40)
    print("[HTML] Tentando extrair dados do produto...")
    print("=" * 40)

    if not html_text:

        print(
            "[HTML] HTML vazio."
        )

        return {}

    try:

        soup = BeautifulSoup(
            html_text,
            "html.parser"
        )

    except Exception as erro:

        print(
            "[HTML] Erro BeautifulSoup:",
            repr(erro)
        )

        return {}

    titulo = ""
    preco = ""
    preco_antigo = ""
    imagem = ""

    # ========================================================
    # TITLE
    # ========================================================

    meta_title = soup.find(
        "meta",
        attrs={
            "property": "og:title"
        }
    )

    if meta_title:

        titulo = (
            meta_title.get("content")
            or ""
        )

    if not titulo:

        meta_title = soup.find(
            "meta",
            attrs={
                "name": "twitter:title"
            }
        )

        if meta_title:

            titulo = (
                meta_title.get("content")
                or ""
            )

    if not titulo and soup.title:

        titulo = soup.title.get_text(
            " ",
            strip=True
        )

    # ========================================================
    # IMAGE
    # ========================================================

    meta_image = soup.find(
        "meta",
        attrs={
            "property": "og:image"
        }
    )

    if meta_image:

        imagem = (
            meta_image.get("content")
            or ""
        )

    if not imagem:

        meta_image = soup.find(
            "meta",
            attrs={
                "name": "twitter:image"
            }
        )

        if meta_image:

            imagem = (
                meta_image.get("content")
                or ""
            )

    # ========================================================
    # JSON-LD
    # ========================================================

    json_ld = extrair_json_ld(
        soup
    )

    for dados in json_ld:

        if not isinstance(
            dados,
            dict
        ):
            continue

        # Produto diretamente
        candidatos = [dados]

        # @graph
        if isinstance(
            dados.get("@graph"),
            list
        ):

            candidatos.extend(
                dados["@graph"]
            )

        for item in candidatos:

            if not isinstance(
                item,
                dict
            ):
                continue

            tipo = item.get(
                "@type",
                ""
            )

            if (
                str(tipo).lower()
                == "product"
            ):

                if not titulo:

                    titulo = (
                        item.get("name")
                        or ""
                    )

                if not imagem:

                    img = item.get(
                        "image"
                    )

                    if isinstance(
                        img,
                        list
                    ) and img:

                        imagem = img[0]

                    elif isinstance(
                        img,
                        str
                    ):

                        imagem = img

                offers = item.get(
                    "offers"
                )

                if isinstance(
                    offers,
                    dict
                ):

                    if not preco:

                        preco = (
                            offers.get(
                                "price"
                            )
                            or ""
                        )

                    if not preco:

                        preco = (
                            offers.get(
                                "lowPrice"
                            )
                            or ""
                        )

    # ========================================================
    # META PRICE
    # ========================================================

    if not preco:

        metas_preco = [

            {
                "property":
                    "product:price:amount"
            },

            {
                "property":
                    "og:price:amount"
            },

            {
                "name":
                    "price"
            },

            {
                "itemprop":
                    "price"
            }

        ]

        for attrs in metas_preco:

            tag = soup.find(
                "meta",
                attrs=attrs
            )

            if tag:

                preco = (
                    tag.get("content")
                    or ""
                )

                if preco:
                    break

    # ========================================================
    # LIMPEZA
    # ========================================================

    titulo = limpar_texto(
        titulo
    )

    preco = limpar_texto(
        preco
    )

    preco_antigo = limpar_texto(
        preco_antigo
    )

    imagem = limpar_texto(
        imagem
    )

    # ========================================================
    # DETECTAR PÁGINA GENÉRICA
    # ========================================================

    titulo_lower = titulo.lower()

    pagina_generica = (
        not titulo
        or "shopee brasil | ofertas incríveis" in titulo_lower
        or "ofertas incríveis. melhores preços do mercado" in titulo_lower
        or titulo_lower == "shopee"
    )

    if pagina_generica:

        print(
            "[HTML] A Shopee retornou uma página genérica."
        )

        titulo = ""

    print("=" * 40)
    print("[HTML] Título:", titulo)
    print("[HTML] Preço:", preco)
    print("[HTML] Imagem:", imagem)
    print("=" * 40)

    return {
        "title": titulo,
        "price": preco,
        "old_price": preco_antigo,
        "image": imagem,
        "product_link": url
    }


# ============================================================
# VALIDAR IMAGEM
# ============================================================

def imagem_valida(url):

    if not url:
        return False

    url_lower = url.lower()

    # Não aceitar imagem genérica da homepage
    if "homepagefe" in url_lower:
        return False

    if "logo" in url_lower:
        return False

    if not (
        url_lower.startswith("http://")
        or url_lower.startswith("https://")
    ):
        return False

    return True


# ============================================================
# FORMATAR PREÇO
# ============================================================

def formatar_preco(valor):

    if valor is None:
        return ""

    valor = str(valor).strip()

    if not valor:
        return ""

    # Já está em formato brasileiro
    if "R$" in valor:
        return valor

    # Decimal simples
    try:

        numero = float(
            valor.replace(",", ".")
        )

        return (
            "R$ "
            + f"{numero:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except Exception:

        return valor


# ============================================================
# MONTAR LEGENDA
# ============================================================

def montar_legenda(produto, link):

    titulo = (
        produto.get("title")
        or produto.get("productName")
        or "Oferta Shopee"
    )

    preco = (
        produto.get("price")
        or ""
    )

    preco_antigo = (
        produto.get("old_price")
        or ""
    )

    link_final = (
        produto.get("offerLink")
        or produto.get("product_link")
        or link
    )

    titulo = limpar_texto(
        titulo
    )

    preco = formatar_preco(
        preco
    )

    preco_antigo = formatar_preco(
        preco_antigo
    )

    linhas = []

    linhas.append(
        f"🦊 <b>{html.escape(titulo)}</b>"
    )

    if preco:

        if preco_antigo:

            linhas.append(
                f"🔥 <s>{html.escape(preco_antigo)}</s> "
                f"<b>{html.escape(preco)}</b>"
            )

        else:

            linhas.append(
                f"🔥 <b>{html.escape(preco)}</b>"
            )

    linhas.append("")

    linhas.append(
        "🛒 <b>Comprar na Shopee:</b>"
    )

    linhas.append(
        html.escape(link_final)
    )

    linhas.append("")

    linhas.append(
        "⚡ Oferta encontrada pela Raposa Caçadora"
    )

    return "\n".join(
        linhas
    )


# ============================================================
# PROCESSAR PRODUTO
# ============================================================

def processar_produto(link):

    print("=" * 40)
    print("[PRODUTO] Abrindo link:")
    print(link)
    print("=" * 40)

    if not link_shopee_valido(link):

        print(
            "[PRODUTO] Link inválido."
        )

        return None

    # ========================================================
    # 1. RESOLVER URL
    # ========================================================

    url_final, html_text = resolver_link_shopee(
        link
    )

    print(
        "[PRODUTO] URL final:",
        url_final
    )

    # ========================================================
    # 2. TENTAR IDS
    # ========================================================

    shop_id, item_id = extrair_ids_shopee(
        url_final,
        html_text
    )

    print(
        "[PRODUTO] shopId:",
        shop_id
    )

    print(
        "[PRODUTO] itemId:",
        item_id
    )

    # ========================================================
    # 3. PRODUCT OFFER
    # ========================================================

    produto_api = None

    if shop_id and item_id:

        produto_api = consultar_product_offer(
            shop_id,
            item_id
        )

    else:

        print(
            "[PRODUTO] Pulando ProductOfferV2 "
            "porque os IDs não foram encontrados."
        )

    # ========================================================
    # 4. FALLBACK HTML
    # ========================================================

    produto_html = {}

    if html_text:

        produto_html = extrair_produto_html(
            url_final,
            html_text
        )

    # ========================================================
    # 5. COMBINAR
    # ========================================================

    produto = {}

    if produto_api:

        produto.update(
            produto_api
        )

    if produto_html:

        if not produto.get("productName"):
            produto["productName"] = (
                produto_html.get("title")
                or ""
            )

        if not produto.get("price"):
            produto["price"] = (
                produto_html.get("price")
                or ""
            )

        if not produto.get("imageUrl"):
            produto["imageUrl"] = (
                produto_html.get("image")
                or ""
            )

        if not produto.get("productLink"):
            produto["productLink"] = (
                produto_html.get("product_link")
                or ""
            )

    # ========================================================
    # 6. NORMALIZAR
    # ========================================================

    titulo = limpar_texto(
        produto.get("productName")
        or produto.get("title")
        or ""
    )

    preco = (
        produto.get("price")
        or ""
    )

    imagem = limpar_texto(
        produto.get("imageUrl")
        or produto.get("image")
        or ""
    )

    product_link = (
        produto.get("offerLink")
        or produto.get("productLink")
        or url_final
    )

    # ========================================================
    # 7. NÃO ACEITAR PÁGINA GENÉRICA
    # ========================================================

    titulo_lower = titulo.lower()

    if (
        not titulo
        or titulo_lower.startswith(
            "shopee brasil |"
        )
        or titulo_lower == "shopee"
    ):

        print(
            "[PRODUTO] ❌ Nenhum título real encontrado."
        )

        titulo = ""

    # ========================================================
    # 8. LOG FINAL
    # ========================================================

    print("=" * 40)
    print("[PRODUTO] RESULTADO FINAL")
    print("[PRODUTO] Título:", titulo)
    print("[PRODUTO] Preço:", preco)
    print("[PRODUTO] Imagem:", imagem)
    print("[PRODUTO] Link:", product_link)
    print("=" * 40)

    # ========================================================
    # 9. SEM DADOS
    # ========================================================

    if not titulo:

        print(
            "[PRODUTO] ❌ Não foi possível obter "
            "dados reais do produto."
        )

        return {
            "success": False,
            "error": (
                "A Shopee não retornou os dados "
                "do produto."
            ),
            "link": url_final,
            "shortLink": None
        }

    # ========================================================
    # 10. SHORT LINK
    # ========================================================

    short_link = gerar_short_link(
        url_final
    )

    if short_link:

        product_link = short_link

    # ========================================================
    # 11. RESULTADO
    # ========================================================

    resultado = {

        "success": True,

        "title": titulo,

        "productName": titulo,

        "price": preco,

        "image": imagem,

        "imageUrl": imagem,

        "product_link": product_link,

        "productLink": product_link,

        "offerLink": short_link or product_link,

        "shortLink": short_link,

        "shopId": shop_id,

        "itemId": item_id
    }

    return resultado


# ============================================================
# PUBLICAR PRODUTO
# ============================================================

def publicar_produto(produto, link_original):

    if not produto:
        return False

    if not produto.get("success"):
        return False

    titulo = (
        produto.get("title")
        or "Oferta Shopee"
    )

    link = (
        produto.get("shortLink")
        or produto.get("offerLink")
        or produto.get("product_link")
        or link_original
    )

    imagem = (
        produto.get("imageUrl")
        or produto.get("image")
        or ""
    )

    legenda = montar_legenda(
        produto,
        link
    )

    print(
        "[TELEGRAM] Publicando:",
        titulo
    )

    print(
        "[TELEGRAM] Link:",
        link
    )

    # ========================================================
    # COM IMAGEM
    # ========================================================

    if imagem_valida(imagem):

        sucesso = telegram_publicar_foto(
            imagem,
            legenda
        )

        if sucesso:

            print(
                "[TELEGRAM] Produto publicado com imagem."
            )

            return True

        print(
            "[TELEGRAM] Falha ao publicar imagem."
        )

    else:

        print(
            "[TELEGRAM] Imagem não disponível."
        )

    # ========================================================
    # FALLBACK TEXTO
    # ========================================================

    sucesso = telegram_publicar_texto(
        legenda
    )

    if sucesso:

        print(
            "[TELEGRAM] Produto publicado como texto."
        )

        return True

    print(
        "[TELEGRAM] ❌ Falha ao publicar produto."
    )

    return False


# ============================================================
# PROCESSAMENTO DA TAREFA
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
                "status": "processando",
                "total": len(links),
                "processados": 0,
                "publicados": 0,
                "erros": 0,
                "mensagem": "Processando produtos..."
            }

        for indice, link in enumerate(
            links[:quantidade],
            start=1
        ):

            print("=" * 40)
            print(
                f"[TASK] Produto {indice}/{quantidade}"
            )

            print(
                "[TELEGRAM] Link:",
                link
            )

            try:

                produto = processar_produto(
                    link
                )

                if produto and produto.get("success"):

                    publicado = publicar_produto(
                        produto,
                        link
                    )

                    if publicado:

                        with tarefas_lock:

                            tarefas[task_id][
                                "publicados"
                            ] += 1

                    else:

                        with tarefas_lock:

                            tarefas[task_id][
                                "erros"
                            ] += 1

                else:

                    with tarefas_lock:

                        tarefas[task_id][
                            "erros"
                        ] += 1

                    print(
                        "[TASK] Produto não possui "
                        "dados suficientes."
                    )

            except Exception as erro:

                print(
                    "[TASK] Erro no produto:",
                    repr(erro)
                )

                with tarefas_lock:

                    tarefas[task_id][
                        "erros"
                    ] += 1

            finally:

                with tarefas_lock:

                    tarefas[task_id][
                        "processados"
                    ] = indice

            # =================================================
            # INTERVALO
            # =================================================

            if indice < quantidade:

                print(
                    f"[TASK] Aguardando {intervalo}s..."
                )

                time.sleep(
                    intervalo
                )

        # =====================================================
        # FINAL
        # =====================================================

        with tarefas_lock:

            tarefas[task_id][
                "status"
            ] = "concluida"

            tarefas[task_id][
                "mensagem"
            ] = "Automação concluída."

        print(
            "[TASK] Finalizada",
            task_id
        )

    except Exception as erro:

        print(
            "[TASK] ERRO FATAL:",
            repr(erro)
        )

        with tarefas_lock:

            tarefas[task_id][
                "status"
            ] = "erro"

            tarefas[task_id][
                "mensagem"
            ] = str(erro)


# ============================================================
# DEBUG ENV
# ============================================================

@app.route(
    "/debug-env",
    methods=["GET"]
)
def debug_env():

    return jsonify({

        "status": "ok",

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

    resultado = telegram_get_me()

    bot = None

    if resultado.get("ok"):

        bot = resultado.get(
            "result"
        )

    return jsonify({

        "BOT_TOKEN": {

            "existe":
                bool(BOT_TOKEN),

            "tamanho":
                len(BOT_TOKEN)
        },

        "CHANNEL_USERNAME": {

            "existe":
                bool(CHANNEL_USERNAME),

            "valor":
                CHANNEL_USERNAME
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

            "SHOPEE_API_URL": {

                "existe":
                    bool(SHOPEE_API_URL),

                "tamanho":
                    len(SHOPEE_API_URL),

                "valor":
                    SHOPEE_API_URL
            },

            "SHOPEE_APP_ID": {

                "existe":
                    bool(SHOPEE_APP_ID),

                "tamanho":
                    len(SHOPEE_APP_ID),

                "mascara":
                    mascara_valor(
                        SHOPEE_APP_ID
                    )
            },

            "SHOPEE_SECRET": {

                "existe":
                    bool(SHOPEE_SECRET),

                "tamanho":
                    len(SHOPEE_SECRET),

                "mascara":
                    mascara_valor(
                        SHOPEE_SECRET
                    )
            }
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
            int(time.time())
    })


# ============================================================
# DEBUG CONEXÃO SHOPEE
# ============================================================

@app.route(
    "/debug-shopee-conexao",
    methods=["GET"]
)
def debug_shopee_conexao():

    if not SHOPEE_API_URL:

        return jsonify({

            "sucesso": False,

            "erro":
                "SHOPEE_API_URL não configurada."

        }), 500

    try:

        resposta = requests.get(
            SHOPEE_API_URL,
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
# TESTE DIRETO DE LINK
# ============================================================

@app.route(
    "/debug-produto",
    methods=["GET"]
)
def debug_produto():

    link = (
        request.args.get(
            "url",
            ""
        )
        .strip()
    )

    if not link:

        return jsonify({

            "sucesso": False,

            "erro":
                "Informe ?url=LINK_DA_SHOPEE"

        }), 400

    if not link_shopee_valido(link):

        return jsonify({

            "sucesso": False,

            "erro":
                "O link informado não parece ser da Shopee."

        }), 400

    try:

        produto = processar_produto(
            link
        )

        return jsonify(
            produto or {
                "success": False,
                "error": "Nenhum resultado."
            }
        )

    except Exception as erro:

        return jsonify({

            "success": False,

            "error": str(erro)

        }), 500


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
                bool(BOT_TOKEN),

            "canal_configurado":
                bool(CHANNEL_USERNAME)
        },

        "shopee": {

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
# TESTE API
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
    print("[API] POST /api/configurar")

    try:

        dados = request.get_json(
            silent=True
        )

        if not isinstance(
            dados,
            dict
        ):

            print(
                "[API] JSON inválido."
            )

            return jsonify({

                "erro":
                    "Dados JSON inválidos."

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

                "erro":
                    "O campo links deve ser uma lista."

            }), 400

        # ====================================================
        # LIMPAR LINKS
        # ====================================================

        links_limpos = []

        for link in links:

            if not isinstance(
                link,
                str
            ):
                continue

            link = link.strip()

            if not link:
                continue

            if not link_shopee_valido(
                link
            ):

                return jsonify({

                    "erro":
                        f"Link inválido: {link}"

                }), 400

            links_limpos.append(
                link
            )

        links = links_limpos

        print(
            "[API] Links recebidos:",
            len(links)
        )

        if not links:

            return jsonify({

                "erro":
                    "Informe pelo menos um link da Shopee."

            }), 400

        if len(links) > MAX_LINKS:

            return jsonify({

                "erro":
                    "Máximo de 20 links."

            }), 400

        # ====================================================
        # INTERVALO
        # ====================================================

        try:

            intervalo = int(
                intervalo
            )

        except Exception:

            return jsonify({

                "erro":
                    "Intervalo inválido."

            }), 400

        if intervalo not in INTERVALOS_PERMITIDOS:

            return jsonify({

                "erro":
                    "Intervalo inválido. "
                    "Use 10, 60, 300 ou 600 segundos."

            }), 400

        # ====================================================
        # QUANTIDADE
        # ====================================================

        try:

            quantidade = int(
                quantidade
            )

        except Exception:

            return jsonify({

                "erro":
                    "Quantidade inválida."

            }), 400

        if quantidade < 1:

            return jsonify({

                "erro":
                    "Quantidade mínima é 1."

            }), 400

        if quantidade > len(links):

            quantidade = len(links)

        # ====================================================
        # LOG
        # ====================================================

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
            bool(SHOPEE_SECRET)
        )

        # ====================================================
        # VERIFICAR CONFIGURAÇÃO
        # ====================================================

        if not BOT_TOKEN:

            return jsonify({

                "erro":
                    "BOT_TOKEN não configurado no servidor."

            }), 500

        if not CHANNEL_USERNAME:

            return jsonify({

                "erro":
                    "CHANNEL_USERNAME não configurado."

            }), 500

        if not SHOPEE_APP_ID:

            return jsonify({

                "erro":
                    "SHOPEE_APP_ID não configurado."

            }), 500

        if not SHOPEE_SECRET:

            return jsonify({

                "erro":
                    "SHOPEE_SECRET não configurado."

            }), 500

        # ====================================================
        # CRIAR TAREFA
        # ====================================================

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
                    0,

                "mensagem":
                    "Tarefa criada."

            }

        print(
            "[TASK] Iniciando",
            task_id
        )

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
            "[API] Task criada:",
            task_id
        )

        return jsonify({

            "sucesso":
                True,

            "mensagem":
                "Automação iniciada com sucesso!",

            "task_id":
                task_id

        }), 200

    except Exception as erro:

        print(
            "[API] ERRO:",
            repr(erro)
        )

        return jsonify({

            "erro":
                str(erro)

        }), 500


# ============================================================
# STATUS DA TAREFA
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
                    "nao_encontrada",

                "mensagem":
                    "Tarefa não encontrada."

            }), 404

        return jsonify(
            tarefa
        )


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
