import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re
from urllib.parse import parse_qsl, urlparse, unquote

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

SHOPEE_APP_ID = os.environ.get(
    "SHOPEE_APP_ID",
    ""
).strip()

SHOPEE_APP_SECRET = os.environ.get(
    "SHOPEE_APP_SECRET",
    ""
).strip()

SHOPEE_API_URL = (
    "https://open-api.affiliate.shopee.com.br/graphql"
)

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
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": (
        "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    )
})


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

        resposta = session.get(
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
# UTILITÁRIOS
# ============================================================

def limpar_texto(texto):

    if not texto:
        return ""

    texto = str(texto)

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def escapar_html(texto):

    if texto is None:
        return ""

    texto = str(texto)

    return (
        texto
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


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

    try:

        # API pode retornar decimal:
        # 129.90
        if "," not in valor:

            numero = float(
                valor.replace(",", ".")
            )

        else:

            numero = float(
                valor
                .replace(".", "")
                .replace(",", ".")
            )

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

    if preco_str is None:
        return 0.0

    if isinstance(preco_str, (int, float)):

        return float(preco_str)

    preco_str = str(
        preco_str
    ).strip()

    if not preco_str:
        return 0.0

    try:

        limpo = (
            preco_str
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
# SHOPEE - EXTRAÇÃO DE SHOP ID / ITEM ID
# ============================================================

def extrair_ids_shopee(url):

    """
    Tenta descobrir shopId e itemId de vários formatos
    comuns de URL da Shopee.

    Exemplos:

    https://shopee.com.br/product/123/456

    https://shopee.com.br/produto-i.123.456

    https://shopee.com.br/opaanlp/123/456

    https://shopee.com.br/...?...shopid=123&itemid=456
    """

    if not url:
        return None, None

    try:

        url = unquote(
            url.strip()
        )

        parsed = urlparse(
            url
        )

        # ====================================================
        # QUERY STRING
        # ====================================================

        params = dict(
            parse_qsl(
                parsed.query,
                keep_blank_values=True
            )
        )

        shop_id = (
            params.get("shopid")
            or
            params.get("shop_id")
        )

        item_id = (
            params.get("itemid")
            or
            params.get("item_id")
        )

        if shop_id and item_id:

            if (
                str(shop_id).isdigit()
                and
                str(item_id).isdigit()
            ):

                return (
                    int(shop_id),
                    int(item_id)
                )

        caminho = (
            parsed.path
            or ""
        )

        caminho = unquote(
            caminho
        )

        # ====================================================
        # /product/SHOP/ITEM
        # ====================================================

        match = re.search(
            r"/product/(\d+)/(\d+)",
            caminho
        )

        if match:

            return (
                int(match.group(1)),
                int(match.group(2))
            )

        # ====================================================
        # /opaanlp/SHOP/ITEM
        # ====================================================

        match = re.search(
            r"/opaanlp/(\d+)/(\d+)",
            caminho
        )

        if match:

            return (
                int(match.group(1)),
                int(match.group(2))
            )

        # ====================================================
        # produto-i.SHOP.ITEM
        # ====================================================

        match = re.search(
            r"-i\.(\d+)\.(\d+)",
            caminho
        )

        if match:

            return (
                int(match.group(1)),
                int(match.group(2))
            )

        # ====================================================
        # Qualquer .SHOP.ITEM
        # ====================================================

        match = re.search(
            r"\.(\d{5,})\.(\d{5,})(?:[/?]|$)",
            caminho
        )

        if match:

            return (
                int(match.group(1)),
                int(match.group(2))
            )

    except Exception as erro:

        print(
            "[SHOPEE] Erro extraindo IDs:",
            erro
        )

    return None, None


# ============================================================
# SHOPEE - RESOLVER URL
# ============================================================

def resolver_url_http(link):

    """
    Tenta resolver o link curto usando HTTP.

    Retorna a URL final.
    """

    print(
        "[SHOPEE] Tentando resolver URL:"
    )

    print(
        link
    )

    try:

        resposta = session.get(
            link,
            timeout=20,
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

        if resposta.url:

            return resposta.url

    except Exception as erro:

        print(
            "[SHOPEE] Falha ao resolver HTTP:",
            erro
        )

    return link


# ============================================================
# SHOPEE - PLAYWRIGHT
# ============================================================

def resolver_url_playwright(link):

    """
    Fallback para links curtos que não redirecionam
    corretamente através de requests.

    Playwright é opcional.

    Se não estiver instalado, simplesmente retorna None.
    """

    try:

        from playwright.sync_api import (
            sync_playwright
        )

    except ImportError:

        print(
            "[SHOPEE] Playwright não instalado."
        )

        return None

    browser = None

    try:

        print(
            "[SHOPEE] Tentando resolver com Playwright..."
        )

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True
            )

            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="pt-BR"
            )

            page.goto(
                link,
                wait_until="domcontentloaded",
                timeout=45000
            )

            # Aguarda possíveis redirecionamentos JS.
            try:

                page.wait_for_timeout(
                    5000
                )

            except Exception:

                pass

            url_final = (
                page.url
            )

            print(
                "[SHOPEE] URL Playwright:",
                url_final
            )

            return url_final

    except Exception as erro:

        print(
            "[SHOPEE] Erro Playwright:",
            erro
        )

        return None

    finally:

        try:

            if browser:
                browser.close()

        except Exception:

            pass


def resolver_url_shopee(link):

    """
    Resolve URL usando HTTP e depois Playwright.
    """

    url_http = resolver_url_http(
        link
    )

    shop_id, item_id = (
        extrair_ids_shopee(
            url_http
        )
    )

    if shop_id and item_id:

        print(
            "[SHOPEE] IDs encontrados via HTTP:",
            shop_id,
            item_id
        )

        return (
            url_http,
            shop_id,
            item_id
        )

    # Se HTTP não resolveu o link curto,
    # tenta navegador real.

    if (
        "s.shopee." in
        link.lower()
    ):

        url_browser = (
            resolver_url_playwright(
                link
            )
        )

        if url_browser:

            shop_id, item_id = (
                extrair_ids_shopee(
                    url_browser
                )
            )

            if shop_id and item_id:

                print(
                    "[SHOPEE] IDs encontrados via Playwright:",
                    shop_id,
                    item_id
                )

                return (
                    url_browser,
                    shop_id,
                    item_id
                )

    # Tenta a própria URL original.
    shop_id, item_id = (
        extrair_ids_shopee(
            link
        )
    )

    if shop_id and item_id:

        return (
            link,
            shop_id,
            item_id
        )

    return (
        url_http or link,
        None,
        None
    )


# ============================================================
# SHOPEE API - ASSINATURA
# ============================================================

def shopee_assinatura(
    timestamp,
    payload
):

    texto = (
        f"{SHOPEE_APP_ID}"
        f"{timestamp}"
        f"{payload}"
        f"{SHOPEE_APP_SECRET}"
    )

    return hashlib.sha256(
        texto.encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================
# SHOPEE API - GRAPHQL
# ============================================================

def shopee_graphql(
    query,
    variables=None
):

    if not SHOPEE_APP_ID:

        return {
            "sucesso": False,
            "erro":
                "SHOPEE_APP_ID não configurado."
        }

    if not SHOPEE_APP_SECRET:

        return {
            "sucesso": False,
            "erro":
                "SHOPEE_APP_SECRET não configurado."
        }

    if variables is None:

        variables = {}

    # ========================================================
    # IMPORTANTE
    # O payload usado na assinatura é exatamente
    # o mesmo JSON enviado para a Shopee.
    # ========================================================

    payload_obj = {
        "query": query,
        "variables": variables
    }

    payload = json.dumps(
        payload_obj,
        separators=(",", ":"),
        ensure_ascii=False
    )

    timestamp = int(
        time.time()
    )

    assinatura = shopee_assinatura(
        timestamp,
        payload
    )

    authorization = (
        "SHA256 "
        f"Credential={SHOPEE_APP_ID}, "
        f"Timestamp={timestamp}, "
        f"Signature={assinatura}"
    )

    headers = {

        "Authorization":
            authorization,

        "Content-Type":
            "application/json",

        "Accept":
            "application/json",

        "User-Agent":
            "Raposa-Cacadora/1.0"
    }

    print(
        "[SHOPEE API] Enviando GraphQL..."
    )

    try:

        resposta = session.post(

            SHOPEE_API_URL,

            data=payload.encode(
                "utf-8"
            ),

            headers=headers,

            timeout=30
        )

        print(
            "[SHOPEE API] HTTP:",
            resposta.status_code
        )

        try:

            resultado = (
                resposta.json()
            )

        except Exception:

            return {

                "sucesso":
                    False,

                "erro":
                    "Shopee retornou uma resposta que não é JSON.",

                "http":
                    resposta.status_code,

                "resposta":
                    resposta.text[:1000]
            }

        if resultado.get(
            "errors"
        ):

            erros = (
                resultado.get(
                    "errors"
                )
            )

            mensagens = []

            for erro in erros:

                if isinstance(
                    erro,
                    dict
                ):

                    mensagem = (
                        erro.get(
                            "message"
                        )
                        or
                        erro.get(
                            "extensions",
                            {}
                        ).get(
                            "message"
                        )
                        or
                        "Erro GraphQL"
                    )

                    codigo = (
                        erro.get(
                            "extensions",
                            {}
                        ).get(
                            "code"
                        )
                    )

                    if codigo:

                        mensagem = (
                            f"{mensagem} "
                            f"(código {codigo})"
                        )

                    mensagens.append(
                        mensagem
                    )

                else:

                    mensagens.append(
                        str(erro)
                    )

            return {

                "sucesso":
                    False,

                "erro":
                    " | ".join(
                        mensagens
                    ),

                "http":
                    resposta.status_code,

                "resposta":
                    resultado
            }

        return {

            "sucesso":
                True,

            "dados":
                resultado,

            "http":
                resposta.status_code
        }

    except requests.RequestException as erro:

        print(
            "[SHOPEE API] Erro conexão:",
            erro
        )

        return {

            "sucesso":
                False,

            "erro":
                f"Erro de conexão com a API Shopee: {erro}"
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
# SHOPEE API - PRODUTO
# ============================================================

def consultar_produto_shopee(
    shop_id,
    item_id
):

    """
    Consulta um produto específico pela API oficial
    de Afiliados da Shopee.
    """

    query = """
query ProductOfferV2($itemId: Int, $shopId: Int, $page: Int, $limit: Int) {
  productOfferV2(
    itemId: $itemId,
    shopId: $shopId,
    page: $page,
    limit: $limit
  ) {
    nodes {
      itemId
      productName
      productLink
      offerLink
      imageUrl
      priceMin
      priceMax
      priceDiscountRate
      sales
      ratingStar
      commissionRate
      sellerCommissionRate
      shopeeCommissionRate
      commission
      shopId
      shopName
      shopType
      productCatIds
      periodStartTime
      periodEndTime
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

        "itemId":
            int(item_id),

        "shopId":
            int(shop_id),

        "page":
            1,

        "limit":
            20
    }

    resultado = shopee_graphql(
        query,
        variables
    )

    if not resultado.get(
        "sucesso"
    ):

        return resultado

    dados = (
        resultado
        .get("dados", {})
        .get("data", {})
        .get("productOfferV2", {})
    )

    nodes = (
        dados.get(
            "nodes",
            []
        )
    )

    if not nodes:

        return {

            "sucesso":
                False,

            "erro":
                "A API da Shopee não encontrou esse produto.",

            "resposta":
                resultado.get(
                    "dados"
                )
        }

    # Em princípio haverá um único item quando
    # itemId + shopId forem usados.

    produto = None

    for node in nodes:

        try:

            node_item = int(
                node.get(
                    "itemId",
                    0
                )
            )

        except Exception:

            node_item = 0

        try:

            node_shop = int(
                node.get(
                    "shopId",
                    0
                )
            )

        except Exception:

            node_shop = 0

        if (
            node_item == int(item_id)
            and
            node_shop == int(shop_id)
        ):

            produto = node
            break

    if not produto:

        produto = nodes[0]

    return {

        "sucesso":
            True,

        "produto":
            produto
    }


# ============================================================
# SHOPEE - DADOS DO PRODUTO
# ============================================================

def extrair_dados_produto(link):

    print(
        "========================================"
    )

    print(
        "[PRODUTO] Abrindo link:"
    )

    print(
        link
    )

    # ========================================================
    # RESOLVE LINK
    # ========================================================

    (
        url_final,
        shop_id,
        item_id
    ) = resolver_url_shopee(
        link
    )

    print(
        "[PRODUTO] URL final:"
    )

    print(
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

    # ========================================================
    # SEM IDs
    # ========================================================

    if not shop_id or not item_id:

        return {

            "sucesso":
                False,

            "erro":
                (
                    "Não foi possível identificar o produto "
                    "nesse link da Shopee. "
                    "O link curto não foi redirecionado para "
                    "uma URL contendo shopId/itemId."
                ),

            "link":
                link
        }

    # ========================================================
    # CONSULTA API
    # ========================================================

    resultado = consultar_produto_shopee(

        shop_id,

        item_id
    )

    if not resultado.get(
        "sucesso"
    ):

        return {

            "sucesso":
                False,

            "erro":
                resultado.get(
                    "erro",
                    "Erro ao consultar produto na Shopee."
                ),

            "link":
                link,

            "shop_id":
                shop_id,

            "item_id":
                item_id
        }

    produto = resultado.get(
        "produto",
        {}
    )

    # ========================================================
    # CAMPOS
    # ========================================================

    titulo = limpar_texto(
        produto.get(
            "productName"
        )
    )

    imagem = (
        produto.get(
            "imageUrl"
        )
        or
        ""
    ).strip()

    product_link = (
        produto.get(
            "productLink"
        )
        or
        ""
    ).strip()

    offer_link = (
        produto.get(
            "offerLink"
        )
        or
        ""
    ).strip()

    preco_min = (
        produto.get(
            "priceMin"
        )
    )

    preco_max = (
        produto.get(
            "priceMax"
        )
    )

    desconto = (
        produto.get(
            "priceDiscountRate"
        )
    )

    # ========================================================
    # VALIDAÇÃO
    # ========================================================

    if not titulo:

        return {

            "sucesso":
                False,

            "erro":
                (
                    "A API da Shopee encontrou o item, "
                    "mas não retornou o nome do produto."
                )
        }

    if not imagem:

        print(
            "[PRODUTO] API não retornou imagem."
        )

    # ========================================================
    # PREÇO
    # ========================================================

    preco_atual = ""

    if preco_min is not None:

        preco_atual = (
            formatar_preco(
                preco_min
            )
        )

    # Se priceMin não existir, tenta priceMax.
    if not preco_atual and preco_max is not None:

        preco_atual = (
            formatar_preco(
                preco_max
            )
        )

    valor_atual = converter_preco_float(
        preco_atual
    )

    # ========================================================
    # PREÇO ANTIGO
    # ========================================================

    preco_antigo = ""

    try:

        desconto_num = float(
            desconto or 0
        )

    except Exception:

        desconto_num = 0

    if (
        desconto_num > 0
        and
        valor_atual > 0
        and
        desconto_num < 100
    ):

        valor_original = (
            valor_atual
            /
            (
                1
                -
                (
                    desconto_num
                    /
                    100
                )
            )
        )

        preco_antigo = formatar_preco(
            valor_original
        )

    # ========================================================
    # LINK DE COMPRA
    # ========================================================

    link_compra = (
        offer_link
        or
        product_link
        or
        link
    )

    # ========================================================
    # RESULTADO
    # ========================================================

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
        "[PRODUTO] Preço antigo:",
        preco_antigo
    )

    print(
        "[PRODUTO] Desconto:",
        desconto_num
    )

    print(
        "[PRODUTO] Imagem:",
        imagem
    )

    print(
        "[PRODUTO] Link compra:",
        link_compra
    )

    print(
        "[PRODUTO] ========================================"
    )

    return {

        "sucesso":
            True,

        "titulo":
            titulo,

        "preco_atual":
            preco_atual,

        "preco_antigo":
            preco_antigo,

        "desconto":
            desconto_num,

        "imagem":
            imagem,

        "link":
            link_compra,

        "link_original":
            link,

        "product_link":
            product_link,

        "offer_link":
            offer_link,

        "shop_id":
            shop_id,

        "item_id":
            item_id
    }


# ============================================================
# TELEGRAM - ENVIO DE TEXTO
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
                False
        }

        if reply_markup:

            payload[
                "reply_markup"
            ] = reply_markup

        resposta = session.post(

            telegram_api_url(
                "sendMessage"
            ),

            json=payload,

            timeout=30
        )

        try:

            resultado = resposta.json()

        except Exception:

            return {

                "ok":
                    False,

                "erro":
                    (
                        "Telegram retornou HTTP "
                        f"{resposta.status_code}"
                    )
            }

        return resultado

    except requests.RequestException as erro:

        return {

            "ok":
                False,

            "erro":
                f"Erro Telegram: {erro}"
        }


# ============================================================
# TELEGRAM - ENVIO DE FOTO
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
                "BOT_TOKEN não disponível."
        }

    if not canal:

        return {

            "ok":
                False,

            "erro":
                "CHANNEL_USERNAME não configurado."
        }

    resposta_imagem = None

    try:

        print(
            "[TELEGRAM] Baixando imagem:"
        )

        print(
            foto
        )

        resposta_imagem = session.get(

            foto,

            timeout=30,

            headers={
                "User-Agent":
                    (
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 "
                        "Chrome/131.0.0.0 Safari/537.36"
                    )
            }
        )

        print(
            "[TELEGRAM] HTTP imagem:",
            resposta_imagem.status_code
        )

        if resposta_imagem.status_code != 200:

            return {

                "ok":
                    False,

                "erro":
                    (
                        "Não foi possível baixar a imagem. "
                        f"HTTP {resposta_imagem.status_code}"
                    )
            }

        content_type = (
            resposta_imagem.headers.get(
                "Content-Type",
                ""
            ).lower()
        )

        if (
            not content_type.startswith(
                "image/"
            )
        ):

            print(
                "[TELEGRAM] Content-Type inesperado:",
                content_type
            )

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
                reply_markup,
                ensure_ascii=False
            )

        arquivos = {

            "photo":
                (
                    "produto.jpg",

                    resposta_imagem.content,

                    content_type
                    or
                    "image/jpeg"
                )
        }

        resposta = session.post(

            telegram_api_url(
                "sendPhoto"
            ),

            data=payload,

            files=arquivos,

            timeout=45
        )

        try:

            return resposta.json()

        except Exception:

            return {

                "ok":
                    False,

                "erro":
                    (
                        "Telegram retornou HTTP "
                        f"{resposta.status_code}"
                    )
            }

    except Exception as erro:

        print(
            "[TELEGRAM] Erro foto:",
            erro
        )

        return {

            "ok":
                False,

            "erro":
                str(erro)
        }

    finally:

        try:

            if resposta_imagem:
                resposta_imagem.close()

        except Exception:

            pass


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

    if not SHOPEE_APP_ID:

        return {

            "sucesso":
                False,

            "mensagem":
                "SHOPEE_APP_ID não configurado no Render."
        }

    if not SHOPEE_APP_SECRET:

        return {

            "sucesso":
                False,

            "mensagem":
                "SHOPEE_APP_SECRET não configurado no Render."
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

    # ========================================================
    # OBTÉM PRODUTO PELA API
    # ========================================================

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
                    "Não foi possível encontrar o produto."
                )
        }

    titulo = dados.get(
        "titulo",
        ""
    )

    preco_atual = dados.get(
        "preco_atual",
        ""
    )

    preco_antigo = dados.get(
        "preco_antigo",
        ""
    )

    desconto = dados.get(
        "desconto",
        0
    )

    foto_url = dados.get(
        "imagem",
        ""
    )

    link_compra = dados.get(
        "link",
        ""
    )

    # ========================================================
    # NÃO PUBLICA PRODUTO SEM TÍTULO
    # ========================================================

    if not titulo:

        return {

            "sucesso":
                False,

            "mensagem":
                "Produto sem título retornado pela Shopee."
        }

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

            f"💰 <s>De: {escapar_html(preco_antigo)}</s>\n"

            f"🔥 <b>POR APENAS: "
            f"{escapar_html(preco_atual)}</b>"
        )

        if desconto:

            bloco_preco += (
                f"  <b>({float(desconto):.0f}% OFF)</b>"
            )

    elif preco_atual:

        bloco_preco = (

            f"💰 <b>POR APENAS: "
            f"{escapar_html(preco_atual)}</b>"
        )

    else:

        bloco_preco = (

            "💰 <b>Confira o preço da oferta!</b>"
        )

    # ========================================================
    # LEGENDA
    # ========================================================

    legenda = (

        "🔥 <b>OFERTA IMPERDÍVEL!</b> 🔥\n\n"

        f"📦 <b>{escapar_html(titulo)}</b>\n\n"

        f"{bloco_preco}\n\n"

        "🚨 <b>Corre porque essa oferta pode "
        "acabar a qualquer momento!</b>\n\n"

        "🛒 <b>APROVEITE AGORA!</b>\n\n"

        "🦊 <b>Raposa Caçadora</b>\n"
        "📌 Ofertas selecionadas todos os dias"
    )

    # ========================================================
    # BOTÃO
    # ========================================================

    if not link_compra:

        link_compra = link

    reply_markup = {

        "inline_keyboard": [

            [

                {

                    "text":
                        "🛒 COMPRAR AGORA",

                    "url":
                        link_compra
                }

            ]

        ]

    }

    # ========================================================
    # ENVIA FOTO REAL
    # ========================================================

    if (
        foto_url
        and
        foto_url.lower().startswith(
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

        print(
            "[TELEGRAM] Produto sem imagem. "
            "Enviando mensagem."
        )

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

        "desconto":
            desconto,

        "imagem":
            foto_url,

        "link":
            link_compra,

        "shop_id":
            dados.get(
                "shop_id"
            ),

        "item_id":
            dados.get(
                "item_id"
            )
    }


# ============================================================
# WORKER
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

        # ====================================================
        # FINALIZA
        # ====================================================

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

        # ====================================================
        # LINK
        # ====================================================

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
                * 100
            )

        # ====================================================
        # PUBLICAÇÃO
        # ====================================================

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

        # ====================================================
        # SALVA
        # ====================================================

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
                        ),

                    "desconto":
                        resultado.get(
                            "desconto"
                        ),

                    "imagem":
                        resultado.get(
                            "imagem"
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
                    * 100
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
                    * 100
                )

                tarefa[
                    "status"
                ] = "erro"

        # ====================================================
        # NÃO PARA A TAREFA POR ERRO
        # ====================================================

        if not sucesso:

            time.sleep(
                1
            )

            continue

        # ====================================================
        # ÚLTIMO
        # ====================================================

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

        # ====================================================
        # INTERVALO
        # ====================================================

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

    return jsonify({

        "status":
            "ok",

        "service":
            "raposa-cacadora",

        "telegram_configurado":
            bool(
                os.environ.get(
                    "BOT_TOKEN",
                    ""
                ).strip()
            ),

        "canal_configurado":
            bool(
                os.environ.get(
                    "CHANNEL_USERNAME",
                    ""
                ).strip()
            ),

        "shopee_app_id_configurado":
            bool(
                SHOPEE_APP_ID
            ),

        "shopee_secret_configurado":
            bool(
                SHOPEE_APP_SECRET
            ),

        "timestamp":
            int(time.time())
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
            bool(
                SHOPEE_APP_ID
            ),

        "SHOPEE_APP_ID_tamanho":
            len(
                SHOPEE_APP_ID
            ),

        "SHOPEE_APP_SECRET_existe":
            bool(
                SHOPEE_APP_SECRET
            ),

        "SHOPEE_APP_SECRET_tamanho":
            len(
                SHOPEE_APP_SECRET
            ),

        "PORT":
            os.environ.get(
                "PORT",
                ""
            )
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

    if resultado.get(
        "ok"
    ):

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
# DEBUG SHOPEE
# ============================================================

@app.route(
    "/debug-shopee",
    methods=["GET"]
)
def debug_shopee():

    return jsonify({

        "api_url":
            SHOPEE_API_URL,

        "app_id_configurado":
            bool(
                SHOPEE_APP_ID
            ),

        "secret_configurado":
            bool(
                SHOPEE_APP_SECRET
            ),

        "app_id_tamanho":
            len(
                SHOPEE_APP_ID
            ),

        "secret_tamanho":
            len(
                SHOPEE_APP_SECRET
            ),

        "playwright_disponivel":
            _playwright_disponivel()
    })


def _playwright_disponivel():

    try:

        import playwright

        return True

    except ImportError:

        return False


# ============================================================
# TESTE SHOPEE
# ============================================================

@app.route(
    "/api/testar-produto",
    methods=["POST"]
)
def testar_produto():

    try:

        dados = request.get_json(
            silent=True
        )

        if not dados:

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "JSON inválido."
            }), 400

        link = str(
            dados.get(
                "link",
                ""
            )
        ).strip()

        if not link:

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "Informe o link da Shopee."
            }), 400

        resultado = extrair_dados_produto(
            link
        )

        if not resultado.get(
            "sucesso"
        ):

            return jsonify(
                resultado
            ), 400

        return jsonify(
            resultado
        )

    except Exception as erro:

        return jsonify({

            "sucesso":
                False,

            "erro":
                str(erro)
        }), 500


# ============================================================
# TELEGRAM INIT DATA
# ============================================================

def validar_init_data(init_data):

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


def obter_usuario(init_data):

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
# SHOPEE LINK
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
    )


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

        # ====================================================
        # TELEGRAM
        # ====================================================

        token = os.environ.get(
            "BOT_TOKEN",
            ""
        ).strip()

        if not token:

            return jsonify({

                "erro":
                    "BOT_TOKEN não está disponível no Render."
            }), 500

        canal = os.environ.get(
            "CHANNEL_USERNAME",
            ""
        ).strip()

        if not canal:

            return jsonify({

                "erro":
                    "CHANNEL_USERNAME não está disponível no Render."
            }), 500

        # ====================================================
        # SHOPEE API
        # ====================================================

        if not SHOPEE_APP_ID:

            return jsonify({

                "erro":
                    "SHOPEE_APP_ID não está configurado no Render."
            }), 500

        if not SHOPEE_APP_SECRET:

            return jsonify({

                "erro":
                    "SHOPEE_APP_SECRET não está configurado no Render."
            }), 500

        # ====================================================
        # INIT DATA
        # ====================================================

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

        # ====================================================
        # LINKS
        # ====================================================

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

        # ====================================================
        # VALIDA LINKS
        # ====================================================

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

        # ====================================================
        # QUANTIDADE
        # ====================================================

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
                    (
                        "A quantidade não pode ser "
                        "maior que os produtos."
                    )
            }), 400

        if quantidade > MAX_LINKS:

            return jsonify({

                "erro":
                    "Máximo de 20 postagens."
            }), 400

        # ====================================================
        # INTERVALO
        # ====================================================

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

        # ====================================================
        # LIMITA LINKS
        # ====================================================

        links = links[
            :quantidade
        ]

        # ====================================================
        # CRIA TAREFA
        # ====================================================

        task_id = criar_tarefa(

            links=links,

            intervalo=intervalo,

            quantidade=quantidade,

            usuario=usuario
        )

        # ====================================================
        # THREAD
        # ====================================================

        thread = threading.Thread(

            target=executar_tarefa,

            args=(task_id,),

            daemon=True
        )

        thread.start()

        # ====================================================
        # RESPOSTA
        # ====================================================

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
                canal,

            "shopee_api":
                True
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
def status(task_id):

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
def parar(task_id):

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
