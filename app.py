import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re
from urllib.parse import urlparse, parse_qs, quote

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
# ARMAZENAMENTO DAS TAREFAS
# ============================================================

tarefas = {}
tarefas_lock = threading.Lock()


# ============================================================
# LOG
# ============================================================

def log(*args):
    print(*args, flush=True)


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
        + ("*" * max(1, len(valor) - 4))
        + valor[-2:]
    )


# ============================================================
# DEBUG ENV
# ============================================================

def debug_variavel(nome):
    valor = os.environ.get(nome, "").strip()

    return {
        "existe": bool(valor),
        "tamanho": len(valor),
        "mascara": mascara_valor(valor)
    }


@app.route("/debug-env", methods=["GET"])
def debug_env():

    return jsonify({

        "status": "ok",

        "telegram": {
            "BOT_TOKEN": debug_variavel("BOT_TOKEN"),
            "CHANNEL_USERNAME": debug_variavel("CHANNEL_USERNAME")
        },

        "shopee": {
            "SHOPEE_API_URL": debug_variavel("SHOPEE_API_URL"),
            "SHOPEE_APP_ID": debug_variavel("SHOPEE_APP_ID"),
            "SHOPEE_SECRET": debug_variavel("SHOPEE_SECRET")
        },

        "ambiente": {
            "PORT": os.environ.get("PORT", ""),
            "PYTHON_VERSION": os.environ.get("PYTHON_VERSION", "")
        },

        "timestamp": int(time.time())
    })


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api_url(metodo):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    return f"https://api.telegram.org/bot{token}/{metodo}"


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
                "erro": resposta.text[:500]
            }

    except Exception as erro:

        return {
            "ok": False,
            "erro": str(erro)
        }


@app.route("/debug-telegram", methods=["GET"])
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

    bot = resultado.get("result") if resultado.get("ok") else None

    return jsonify({

        "BOT_TOKEN": {
            "existe": bool(token),
            "tamanho": len(token)
        },

        "CHANNEL_USERNAME": {
            "existe": bool(canal),
            "valor": canal
        },

        "telegram_api_ok": resultado.get(
            "ok",
            False
        ),

        "bot": {
            "id": bot.get("id") if bot else None,
            "is_bot": bot.get("is_bot") if bot else None,
            "first_name": bot.get("first_name") if bot else None,
            "username": bot.get("username") if bot else None
        },

        "erro":
            resultado.get("erro")
            or resultado.get("description")
    })


# ============================================================
# TELEGRAM - PUBLICAR FOTO
# ============================================================

def telegram_enviar_foto(
    imagem,
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

    if not imagem:
        return {
            "ok": False,
            "erro": "Imagem não informada."
        }

    try:

        resposta = requests.post(
            telegram_api_url("sendPhoto"),
            json={
                "chat_id": canal,
                "photo": imagem,
                "caption": legenda,
                "parse_mode": "HTML"
            },
            timeout=30
        )

        try:
            dados = resposta.json()
        except Exception:
            dados = {
                "ok": False,
                "erro": resposta.text[:500]
            }

        if not resposta.ok:
            return {
                "ok": False,
                "http_status": resposta.status_code,
                "erro": dados.get(
                    "description",
                    "Erro Telegram"
                )
            }

        return dados

    except Exception as erro:

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# SHOPEE - CONFIGURAÇÃO
# ============================================================

def shopee_config_ok():

    return bool(
        SHOPEE_API_URL
        and SHOPEE_APP_ID
        and SHOPEE_SECRET
    )


# ============================================================
# SHOPEE - ASSINATURA
# ============================================================

def shopee_assinar(payload_string):

    timestamp = str(
        int(time.time())
    )

    fator = (
        SHOPEE_APP_ID
        + timestamp
        + payload_string
        + SHOPEE_SECRET
    )

    assinatura = hashlib.sha256(
        fator.encode("utf-8")
    ).hexdigest()

    authorization = (
        "SHA256 "
        f"Credential={SHOPEE_APP_ID}, "
        f"Timestamp={timestamp}, "
        f"Signature={assinatura}"
    )

    return timestamp, authorization


# ============================================================
# SHOPEE - GRAPHQL
# ============================================================

def shopee_graphql(
    query,
    variables=None
):

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

    if not SHOPEE_API_URL:
        return {
            "ok": False,
            "erro": "SHOPEE_API_URL não configurada."
        }

    payload = {
        "query": query
    }

    if variables is not None:
        payload["variables"] = variables

    # IMPORTANTE:
    # Este MESMO JSON é usado para gerar a assinatura
    # e enviado no body.
    payload_string = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":")
    )

    timestamp, authorization = shopee_assinar(
        payload_string
    )

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": authorization,
        "User-Agent": "Raposa-Cacadora/1.0"
    }

    log("========================================")
    log("[SHOPEE API] GraphQL")
    log("[SHOPEE API] URL:", SHOPEE_API_URL)
    log("[SHOPEE API] AppID:", mascara_valor(SHOPEE_APP_ID))
    log("[SHOPEE API] Timestamp:", timestamp)
    log("[SHOPEE API] Payload:", payload_string)
    log("========================================")

    try:

        resposta = requests.post(
            SHOPEE_API_URL,
            data=payload_string.encode("utf-8"),
            headers=headers,
            timeout=30
        )

        log(
            "[SHOPEE API] HTTP:",
            resposta.status_code
        )

        texto = resposta.text

        log(
            "[SHOPEE API] Resposta:",
            texto[:3000]
        )

        try:

            dados = resposta.json()

        except Exception:

            return {
                "ok": False,
                "http_status": resposta.status_code,
                "erro": "Resposta não é JSON.",
                "resposta": texto[:2000]
            }

        if not resposta.ok:

            return {
                "ok": False,
                "http_status": resposta.status_code,
                "erro": "HTTP error",
                "resposta": dados
            }

        if dados.get("errors"):

            return {
                "ok": False,
                "http_status": resposta.status_code,
                "erro": "GraphQL errors",
                "resposta": dados
            }

        return {
            "ok": True,
            "http_status": resposta.status_code,
            "dados": dados
        }

    except Exception as erro:

        log(
            "[SHOPEE API] EXCEPTION:",
            erro
        )

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# SHOPEE - RESOLVER URL
# ============================================================

def eh_url_shopee(url):

    try:

        parsed = urlparse(url)

        host = parsed.netloc.lower()

        hosts_validos = (
            "shopee.com.br",
            "www.shopee.com.br",
            "s.shopee.com.br",
            "shp.ee",
            "br.shp.ee"
        )

        return any(
            host == h or host.endswith("." + h)
            for h in hosts_validos
        )

    except Exception:

        return False


def resolver_url_shopee(url):

    log("========================================")
    log("[SHOPEE] Tentando resolver URL:")
    log(url)

    headers_lista = [

        {
            "User-Agent":
                "Mozilla/5.0 (Linux; Android 15) "
                "AppleWebKit/537.36 "
                "Chrome/151.0.0.0 Mobile Safari/537.36",
            "Accept":
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/avif,"
                "image/webp,*/*;q=0.8",
            "Accept-Language":
                "pt-BR,pt;q=0.9,en;q=0.8"
        },

        {
            "User-Agent":
                "Mozilla/5.0",
            "Accept":
                "*/*"
        }
    ]

    for tentativa, headers in enumerate(
        headers_lista,
        start=1
    ):

        try:

            resposta = requests.get(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=30
            )

            log(
                f"[SHOPEE] Tentativa {tentativa}"
            )

            log(
                "[SHOPEE] HTTP:",
                resposta.status_code
            )

            log(
                "[SHOPEE] URL final:",
                resposta.url
            )

            # Verifica também Location
            location = resposta.headers.get(
                "Location"
            )

            if location:

                log(
                    "[SHOPEE] Location:",
                    location
                )

            final_url = (
                resposta.url
                or location
                or url
            )

            if (
                final_url
                and
                final_url != url
                and
                "shopee.com.br" in final_url.lower()
            ):

                return final_url

            # Algumas páginas podem colocar o link
            # canônico dentro do HTML.
            texto = resposta.text or ""

            padroes = [

                r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)',

                r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)',

                r'"canonicalUrl"\s*:\s*"([^"]+)',

                r'"url"\s*:\s*"https:\\?/\\?/shopee\.com\.br[^"]+'
            ]

            for padrao in padroes:

                encontrado = re.search(
                    padrao,
                    texto,
                    re.IGNORECASE
                )

                if encontrado:

                    candidato = encontrado.group(1)

                    candidato = (
                        candidato
                        .replace("\\/", "/")
                    )

                    if (
                        "shopee.com.br" in
                        candidato.lower()
                    ):

                        log(
                            "[SHOPEE] URL encontrada no HTML:",
                            candidato
                        )

                        return candidato

        except Exception as erro:

            log(
                "[SHOPEE] Erro na tentativa:",
                erro
            )

    log(
        "[SHOPEE] Não foi possível resolver o link curto."
    )

    return url


# ============================================================
# SHOPEE - EXTRAIR SHOP ID / ITEM ID
# ============================================================

def extrair_ids_shopee(url):

    if not url:
        return None, None

    log(
        "[SHOPEE] Extraindo IDs de:",
        url
    )

    # --------------------------------------------------------
    # FORMATO:
    # /opaanlp/217896078/58202483323
    # --------------------------------------------------------

    match = re.search(
        r"/opaanlp/(\d+)/(\d+)",
        url
    )

    if match:

        shop_id = match.group(1)
        item_id = match.group(2)

        log(
            "[SHOPEE] IDs opaanlp:",
            shop_id,
            item_id
        )

        return shop_id, item_id

    # --------------------------------------------------------
    # FORMATO:
    # /product/SHOP/ITEM
    # --------------------------------------------------------

    match = re.search(
        r"/product/(\d+)/(\d+)",
        url
    )

    if match:

        shop_id = match.group(1)
        item_id = match.group(2)

        log(
            "[SHOPEE] IDs product:",
            shop_id,
            item_id
        )

        return shop_id, item_id

    # --------------------------------------------------------
    # FORMATO:
    # produto-i.SHOP.ITEM
    # --------------------------------------------------------

    match = re.search(
        r"-i\.(\d+)\.(\d+)",
        url
    )

    if match:

        shop_id = match.group(1)
        item_id = match.group(2)

        log(
            "[SHOPEE] IDs slug:",
            shop_id,
            item_id
        )

        return shop_id, item_id

    # --------------------------------------------------------
    # QUERY STRING:
    # ?shopid=...&itemid=...
    # --------------------------------------------------------

    try:

        parsed = urlparse(url)

        query = parse_qs(
            parsed.query
        )

        shop_values = (
            query.get("shopid")
            or query.get("shopId")
            or query.get("shop_id")
        )

        item_values = (
            query.get("itemid")
            or query.get("itemId")
            or query.get("item_id")
        )

        if shop_values and item_values:

            shop_id = shop_values[0]
            item_id = item_values[0]

            if (
                str(shop_id).isdigit()
                and
                str(item_id).isdigit()
            ):

                log(
                    "[SHOPEE] IDs query:",
                    shop_id,
                    item_id
                )

                return (
                    str(shop_id),
                    str(item_id)
                )

    except Exception:
        pass

    log(
        "[SHOPEE] Nenhum shopId/itemId encontrado."
    )

    return None, None


# ============================================================
# SHOPEE - BUSCAR PRODUTO PELO SHOP + ITEM
# ============================================================

def shopee_produto_por_ids(
    shop_id,
    item_id
):

    if not shop_id or not item_id:

        return {
            "ok": False,
            "erro": "shopId/itemId não informados."
        }

    # Query compatível com productOfferV2.
    query = """
query ProductOfferById($shopId: Int64!, $itemId: Int64!) {
  productOfferV2(
    shopId: $shopId,
    itemId: $itemId,
    page: 1,
    limit: 1
  ) {
    nodes {
      itemId
      commissionRate
      sellerCommissionRate
      shopeeCommissionRate
      commission
      sales
      priceMax
      priceMin
      ratingStar
      priceDiscountRate
      imageUrl
      productName
      shopId
      shopName
      shopType
      productLink
      offerLink
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
        "shopId": int(shop_id),
        "itemId": int(item_id)
    }

    resultado = shopee_graphql(
        query,
        variables
    )

    if not resultado.get("ok"):

        return resultado

    dados = resultado.get(
        "dados",
        {}
    )

    try:

        nodes = (
            dados
            .get("data", {})
            .get("productOfferV2", {})
            .get("nodes", [])
        )

    except Exception:

        nodes = []

    if not nodes:

        log(
            "[SHOPEE API] Produto não encontrado no catálogo de ofertas."
        )

        return {
            "ok": False,
            "erro": "Produto não encontrado no ProductOfferV2.",
            "dados": dados
        }

    produto = nodes[0]

    log(
        "[SHOPEE API] Produto encontrado:"
    )

    log(
        "[SHOPEE API] Nome:",
        produto.get("productName")
    )

    log(
        "[SHOPEE API] Preço:",
        produto.get("priceMin")
    )

    log(
        "[SHOPEE API] Imagem:",
        produto.get("imageUrl")
    )

    log(
        "[SHOPEE API] OfferLink:",
        produto.get("offerLink")
    )

    return {
        "ok": True,
        "produto": produto
    }


# ============================================================
# SHOPEE - GERAR SHORT LINK
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
        query,
        variables
    )

    if not resultado.get("ok"):
        return resultado

    dados = resultado.get(
        "dados",
        {}
    )

    try:

        short_link = (
            dados
            .get("data", {})
            .get("generateShortLink", {})
            .get("shortLink")
        )

    except Exception:

        short_link = None

    if not short_link:

        return {
            "ok": False,
            "erro": "Shopee não retornou shortLink.",
            "dados": dados
        }

    log(
        "[SHOPEE API] ShortLink gerado:",
        short_link
    )

    return {
        "ok": True,
        "shortLink": short_link
    }


# ============================================================
# SHOPEE - PROCESSAR PRODUTO
# ============================================================

def processar_produto(
    link_original
):

    log("")
    log("========================================")
    log("[PRODUTO] Abrindo link:")
    log(link_original)
    log("========================================")

    if not eh_url_shopee(
        link_original
    ):

        return {
            "ok": False,
            "erro": "Link não pertence à Shopee."
        }

    # --------------------------------------------------------
    # 1. Resolver URL
    # --------------------------------------------------------

    url_final = resolver_url_shopee(
        link_original
    )

    log(
        "[PRODUTO] URL final:",
        url_final
    )

    # --------------------------------------------------------
    # 2. Extrair IDs
    # --------------------------------------------------------

    shop_id, item_id = extrair_ids_shopee(
        url_final
    )

    log(
        "[PRODUTO] shopId:",
        shop_id
    )

    log(
        "[PRODUTO] itemId:",
        item_id
    )

    # --------------------------------------------------------
    # 3. Tentar API ProductOffer
    # --------------------------------------------------------

    if shopee_config_ok():

        if shop_id and item_id:

            api_resultado = shopee_produto_por_ids(
                shop_id,
                item_id
            )

            if api_resultado.get("ok"):

                produto = api_resultado["produto"]

                # Link de afiliado retornado pela Shopee.
                affiliate_link = (
                    produto.get("offerLink")
                    or produto.get("productLink")
                    or url_final
                )

                return {
                    "ok": True,
                    "fonte": "shopee_api",
                    "url_original": link_original,
                    "url_final": url_final,
                    "shop_id": str(
                        produto.get("shopId")
                        or shop_id
                    ),
                    "item_id": str(
                        produto.get("itemId")
                        or item_id
                    ),
                    "titulo": (
                        produto.get("productName")
                        or "Produto Shopee"
                    ),
                    "preco": (
                        produto.get("priceMin")
                        or ""
                    ),
                    "preco_max": (
                        produto.get("priceMax")
                        or ""
                    ),
                    "desconto": (
                        produto.get("priceDiscountRate")
                        or 0
                    ),
                    "comissao": (
                        produto.get("commission")
                        or ""
                    ),
                    "comissao_rate": (
                        produto.get("commissionRate")
                        or ""
                    ),
                    "imagem": (
                        produto.get("imageUrl")
                        or ""
                    ),
                    "link": affiliate_link,
                    "produto_api": produto
                }

        else:

            log(
                "[PRODUTO] Não há IDs para consultar ProductOfferV2."
            )

    else:

        log(
            "[PRODUTO] API Shopee não configurada completamente."
        )

    # --------------------------------------------------------
    # 4. Fallback: generateShortLink
    # --------------------------------------------------------

    if shopee_config_ok():

        log(
            "[PRODUTO] Tentando generateShortLink..."
        )

        short_resultado = shopee_generate_short_link(
            url_final
        )

        if short_resultado.get("ok"):

            return {
                "ok": True,
                "fonte": "generateShortLink",
                "url_original": link_original,
                "url_final": url_final,
                "shop_id": shop_id or "",
                "item_id": item_id or "",
                "titulo": "Oferta Shopee",
                "preco": "",
                "preco_max": "",
                "desconto": 0,
                "comissao": "",
                "comissao_rate": "",
                "imagem": "",
                "link": short_resultado.get(
                    "shortLink"
                )
            }

    # --------------------------------------------------------
    # 5. Fallback HTML
    # --------------------------------------------------------

    return processar_produto_html(
        link_original,
        url_final
    )


# ============================================================
# FALLBACK HTML
# ============================================================

def processar_produto_html(
    link_original,
    url_final
):

    log(
        "[PRODUTO] Tentando fallback HTML..."
    )

    headers = {
        "User-Agent":
            "Mozilla/5.0 (Linux; Android 15) "
            "AppleWebKit/537.36 "
            "Chrome/151.0.0.0 Mobile Safari/537.36",
        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8"
    }

    try:

        resposta = requests.get(
            url_final,
            headers=headers,
            timeout=30,
            allow_redirects=True
        )

        log(
            "[PRODUTO] HTTP fallback:",
            resposta.status_code
        )

        html = resposta.text or ""

        log(
            "[PRODUTO] HTML recebido:",
            len(html),
            "bytes"
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        titulo = ""
        imagem = ""
        preco = ""

        # ----------------------------------------------------
        # OG TITLE
        # ----------------------------------------------------

        og_title = soup.find(
            "meta",
            property="og:title"
        )

        if og_title:
            titulo = (
                og_title.get("content")
                or ""
            ).strip()

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        if not titulo:

            title_tag = soup.find(
                "title"
            )

            if title_tag:
                titulo = (
                    title_tag.get_text(
                        strip=True
                    )
                )

        # ----------------------------------------------------
        # OG IMAGE
        # ----------------------------------------------------

        og_image = soup.find(
            "meta",
            property="og:image"
        )

        if og_image:

            imagem = (
                og_image.get("content")
                or ""
            ).strip()

        # ----------------------------------------------------
        # META PRICE
        # ----------------------------------------------------

        price_candidates = [

            soup.find(
                "meta",
                property="product:price:amount"
            ),

            soup.find(
                "meta",
                attrs={
                    "name": "product:price:amount"
                }
            )
        ]

        for tag in price_candidates:

            if tag:

                preco = (
                    tag.get("content")
                    or ""
                ).strip()

                if preco:
                    break

        # ----------------------------------------------------
        # JSON-LD
        # ----------------------------------------------------

        for script in soup.find_all(
            "script",
            type="application/ld+json"
        ):

            try:

                conteudo = json.loads(
                    script.string or
                    script.get_text()
                )

                objetos = (
                    conteudo
                    if isinstance(
                        conteudo,
                        list
                    )
                    else [conteudo]
                )

                for obj in objetos:

                    if not isinstance(
                        obj,
                        dict
                    ):
                        continue

                    if not titulo:

                        titulo = (
                            obj.get(
                                "name"
                            )
                            or ""
                        )

                    if not imagem:

                        imagem_valor = (
                            obj.get(
                                "image"
                            )
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

                        imagem = (
                            imagem_valor
                            or ""
                        )

                    if not preco:

                        offers = obj.get(
                            "offers"
                        )

                        if isinstance(
                            offers,
                            dict
                        ):

                            preco = str(
                                offers.get(
                                    "price",
                                    ""
                                )
                            )

            except Exception:
                continue

        if not titulo:

            titulo = "Oferta Shopee"

        # Não usamos uma imagem genérica da Shopee
        # como se fosse imagem do produto.
        if not imagem:

            log(
                "[PRODUTO] Nenhuma imagem de produto encontrada."
            )

        log(
            "========================================"
        )

        log(
            "[PRODUTO] Título:",
            titulo
        )

        log(
            "[PRODUTO] Preço atual:",
            preco
        )

        log(
            "[PRODUTO] Imagem:",
            imagem
        )

        log(
            "========================================"
        )

        return {
            "ok": True,
            "fonte": "html",
            "url_original": link_original,
            "url_final": resposta.url or url_final,
            "shop_id": "",
            "item_id": "",
            "titulo": titulo,
            "preco": preco,
            "preco_max": "",
            "desconto": 0,
            "comissao": "",
            "comissao_rate": "",
            "imagem": imagem,
            "link": url_final
        }

    except Exception as erro:

        log(
            "[PRODUTO] Fallback HTML erro:",
            erro
        )

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# FORMATAÇÃO TELEGRAM
# ============================================================

def formatar_preco(preco):

    if preco is None:
        return ""

    texto = str(preco).strip()

    if not texto:
        return ""

    # Se a API já mandar algo como R$ 99,90,
    # não altera.
    if "R$" in texto:
        return texto

    try:

        numero = float(
            texto.replace(",", ".")
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


def montar_legenda(produto):

    titulo = (
        produto.get("titulo")
        or "Oferta Shopee"
    )

    preco = formatar_preco(
        produto.get("preco")
    )

    preco_max = formatar_preco(
        produto.get("preco_max")
    )

    desconto = produto.get(
        "desconto"
    )

    link = (
        produto.get("link")
        or produto.get("url_final")
        or ""
    )

    linhas = []

    linhas.append(
        f"<b>🦊 ACHADINHO SHOPEE</b>"
    )

    linhas.append("")

    linhas.append(
        f"<b>{titulo}</b>"
    )

    if preco:

        if (
            preco_max
            and
            preco_max != preco
        ):

            linhas.append(
                f"💰 <b>{preco}</b>"
            )

        else:

            linhas.append(
                f"💰 <b>{preco}</b>"
            )

    if desconto:

        try:

            desconto_int = int(
                desconto
            )

            if desconto_int > 0:

                linhas.append(
                    f"🔥 <b>{desconto_int}% OFF</b>"
                )

        except Exception:
            pass

    linhas.append("")

    if link:

        linhas.append(
            f'🛒 <a href="{link}">COMPRAR NA SHOPEE</a>'
        )

    return "\n".join(
        linhas
    )


# ============================================================
# PUBLICAR PRODUTO
# ============================================================

def publicar_produto(
    produto
):

    titulo = produto.get(
        "titulo",
        "Oferta Shopee"
    )

    imagem = produto.get(
        "imagem"
    )

    link = produto.get(
        "link"
    )

    log(
        "[TELEGRAM] Publicando:",
        titulo
    )

    log(
        "[TELEGRAM] Link:",
        link
    )

    legenda = montar_legenda(
        produto
    )

    # --------------------------------------------------------
    # Com imagem
    # --------------------------------------------------------

    if imagem:

        log(
            "[TELEGRAM] Baixando/verificando imagem:",
            imagem
        )

        try:

            img = requests.get(
                imagem,
                timeout=30
            )

            log(
                "[TELEGRAM] HTTP imagem:",
                img.status_code
            )

            if img.ok:

                resultado = telegram_enviar_foto(
                    imagem,
                    legenda
                )

                if resultado.get("ok"):

                    log(
                        "[TELEGRAM] Produto publicado com imagem."
                    )

                    return resultado

                log(
                    "[TELEGRAM] Falha sendPhoto:",
                    resultado
                )

        except Exception as erro:

            log(
                "[TELEGRAM] Erro imagem:",
                erro
            )

    # --------------------------------------------------------
    # Sem imagem: envia mensagem de texto
    # --------------------------------------------------------

    try:

        resposta = requests.post(
            telegram_api_url(
                "sendMessage"
            ),
            json={
                "chat_id": CHANNEL_USERNAME,
                "text": legenda,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            },
            timeout=30
        )

        try:
            dados = resposta.json()
        except Exception:
            dados = {
                "ok": False,
                "erro": resposta.text[:500]
            }

        if dados.get("ok"):

            log(
                "[TELEGRAM] Produto publicado como texto."
            )

        else:

            log(
                "[TELEGRAM] Erro sendMessage:",
                dados
            )

        return dados

    except Exception as erro:

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# PROCESSAMENTO DA TAREFA
# ============================================================

def executar_tarefa(
    task_id,
    links,
    intervalo,
    quantidade
):

    log("")
    log(
        "[TASK] Iniciando",
        task_id
    )

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

        log("")
        log(
            "========================================"
        )

        log(
            f"[TASK] Produto {indice}/{len(links[:quantidade])}"
        )

        log(
            "[TELEGRAM] Link:",
            link
        )

        try:

            produto = processar_produto(
                link
            )

            if not produto.get("ok"):

                log(
                    "[PRODUTO] ERRO:",
                    produto.get("erro")
                )

                with tarefas_lock:

                    tarefas[task_id][
                        "erros"
                    ] += 1

                    tarefas[task_id][
                        "processados"
                    ] += 1

                continue

            # Publica no Telegram
            telegram_resultado = publicar_produto(
                produto
            )

            with tarefas_lock:

                tarefas[task_id][
                    "processados"
                ] += 1

                if telegram_resultado.get("ok"):

                    tarefas[task_id][
                        "publicados"
                    ] += 1

                else:

                    tarefas[task_id][
                        "erros"
                    ] += 1

                    log(
                        "[TELEGRAM] ERRO:",
                        telegram_resultado
                    )

            # ------------------------------------------------
            # Intervalo
            # ------------------------------------------------

            if indice < quantidade:

                log(
                    f"[TASK] Aguardando {intervalo}s..."
                )

                # Espera em pequenos blocos para
                # permitir cancelamento futuramente.
                restante = intervalo

                while restante > 0:

                    with tarefas_lock:

                        if tarefas.get(
                            task_id,
                            {}
                        ).get(
                            "status"
                        ) == "cancelada":

                            log(
                                "[TASK] Cancelada."
                            )

                            return

                    espera = min(
                        restante,
                        1
                    )

                    time.sleep(
                        espera
                    )

                    restante -= espera

        except Exception as erro:

            log(
                "[TASK] ERRO:",
                erro
            )

            with tarefas_lock:

                tarefas[task_id][
                    "erros"
                ] += 1

                tarefas[task_id][
                    "processados"
                ] += 1

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    with tarefas_lock:

        tarefa = tarefas.get(
            task_id,
            {}
        )

        if tarefa.get(
            "status"
        ) != "cancelada":

            tarefa["status"] = "concluida"

            tarefa["mensagem"] = (
                "Automação concluída."
            )

    log("")
    log(
        "[TASK] Finalizada",
        task_id
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

        log("")
        log(
            "========================================"
        )

        log(
            "[API] POST /api/configurar"
        )

        # ----------------------------------------------------
        # JSON
        # ----------------------------------------------------

        if not isinstance(
            dados,
            dict
        ):

            log(
                "[API] JSON inválido."
            )

            return jsonify({
                "sucesso": False,
                "erro": "JSON inválido."
            }), 400

        # ----------------------------------------------------
        # Links
        # ----------------------------------------------------

        links = dados.get(
            "links"
        )

        if not isinstance(
            links,
            list
        ):

            # Aceita também um único link,
            # caso algum frontend antigo envie string.
            link_unico = dados.get(
                "link"
            )

            if isinstance(
                link_unico,
                str
            ):

                links = [
                    link_unico
                ]

            else:

                return jsonify({
                    "sucesso": False,
                    "erro":
                        "Informe pelo menos um link da Shopee."
                }), 400

        # Limpeza
        links = [
            str(link).strip()
            for link in links
            if str(link).strip()
        ]

        log(
            "[API] Links recebidos:",
            len(links)
        )

        if not links:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Informe um link da Shopee."
            }), 400

        if len(links) > MAX_LINKS:

            return jsonify({
                "sucesso": False,
                "erro":
                    f"Máximo de {MAX_LINKS} produtos."
            }), 400

        # ----------------------------------------------------
        # Validação dos domínios
        # ----------------------------------------------------

        invalidos = [
            link
            for link in links
            if not eh_url_shopee(link)
        ]

        if invalidos:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Um ou mais links não são da Shopee.",
                "links_invalidos": invalidos[:5]
            }), 400

        # ----------------------------------------------------
        # Intervalo
        # ----------------------------------------------------

        try:

            intervalo = int(
                dados.get(
                    "intervalo",
                    10
                )
            )

        except Exception:

            intervalo = 10

        if intervalo not in INTERVALOS_PERMITIDOS:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Intervalo inválido.",
                "permitidos":
                    sorted(
                        INTERVALOS_PERMITIDOS
                    )
            }), 400

        # ----------------------------------------------------
        # Quantidade
        # ----------------------------------------------------

        try:

            quantidade = int(
                dados.get(
                    "quantidade",
                    len(links)
                )
            )

        except Exception:

            quantidade = len(links)

        if quantidade < 1:

            quantidade = 1

        if quantidade > len(links):

            quantidade = len(links)

        if quantidade > MAX_LINKS:

            quantidade = MAX_LINKS

        # ----------------------------------------------------
        # Telegram
        # ----------------------------------------------------

        init_data = (
            dados.get(
                "initData"
            )
            or ""
        )

        usuario = (
            dados.get(
                "user"
            )
            or {}
        )

        log(
            "[TELEGRAM] Usuário:",
            usuario
        )

        log(
            "[TELEGRAM] Canal:",
            CHANNEL_USERNAME
        )

        # ----------------------------------------------------
        # Configuração Shopee
        # ----------------------------------------------------

        log(
            "[SHOPEE] API URL:",
            SHOPEE_API_URL
        )

        log(
            "[SHOPEE] AppID:",
            mascara_valor(
                SHOPEE_APP_ID
            )
        )

        log(
            "[SHOPEE] Secret configurado:",
            bool(
                SHOPEE_SECRET
            )
        )

        # ----------------------------------------------------
        # Criar task
        # ----------------------------------------------------

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
                    "Automação iniciando.",

                "criado_em":
                    int(time.time())
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

        log(
            "[API] Task criada:",
            task_id
        )

        log(
            "========================================"
        )

        return jsonify({

            "sucesso":
                True,

            "mensagem":
                "Automação iniciada com sucesso.",

            "task_id":
                task_id,

            "total":
                quantidade,

            "intervalo":
                intervalo
        })

    except Exception as erro:

        log(
            "[API] ERRO /api/configurar:",
            erro
        )

        return jsonify({

            "sucesso":
                False,

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
def status_tarefa(
    task_id
):

    with tarefas_lock:

        tarefa = tarefas.get(
            task_id
        )

        if not tarefa:

            return jsonify({

                "status":
                    "nao_encontrada",

                "erro":
                    "Tarefa não encontrada."
            }), 404

        return jsonify(
            dict(tarefa)
        )


# ============================================================
# CANCELAR TAREFA
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

        tarefa["mensagem"] = (
            "Automação cancelada."
        )

    return jsonify({

        "sucesso":
            True,

        "mensagem":
            "Tarefa cancelada."
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
                shopee_config_ok()
        },

        "timestamp":
            int(time.time())
    })


# ============================================================
# TESTAR CONEXÃO SHOPEE
# ============================================================

@app.route(
    "/debug-shopee-conexao",
    methods=["GET"]
)
def debug_shopee_conexao():

    resultado = {

        "api_url":
            SHOPEE_API_URL,

        "app_id_configurado":
            bool(
                SHOPEE_APP_ID
            ),

        "secret_configurado":
            bool(
                SHOPEE_SECRET
            ),

        "configuracao_completa":
            shopee_config_ok(),

        "timestamp":
            int(time.time())
    }

    if not shopee_config_ok():

        resultado["sucesso"] = False

        resultado["erro"] = (
            "Configure SHOPEE_API_URL, "
            "SHOPEE_APP_ID e SHOPEE_SECRET."
        )

        return jsonify(
            resultado
        ), 500

    # --------------------------------------------------------
    # Query simples para testar autenticação.
    # --------------------------------------------------------

    query = """
query TestShopee {
  shopeeOfferV2(
    page: 1,
    limit: 1
  ) {
    nodes {
      offerName
      offerLink
    }
    pageInfo {
      page
      limit
      hasNextPage
    }
  }
}
"""

    api_resultado = shopee_graphql(
        query
    )

    resultado["api"] = api_resultado

    if api_resultado.get("ok"):

        resultado["sucesso"] = True

        return jsonify(
            resultado
        )

    resultado["sucesso"] = False

    return jsonify(
        resultado
    ), 500


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
                shopee_config_ok()
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
            shopee_config_ok(),

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
