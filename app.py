import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re

from urllib.parse import urlparse, parse_qsl, unquote

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
                timeout=40
            )

        else:
            resposta = requests.post(
                telegram_api_url(metodo),
                json=payload or {},
                timeout=40
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


# ============================================================
# TELEGRAM - PUBLICAR TEXTO
# ============================================================

def telegram_publicar_texto(texto):

    canal = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()

    if not canal:
        log("[TELEGRAM] CHANNEL_USERNAME não configurado.")
        return False, "CHANNEL_USERNAME não configurado."

    resultado = telegram_request(
        "sendMessage",
        {
            "chat_id": canal,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
    )

    if resultado.get("ok"):

        log("[TELEGRAM] Mensagem publicada.")

        return True, resultado

    erro = (
        resultado.get("description")
        or
        "Erro desconhecido do Telegram."
    )

    log("[TELEGRAM] ERRO:", erro)

    return False, erro


# ============================================================
# TELEGRAM - PUBLICAR IMAGEM
# ============================================================

def telegram_publicar_foto(
    imagem_url,
    legenda
):

    canal = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()

    if not canal:
        return False, "CHANNEL_USERNAME não configurado."

    if not imagem_url:
        return telegram_publicar_texto(legenda)

    try:

        log("[TELEGRAM] Baixando imagem:")
        log(imagem_url)

        resposta_imagem = requests.get(
            imagem_url,
            timeout=30,
            headers={
                "User-Agent":
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
            }
        )

        log(
            "[TELEGRAM] HTTP imagem:",
            resposta_imagem.status_code
        )

        if resposta_imagem.status_code != 200:
            return telegram_publicar_texto(legenda)

        arquivo = resposta_imagem.content

        resultado = telegram_request(
            "sendPhoto",
            payload={
                "chat_id": canal,
                "caption": legenda,
                "parse_mode": "HTML"
            },
            files={
                "photo": (
                    "produto.jpg",
                    arquivo,
                    resposta_imagem.headers.get(
                        "Content-Type",
                        "image/jpeg"
                    )
                )
            }
        )

        if resultado.get("ok"):

            log("[TELEGRAM] Produto publicado com imagem.")

            return True, resultado

        erro = (
            resultado.get("description")
            or
            "Erro ao enviar foto."
        )

        log("[TELEGRAM] Erro ao enviar foto:", erro)

        return telegram_publicar_texto(legenda)

    except Exception as erro:

        log(
            "[TELEGRAM] Erro baixando/enviando imagem:",
            erro
        )

        return telegram_publicar_texto(legenda)


# ============================================================
# ASSINATURA SHOPEE
# ============================================================

def shopee_headers(payload):

    timestamp = int(time.time())

    payload_string = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":")
    )

    texto_assinatura = (
        SHOPEE_APP_ID
        +
        str(timestamp)
        +
        payload_string
        +
        SHOPEE_SECRET
    )

    signature = hashlib.sha256(
        texto_assinatura.encode("utf-8")
    ).hexdigest()

    authorization = (
        f"SHA256 "
        f"Credential={SHOPEE_APP_ID}, "
        f"Timestamp={timestamp}, "
        f"Signature={signature}"
    )

    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": authorization
    }


# ============================================================
# GRAPHQL SHOPEE
# ============================================================

def shopee_graphql(
    query,
    variables=None,
    operation_name=None
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

    if operation_name:
        payload["operationName"] = operation_name

    headers = shopee_headers(payload)

    try:

        log("========================================")
        log("[SHOPEE API] GraphQL")
        log("[SHOPEE API] URL:", SHOPEE_API_URL)
        log("[SHOPEE API] AppID:", mascara_valor(SHOPEE_APP_ID))
        log(
            "[SHOPEE API] Timestamp:",
            headers["Authorization"].split("Timestamp=")[1].split(",")[0]
        )

        log(
            "[SHOPEE API] Payload:",
            json.dumps(
                payload,
                ensure_ascii=False
            )
        )

        resposta = requests.post(
            SHOPEE_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )

        log(
            "[SHOPEE API] HTTP:",
            resposta.status_code
        )

        texto = resposta.text

        log(
            "[SHOPEE API] Resposta:",
            texto[:5000]
        )

        try:
            dados = resposta.json()
        except Exception:

            return {
                "ok": False,
                "http_status": resposta.status_code,
                "erro":
                    "Shopee retornou uma resposta que não é JSON."
            }

        if resposta.status_code != 200:

            return {
                "ok": False,
                "http_status": resposta.status_code,
                "erro":
                    dados.get("message")
                    or
                    dados.get("error")
                    or
                    "Erro HTTP na API Shopee.",
                "dados": dados
            }

        if dados.get("errors"):

            erros = []

            for erro in dados.get("errors", []):

                mensagem = (
                    erro.get("message")
                    or
                    "Erro GraphQL"
                )

                extensao = erro.get(
                    "extensions",
                    {}
                )

                codigo = extensao.get(
                    "code"
                )

                if codigo:
                    mensagem = (
                        f"{mensagem} "
                        f"(código {codigo})"
                    )

                erros.append(mensagem)

            return {
                "ok": False,
                "http_status": 200,
                "erro": " | ".join(erros),
                "dados": dados
            }

        return {
            "ok": True,
            "http_status": 200,
            "dados": dados
        }

    except requests.RequestException as erro:

        log(
            "[SHOPEE API] RequestException:",
            erro
        )

        return {
            "ok": False,
            "erro": str(erro)
        }

    except Exception as erro:

        log(
            "[SHOPEE API] Exception:",
            erro
        )

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# EXTRAIR SHOP ID / ITEM ID
# ============================================================

def extrair_ids_shopee(url):

    if not url:
        return None, None

    texto = unquote(url)

    log("[SHOPEE] Extraindo IDs de:", texto)

    shop_id = None
    item_id = None

    # --------------------------------------------------------
    # FORMATO:
    # shopee.com.br/product/123/456
    # --------------------------------------------------------

    padroes = [

        r"/product/(\d+)/(\d+)",

        r"/opaanlp/(\d+)/(\d+)",

        r"-i\.(\d+)\.(\d+)",

        r"shopid[=/](\d+).*?itemid[=/](\d+)",

        r"itemid[=/](\d+).*?shopid[=/](\d+)"
    ]

    for indice, padrao in enumerate(padroes):

        match = re.search(
            padrao,
            texto,
            re.IGNORECASE
        )

        if not match:
            continue

        if indice == 4:

            item_id = match.group(1)
            shop_id = match.group(2)

        else:

            shop_id = match.group(1)
            item_id = match.group(2)

        break

    # --------------------------------------------------------
    # QUERY STRING
    # --------------------------------------------------------

    try:

        parsed = urlparse(texto)

        params = dict(
            parse_qsl(
                parsed.query,
                keep_blank_values=True
            )
        )

        if not shop_id:

            shop_id = (
                params.get("shopid")
                or
                params.get("shop_id")
            )

        if not item_id:

            item_id = (
                params.get("itemid")
                or
                params.get("item_id")
            )

    except Exception:
        pass

    if shop_id and item_id:

        log(
            "[SHOPEE] IDs encontrados:",
            shop_id,
            item_id
        )

        return str(shop_id), str(item_id)

    log(
        "[SHOPEE] Nenhum shopId/itemId encontrado."
    )

    return None, None


# ============================================================
# RESOLVER LINK
# ============================================================

def resolver_url_shopee(url):

    log("========================================")
    log("[SHOPEE] Tentando resolver URL:")
    log(url)
    log("========================================")

    headers = {
        "User-Agent":
            "Mozilla/5.0 (Linux; Android 13) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0 Mobile Safari/537.36",
        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8"
    }

    urls_tentar = [
        url,
        url + "?__classic__=1"
    ]

    for numero, url_teste in enumerate(
        urls_tentar,
        start=1
    ):

        try:

            log(
                f"[SHOPEE] Tentativa {numero}"
            )

            resposta = requests.get(
                url_teste,
                headers=headers,
                timeout=25,
                allow_redirects=True
            )

            log(
                "[SHOPEE] HTTP:",
                resposta.status_code
            )

            log(
                "[SHOPEE] URL final HTTP:",
                resposta.url
            )

            if resposta.status_code != 200:
                continue

            url_final = resposta.url

            # ----------------------------------------------
            # Verifica URL final
            # ----------------------------------------------

            shop_id, item_id = extrair_ids_shopee(
                url_final
            )

            if shop_id and item_id:

                return {
                    "url": url_final,
                    "shop_id": shop_id,
                    "item_id": item_id,
                    "html": resposta.text
                }

            # ----------------------------------------------
            # Procurar URLs no HTML
            # ----------------------------------------------

            html = resposta.text

            encontrados = re.findall(
                r'https?://[^"\']+',
                html
            )

            for encontrada in encontrados:

                encontrada = (
                    encontrada
                    .replace(
                        "\\u002F",
                        "/"
                    )
                    .replace(
                        "\\/",
                        "/"
                    )
                )

                sid, iid = extrair_ids_shopee(
                    encontrada
                )

                if sid and iid:

                    log(
                        "[SHOPEE] URL de produto encontrada no HTML:",
                        encontrada
                    )

                    return {
                        "url": encontrada,
                        "shop_id": sid,
                        "item_id": iid,
                        "html": html
                    }

            # ----------------------------------------------
            # Mesmo sem IDs, retorna HTML para metadata
            # ----------------------------------------------

            return {
                "url": url_final,
                "shop_id": None,
                "item_id": None,
                "html": html
            }

        except Exception as erro:

            log(
                "[SHOPEE] Erro tentativa:",
                erro
            )

    return {
        "url": url,
        "shop_id": None,
        "item_id": None,
        "html": ""
    }


# ============================================================
# PRODUCT OFFER V2 - POR ID
# ============================================================

def buscar_produto_por_ids(
    shop_id,
    item_id
):

    if not shop_id or not item_id:
        return None

    query = """
query GetProductOffer(
    $shopId: Int!,
    $itemId: Int!
) {
    productOfferV2(
        shopId: $shopId,
        itemId: $itemId
    ) {
        nodes {
            itemId
            shopId
            productName
            productLink
            offerLink
            imageUrl
            priceMin
            priceMax
            priceDiscountRate
            commissionRate
            sales
            ratingStar
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

    resultado = shopee_graphql(
        query=query,
        variables={
            "shopId": int(shop_id),
            "itemId": int(item_id)
        },
        operation_name="GetProductOffer"
    )

    if not resultado.get("ok"):

        log(
            "[PRODUTO] productOfferV2 por ID falhou:",
            resultado.get("erro")
        )

        return None

    try:

        data = resultado["dados"]["data"]

        oferta = data.get(
            "productOfferV2"
        )

        if not oferta:
            return None

        nodes = oferta.get(
            "nodes",
            []
        )

        if not nodes:
            return None

        produto = nodes[0]

        log(
            "[PRODUTO] Produto encontrado pela API:",
            produto
        )

        return normalizar_produto_api(
            produto
        )

    except Exception as erro:

        log(
            "[PRODUTO] Erro interpretando productOfferV2:",
            erro
        )

        return None


# ============================================================
# PRODUCT OFFER V2 - BUSCA POR LINK
# ============================================================

def buscar_produto_por_link(
    link
):

    if not link:
        return None

    # --------------------------------------------------------
    # Algumas versões da API aceitam productLink como filtro.
    # Fazemos uma busca pequena e tentamos encontrar o link.
    # --------------------------------------------------------

    query = """
query ProductOffers {
    productOfferV2(
        keyword: ""
        listType: 1
        sortType: 1
        page: 1
        limit: 20
    ) {
        nodes {
            itemId
            shopId
            productName
            productLink
            offerLink
            imageUrl
            priceMin
            priceMax
            priceDiscountRate
            commissionRate
            sales
            ratingStar
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

    resultado = shopee_graphql(
        query=query,
        operation_name="ProductOffers"
    )

    if not resultado.get("ok"):

        log(
            "[PRODUTO] Busca geral productOfferV2 falhou:",
            resultado.get("erro")
        )

        return None

    try:

        nodes = (
            resultado["dados"]
            .get("data", {})
            .get("productOfferV2", {})
            .get("nodes", [])
        )

        alvo = link.rstrip("/").lower()

        for produto in nodes:

            links_comparar = [
                produto.get("productLink", ""),
                produto.get("offerLink", "")
            ]

            for candidato in links_comparar:

                if not candidato:
                    continue

                if (
                    candidato.rstrip("/").lower()
                    == alvo
                ):

                    return normalizar_produto_api(
                        produto
                    )

        return None

    except Exception as erro:

        log(
            "[PRODUTO] Erro busca por link:",
            erro
        )

        return None


# ============================================================
# NORMALIZAR PRODUTO API
# ============================================================

def normalizar_produto_api(produto):

    if not produto:
        return None

    nome = (
        produto.get("productName")
        or
        produto.get("name")
        or
        ""
    ).strip()

    imagem = (
        produto.get("imageUrl")
        or
        ""
    ).strip()

    link_produto = (
        produto.get("productLink")
        or
        produto.get("offerLink")
        or
        ""
    ).strip()

    preco_min = produto.get(
        "priceMin"
    )

    preco_max = produto.get(
        "priceMax"
    )

    desconto = produto.get(
        "priceDiscountRate"
    )

    if not nome:
        return None

    return {
        "titulo": nome,
        "imagem": imagem,
        "preco_atual": preco_min,
        "preco_max": preco_max,
        "desconto": desconto,
        "link": link_produto,
        "offer_link": (
            produto.get("offerLink")
            or
            ""
        ),
        "item_id": produto.get("itemId"),
        "shop_id": produto.get("shopId"),
        "shop_name": produto.get("shopName"),
        "sales": produto.get("sales"),
        "rating": produto.get("ratingStar"),
        "origem": "shopee_api"
    }


# ============================================================
# EXTRAIR METADATA DO HTML
# ============================================================

def extrair_metadata_html(html):

    if not html:
        return None

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        def meta(
            *chaves
        ):

            for chave in chaves:

                tag = soup.find(
                    "meta",
                    attrs={
                        "property": chave
                    }
                )

                if not tag:

                    tag = soup.find(
                        "meta",
                        attrs={
                            "name": chave
                        }
                    )

                if tag and tag.get("content"):

                    return tag.get(
                        "content"
                    ).strip()

            return ""

        titulo = (
            meta(
                "og:title",
                "twitter:title"
            )
            or
            (
                soup.title.string.strip()
                if soup.title and soup.title.string
                else ""
            )
        )

        imagem = meta(
            "og:image",
            "twitter:image"
        )

        descricao = meta(
            "og:description",
            "description"
        )

        # ----------------------------------------------------
        # Procurar preço no texto/HTML
        # ----------------------------------------------------

        texto = soup.get_text(
            " ",
            strip=True
        )

        precos = re.findall(
            r'R\$\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?',
            texto
        )

        preco = ""

        if precos:
            preco = precos[0]

        # ----------------------------------------------------
        # Remover título genérico da Shopee
        # ----------------------------------------------------

        titulo_baixo = titulo.lower()

        titulos_invalidos = [
            "shopee brasil",
            "ofertas incríveis",
            "melhores preços do mercado",
            "shopee brasil | ofertas"
        ]

        if any(
            item in titulo_baixo
            for item in titulos_invalidos
        ):

            titulo = ""

        if not titulo and not imagem and not preco:
            return None

        return {
            "titulo": titulo,
            "imagem": imagem,
            "preco_atual": preco,
            "preco_max": "",
            "desconto": "",
            "link": "",
            "offer_link": "",
            "item_id": None,
            "shop_id": None,
            "shop_name": "",
            "sales": None,
            "rating": None,
            "descricao": descricao,
            "origem": "html"
        }

    except Exception as erro:

        log(
            "[HTML] Erro extraindo metadata:",
            erro
        )

        return None


# ============================================================
# GERAR SHORT LINK
# ============================================================

def gerar_short_link(
    origin_url
):

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

    resultado = shopee_graphql(
        query=query,
        variables={
            "input": {
                "originUrl": origin_url
            }
        },
        operation_name="GenerateShortLink"
    )

    if not resultado.get("ok"):

        log(
            "[SHOPEE API] Falha generateShortLink:",
            resultado.get("erro")
        )

        return None

    try:

        short_link = (
            resultado["dados"]
            ["data"]
            ["generateShortLink"]
            ["shortLink"]
        )

        log(
            "[SHOPEE API] ShortLink gerado:",
            short_link
        )

        return short_link

    except Exception as erro:

        log(
            "[SHOPEE API] Resposta sem shortLink:",
            erro
        )

        return None


# ============================================================
# FORMATAR PREÇO
# ============================================================

def formatar_preco(valor):

    if valor is None:
        return ""

    if isinstance(valor, str):

        valor = valor.strip()

        if valor.startswith("R$"):
            return valor

        # Caso já venha como número em string
        try:
            valor = float(
                valor.replace(
                    ".",
                    ""
                ).replace(
                    ",",
                    "."
                )
            )
        except Exception:
            return valor

    try:

        return (
            "R$ "
            +
            f"{float(valor):,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except Exception:

        return str(valor)


# ============================================================
# MONTAR TEXTO DO PRODUTO
# ============================================================

def montar_legenda(
    produto,
    link
):

    titulo = (
        produto.get("titulo")
        or
        "Produto Shopee"
    ).strip()

    preco = formatar_preco(
        produto.get("preco_atual")
    )

    preco_max = formatar_preco(
        produto.get("preco_max")
    )

    desconto = produto.get(
        "desconto"
    )

    short_link = (
        produto.get("short_link")
        or
        link
    )

    partes = []

    partes.append(
        "🦊 <b>OFERTA SHOPEE</b>"
    )

    partes.append("")

    partes.append(
        f"🔥 <b>{titulo}</b>"
    )

    if preco:

        if (
            preco_max
            and
            preco_max != preco
        ):

            partes.append(
                f"💰 <b>{preco}</b>"
            )

            partes.append(
                f"🏷️ De: {preco_max}"
            )

        else:

            partes.append(
                f"💰 <b>{preco}</b>"
            )

    if desconto not in (
        None,
        "",
        0,
        "0"
    ):

        try:

            partes.append(
                f"🔥 {desconto}% OFF"
            )

        except Exception:
            pass

    partes.append("")

    partes.append(
        "🛒 <b>COMPRAR NA SHOPEE</b>"
    )

    partes.append(
        f"👉 {short_link}"
    )

    return "\n".join(partes)


# ============================================================
# PROCESSAR PRODUTO
# ============================================================

def processar_produto(link):

    log("========================================")
    log("[PRODUTO] Abrindo link:")
    log(link)
    log("========================================")

    resolvido = resolver_url_shopee(
        link
    )

    url_final = resolvido.get(
        "url"
    ) or link

    shop_id = resolvido.get(
        "shop_id"
    )

    item_id = resolvido.get(
        "item_id"
    )

    html = resolvido.get(
        "html",
        ""
    )

    log(
        "[PRODUTO] URL final:",
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

    produto = None

    # --------------------------------------------------------
    # 1. API por IDs
    # --------------------------------------------------------

    if shop_id and item_id:

        log(
            "[PRODUTO] Consultando ProductOfferV2..."
        )

        produto = buscar_produto_por_ids(
            shop_id,
            item_id
        )

    else:

        log(
            "[PRODUTO] Não há IDs para consultar ProductOfferV2."
        )

    # --------------------------------------------------------
    # 2. Tentar metadata HTML
    # --------------------------------------------------------

    if not produto:

        log(
            "[PRODUTO] API não retornou produto."
        )

        log(
            "[PRODUTO] Tentando metadata HTML..."
        )

        produto = extrair_metadata_html(
            html
        )

    # --------------------------------------------------------
    # 3. Se ainda não encontrou, erro.
    # --------------------------------------------------------

    if not produto:

        return {
            "sucesso": False,
            "erro":
                "A Shopee não retornou os dados do produto.",
            "link": link,
            "url_final": url_final,
            "shop_id": shop_id,
            "item_id": item_id,
            "short_link": None
        }

    # --------------------------------------------------------
    # 4. Validar título
    # --------------------------------------------------------

    titulo = (
        produto.get("titulo")
        or
        ""
    ).strip()

    if not titulo:

        return {
            "sucesso": False,
            "erro":
                "Foi encontrado conteúdo da Shopee, "
                "mas não foi possível identificar o nome do produto.",
            "link": link,
            "url_final": url_final,
            "shop_id": shop_id,
            "item_id": item_id,
            "short_link": None
        }

    # --------------------------------------------------------
    # 5. Gerar link de afiliado
    # --------------------------------------------------------

    url_para_afiliado = (
        produto.get("link")
        or
        produto.get("offer_link")
        or
        url_final
        or
        link
    )

    log(
        "[PRODUTO] URL usada para afiliado:",
        url_para_afiliado
    )

    short_link = gerar_short_link(
        url_para_afiliado
    )

    # --------------------------------------------------------
    # 6. Se não gerou short link, ainda podemos usar
    #    offer_link caso exista.
    # --------------------------------------------------------

    if not short_link:

        short_link = (
            produto.get("offer_link")
            or
            ""
        )

    if not short_link:

        return {
            "sucesso": False,
            "erro":
                "Os dados do produto foram encontrados, "
                "mas a Shopee não conseguiu gerar o link de afiliado.",
            "link": link,
            "url_final": url_final,
            "shop_id": shop_id,
            "item_id": item_id,
            "short_link": None,
            "produto": produto
        }

    produto["short_link"] = short_link

    # --------------------------------------------------------
    # 7. Legenda
    # --------------------------------------------------------

    legenda = montar_legenda(
        produto,
        short_link
    )

    produto["legenda"] = legenda

    log("========================================")
    log(
        "[PRODUTO] Título:",
        produto.get("titulo")
    )

    log(
        "[PRODUTO] Preço:",
        produto.get("preco_atual")
    )

    log(
        "[PRODUTO] Imagem:",
        produto.get("imagem")
    )

    log(
        "[PRODUTO] ShortLink:",
        short_link
    )

    log("========================================")

    return {
        "sucesso": True,
        "link": link,
        "url_final": url_final,
        "shop_id": shop_id,
        "item_id": item_id,
        "short_link": short_link,
        "produto": produto
    }


# ============================================================
# PROCESSAR TAREFA
# ============================================================

def executar_tarefa(
    task_id,
    links,
    intervalo,
    quantidade,
    usuario
):

    log(
        "[TASK] Iniciando",
        task_id
    )

    with tarefas_lock:

        tarefas[task_id] = {
            "status": "processando",
            "task_id": task_id,
            "total": len(links),
            "processados": 0,
            "publicados": 0,
            "erros": []
        }

    try:

        for indice, link in enumerate(
            links,
            start=1
        ):

            log("========================================")
            log(
                f"[TASK] Produto {indice}/{len(links)}"
            )

            log(
                "[TELEGRAM] Link:",
                link
            )

            resultado = processar_produto(
                link
            )

            if not resultado.get(
                "sucesso"
            ):

                erro = {
                    "produto": indice,
                    "link": link,
                    "erro":
                        resultado.get(
                            "erro",
                            "Erro desconhecido."
                        )
                }

                log(
                    "[TASK] ERRO:",
                    erro
                )

                with tarefas_lock:

                    tarefas[task_id][
                        "erros"
                    ].append(
                        erro
                    )

                    tarefas[task_id][
                        "processados"
                    ] = indice

                # Não publica conteúdo incorreto
                continue

            produto = resultado[
                "produto"
            ]

            legenda = produto[
                "legenda"
            ]

            imagem = produto.get(
                "imagem"
            )

            log(
                "[TELEGRAM] Publicando:",
                produto.get("titulo")
            )

            log(
                "[TELEGRAM] Link:",
                resultado.get(
                    "short_link"
                )
            )

            if imagem:

                sucesso, retorno = (
                    telegram_publicar_foto(
                        imagem,
                        legenda
                    )
                )

            else:

                sucesso, retorno = (
                    telegram_publicar_texto(
                        legenda
                    )
                )

            if sucesso:

                log(
                    "[TELEGRAM] Produto publicado."
                )

                with tarefas_lock:

                    tarefas[task_id][
                        "publicados"
                    ] += 1

            else:

                erro = {
                    "produto": indice,
                    "link": link,
                    "erro":
                        f"Telegram: {retorno}"
                }

                with tarefas_lock:

                    tarefas[task_id][
                        "erros"
                    ].append(
                        erro
                    )

            with tarefas_lock:

                tarefas[task_id][
                    "processados"
                ] = indice

            # ------------------------------------------------
            # Intervalo
            # ------------------------------------------------

            if indice < len(links):

                log(
                    f"[TASK] Aguardando {intervalo}s..."
                )

                time.sleep(
                    intervalo
                )

        with tarefas_lock:

            tarefas[task_id][
                "status"
            ] = "concluida"

            tarefas[task_id][
                "finalizada_em"
            ] = int(
                time.time()
            )

        log(
            "[TASK] Finalizada",
            task_id
        )

    except Exception as erro:

        log(
            "[TASK] ERRO FATAL:",
            erro
        )

        with tarefas_lock:

            tarefas[task_id][
                "status"
            ] = "erro"

            tarefas[task_id][
                "erro"
            ] = str(erro)

            tarefas[task_id][
                "finalizada_em"
            ] = int(
                time.time()
            )


# ============================================================
# API CONFIGURAR
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    log("========================================")
    log("[API] POST /api/configurar")

    try:

        dados = request.get_json(
            silent=True
        )

        if not dados:

            return jsonify({
                "sucesso": False,
                "erro":
                    "JSON inválido ou vazio."
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
                "sucesso": False,
                "erro":
                    "O campo links precisa ser uma lista."
            }), 400

        # ----------------------------------------------------
        # Limpeza
        # ----------------------------------------------------

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
                    "Informe pelo menos um link da Shopee."
            }), 400

        if len(links) > MAX_LINKS:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Máximo de 20 links."
            }), 400

        try:

            intervalo = int(
                intervalo
            )

        except Exception:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Intervalo inválido."
            }), 400

        if intervalo not in INTERVALOS_PERMITIDOS:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Intervalo inválido. "
                    "Use 10, 60, 300 ou 600 segundos."
            }), 400

        try:

            quantidade = int(
                quantidade
            )

        except Exception:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Quantidade inválida."
            }), 400

        if quantidade < 1:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Quantidade mínima é 1."
            }), 400

        if quantidade > len(links):

            quantidade = len(links)

        # ----------------------------------------------------
        # Validar URLs
        # ----------------------------------------------------

        for link in links:

            try:

                parsed = urlparse(
                    link
                )

                hostname = (
                    parsed.hostname
                    or
                    ""
                ).lower()

                if (
                    parsed.scheme
                    not in
                    ("http", "https")
                ):

                    return jsonify({
                        "sucesso": False,
                        "erro":
                            f"Link inválido: {link}"
                    }), 400

                if "shopee" not in hostname:

                    return jsonify({
                        "sucesso": False,
                        "erro":
                            f"O link não parece ser da Shopee: {link}"
                    }), 400

            except Exception:

                return jsonify({
                    "sucesso": False,
                    "erro":
                        f"Link inválido: {link}"
                }), 400

        # ----------------------------------------------------
        # Configuração
        # ----------------------------------------------------

        log(
            "[TELEGRAM] Usuário:",
            usuario
        )

        log(
            "[TELEGRAM] Canal:",
            CHANNEL_USERNAME
        )

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
            bool(SHOPEE_SECRET)
        )

        # ----------------------------------------------------
        # Verificar credenciais mínimas
        # ----------------------------------------------------

        if not BOT_TOKEN:

            return jsonify({
                "sucesso": False,
                "erro":
                    "BOT_TOKEN não configurado no servidor."
            }), 500

        if not CHANNEL_USERNAME:

            return jsonify({
                "sucesso": False,
                "erro":
                    "CHANNEL_USERNAME não configurado no servidor."
            }), 500

        if not SHOPEE_APP_ID:

            return jsonify({
                "sucesso": False,
                "erro":
                    "SHOPEE_APP_ID não configurado no servidor."
            }), 500

        if not SHOPEE_SECRET:

            return jsonify({
                "sucesso": False,
                "erro":
                    "SHOPEE_SECRET não configurado no servidor."
            }), 500

        # ----------------------------------------------------
        # Criar tarefa
        # ----------------------------------------------------

        task_id = str(
            uuid.uuid4()
        )

        with tarefas_lock:

            tarefas[task_id] = {
                "status": "aguardando",
                "task_id": task_id,
                "total": quantidade,
                "processados": 0,
                "publicados": 0,
                "erros": []
            }

        thread = threading.Thread(
            target=executar_tarefa,
            args=(
                task_id,
                links[:quantidade],
                intervalo,
                quantidade,
                usuario
            ),
            daemon=True
        )

        thread.start()

        log(
            "[API] Task criada:",
            task_id
        )

        return jsonify({
            "sucesso": True,
            "mensagem":
                "Automação iniciada com sucesso!",
            "task_id": task_id
        })

    except Exception as erro:

        log(
            "[API] Erro:",
            erro
        )

        return jsonify({
            "sucesso": False,
            "erro": str(erro)
        }), 500


# ============================================================
# API STATUS
# ============================================================

@app.route(
    "/api/status/<task_id>",
    methods=["GET"]
)
def status_task(task_id):

    with tarefas_lock:

        tarefa = tarefas.get(
            task_id
        )

        if not tarefa:

            return jsonify({
                "status": "nao_encontrada",
                "erro":
                    "Tarefa não encontrada."
            }), 404

        return jsonify(
            tarefa
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

        # GET serve apenas para verificar conectividade.
        # A API GraphQL propriamente dita usa POST.

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
                len(
                    resposta.content
                ),

            "url_final":
                resposta.url
        })

    except Exception as erro:

        return jsonify({

            "sucesso": False,

            "erro": str(erro)
        }), 500


# ============================================================
# DEBUG - TESTAR GRAPHQL
# ============================================================

@app.route(
    "/debug-shopee-graphql",
    methods=["GET"]
)
def debug_shopee_graphql():

    query = """
query TestOffers {
    productOfferV2(
        keyword: "celular"
        listType: 1
        sortType: 1
        page: 1
        limit: 3
    ) {
        nodes {
            itemId
            shopId
            productName
            productLink
            offerLink
            imageUrl
            priceMin
            priceMax
            priceDiscountRate
        }
        pageInfo {
            page
            limit
            hasNextPage
        }
    }
}
"""

    resultado = shopee_graphql(
        query=query,
        operation_name="TestOffers"
    )

    # Nunca devolve Secret.
    return jsonify({
        "sucesso":
            resultado.get(
                "ok",
                False
            ),

        "http_status":
            resultado.get(
                "http_status"
            ),

        "erro":
            resultado.get(
                "erro"
            ),

        "tem_dados":
            bool(
                resultado.get(
                    "dados"
                )
            )
    })


# ============================================================
# DEBUG - TESTAR SHORT LINK
# ============================================================

@app.route(
    "/debug-shopee-shortlink",
    methods=["GET"]
)
def debug_shopee_shortlink():

    link = request.args.get(
        "link",
        ""
    ).strip()

    if not link:

        return jsonify({
            "sucesso": False,
            "erro":
                "Informe ?link=https://..."
        }), 400

    resultado = gerar_short_link(
        link
    )

    if not resultado:

        return jsonify({
            "sucesso": False,
            "erro":
                "Não foi possível gerar short link."
        }), 500

    return jsonify({
        "sucesso": True,
        "short_link": resultado
    })


# ============================================================
# DEBUG - TESTAR PRODUTO
# ============================================================

@app.route(
    "/debug-produto",
    methods=["GET"]
)
def debug_produto():

    link = request.args.get(
        "link",
        ""
    ).strip()

    if not link:

        return jsonify({
            "sucesso": False,
            "erro":
                "Informe ?link=https://..."
        }), 400

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

        "status": "ok",

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
# TESTE
# ============================================================

@app.route(
    "/api/teste",
    methods=["GET"]
)
def teste():

    return jsonify({

        "sucesso": True,

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
