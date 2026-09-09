import os
import json
import re
import time
import uuid
import threading
import hashlib

from urllib.parse import urlparse, parse_qs, unquote

import requests

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from playwright.sync_api import sync_playwright


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

            tarefas[task_id].update(dados)


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

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# SHOPEE GRAPHQL
# ============================================================

def shopee_assinatura(payload):

    timestamp = int(time.time())

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
        payload_obj["operationName"] = operation_name

    if variables is not None:
        payload_obj["variables"] = variables

    payload = json.dumps(
        payload_obj,
        ensure_ascii=False,
        separators=(",", ":")
    )

    timestamp, assinatura = shopee_assinatura(
        payload
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization":
            f"SHA256 Credential={SHOPEE_APP_ID},"
            f"Timestamp={timestamp},"
            f"Signature={assinatura}",
        "User-Agent":
            "Raposa-Cacadora/3.0"
    }

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

        try:
            dados = resposta.json()

        except Exception:

            return {
                "ok": False,
                "http_status": resposta.status_code,
                "erro": "Resposta não é JSON.",
                "texto": resposta.text[:5000]
            }

        if resposta.status_code != 200:

            return {
                "ok": False,
                "http_status": resposta.status_code,
                "dados": dados,
                "erro": "HTTP diferente de 200."
            }

        if dados.get("errors"):

            return {
                "ok": False,
                "http_status": resposta.status_code,
                "dados": dados,
                "erro": dados["errors"]
            }

        return {
            "ok": True,
            "http_status": resposta.status_code,
            "dados": dados
        }

    except Exception as erro:

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# GERAR LINK DE AFILIADO
# ============================================================

def shopee_generate_short_link(origin_url):

    query = """
mutation GenerateShortLink($input: ShortLinkInput!) {
  generateShortLink(input: $input) {
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

        return {
            "ok": False,
            "erro": resultado.get("erro"),
            "dados": resultado.get("dados")
        }

    try:

        short_link = (
            resultado["dados"]
            ["data"]
            ["generateShortLink"]
            ["shortLink"]
        )

    except Exception:

        return {
            "ok": False,
            "erro": "Shopee não retornou shortLink.",
            "dados": resultado.get("dados")
        }

    return {
        "ok": True,
        "shortLink": short_link
    }


# ============================================================
# PLAYWRIGHT + CHROMIUM
# ============================================================

def resolver_url_shopee(link):

    print("=" * 60)
    print("[PLAYWRIGHT] RESOLVENDO LINK")
    print(link)
    print("=" * 60)

    navegador = None

    try:

        with sync_playwright() as p:

            navegador = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-zygote"
                ]
            )

            pagina = navegador.new_page(
                viewport={
                    "width": 390,
                    "height": 844
                },
                user_agent=(
                    "Mozilla/5.0 "
                    "(Linux; Android 15) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/151.0.0.0 "
                    "Mobile Safari/537.36"
                ),
                locale="pt-BR"
            )

            pagina.set_default_timeout(60000)

            urls_observadas = []

            def observar_resposta(resposta):

                try:

                    url = resposta.url

                    if "shopee.com.br" in url.lower():

                        urls_observadas.append(url)

                except Exception:

                    pass

            pagina.on(
                "response",
                observar_resposta
            )

            print(
                "[PLAYWRIGHT] Abrindo..."
            )

            pagina.goto(
                link,
                wait_until="domcontentloaded",
                timeout=60000
            )

            print(
                "[PLAYWRIGHT] URL inicial:",
                pagina.url
            )

            # Dá tempo para JavaScript/redirecionamentos.
            pagina.wait_for_timeout(5000)

            # Tenta aguardar a rede estabilizar.
            try:

                pagina.wait_for_load_state(
                    "networkidle",
                    timeout=15000
                )

            except Exception:

                pass

            pagina.wait_for_timeout(3000)

            url_final = pagina.url

            html = pagina.content()

            print(
                "[PLAYWRIGHT] URL FINAL:",
                url_final
            )

            print(
                "[PLAYWRIGHT] HTML:",
                len(html),
                "bytes"
            )

            print(
                "[PLAYWRIGHT] URLs observadas:",
                len(urls_observadas)
            )

            # =================================================
            # Procurar links de produto no HTML
            # =================================================

            links_produto = []

            padroes = [

                r'https?://[^"\']*shopee\.com\.br/[^"\']+',

                r'https?:\\/\\/[^"\']*shopee\.com\.br\\/[^"\']+',

                r'productLink["\']?\s*[:=]\s*["\']([^"\']+)',

                r'canonical["\']?\s*[:=]\s*["\']([^"\']+)'
            ]

            for padrao in padroes:

                try:

                    encontrados = re.findall(
                        padrao,
                        html,
                        re.IGNORECASE
                    )

                    for encontrado in encontrados:

                        if isinstance(
                            encontrado,
                            tuple
                        ):

                            encontrado = encontrado[0]

                        encontrado = (
                            str(encontrado)
                            .replace("\\/", "/")
                            .replace("\\u002F", "/")
                        )

                        encontrado = normalizar_url(
                            encontrado
                        )

                        if (
                            "shopee.com.br"
                            in encontrado.lower()
                            and
                            encontrado not in links_produto
                        ):

                            links_produto.append(
                                encontrado
                            )

                except Exception:

                    pass

            # Também analisa URLs observadas.
            for url in urls_observadas:

                url = normalizar_url(url)

                if (
                    url not in links_produto
                    and
                    "shopee.com.br" in url.lower()
                ):

                    links_produto.append(url)

            print(
                "[PLAYWRIGHT] Links encontrados:",
                len(links_produto)
            )

            return {
                "ok": True,
                "url": url_final,
                "html": html,
                "links_produto": links_produto
            }

    except Exception as erro:

        print(
            "[PLAYWRIGHT] ERRO:",
            erro
        )

        return {
            "ok": False,
            "url": link,
            "html": "",
            "links_produto": [],
            "erro": str(erro)
        }

    finally:

        try:

            if navegador:
                navegador.close()

        except Exception:

            pass


# ============================================================
# EXTRAIR IDS
# ============================================================

def extrair_ids_shopee(url):

    if not url:
        return None, None

    url = normalizar_url(url)

    padroes = [

        r"/product/(\d+)/(\d+)",

        r"-i\.(\d+)\.(\d+)",

        r"/(\d{5,})/(\d{5,})(?:[/?#]|$)"
    ]

    for padrao in padroes:

        match = re.search(
            padrao,
            url,
            re.IGNORECASE
        )

        if match:

            return (
                match.group(1),
                match.group(2)
            )

    try:

        parsed = urlparse(url)

        params = parse_qs(
            parsed.query
        )

        shop_id = None
        item_id = None

        for chave in (
            "shopid",
            "shopId",
            "shop_id"
        ):

            if params.get(chave):

                shop_id = params[chave][0]

                break

        for chave in (
            "itemid",
            "itemId",
            "item_id"
        ):

            if params.get(chave):

                item_id = params[chave][0]

                break

        return shop_id, item_id

    except Exception:

        return None, None


# ============================================================
# METADATA
# ============================================================

def extrair_meta(html, propriedade):

    if not html:
        return ""

    padroes = [

        rf'<meta[^>]+property=["\']'
        rf'{re.escape(propriedade)}'
        rf'["\'][^>]+content=["\']'
        rf'(.*?)["\']',

        rf'<meta[^>]+content=["\']'
        rf'(.*?)["\'][^>]+property=["\']'
        rf'{re.escape(propriedade)}'
        rf'["\']'
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
# JSON-LD
# ============================================================

def extrair_produto_jsonld(html):

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

        objetos = (
            dados
            if isinstance(dados, list)
            else [dados]
            if isinstance(dados, dict)
            else []
        )

        for obj in objetos:

            if not isinstance(obj, dict):
                continue

            tipo = obj.get("@type")

            if not (
                tipo == "Product"
                or (
                    isinstance(tipo, list)
                    and "Product" in tipo
                )
            ):

                continue

            nome = obj.get("name", "")

            imagem = obj.get("image", "")

            preco = ""

            offers = obj.get("offers")

            if isinstance(offers, dict):

                preco = (
                    offers.get("price")
                    or
                    offers.get("lowPrice")
                    or
                    ""
                )

            elif isinstance(offers, list) and offers:

                preco = (
                    offers[0].get("price")
                    or
                    offers[0].get("lowPrice")
                    or
                    ""
                )

            if isinstance(imagem, list):

                imagem = (
                    imagem[0]
                    if imagem
                    else ""
                )

            return {
                "productName": nome,
                "price": preco,
                "imageUrl": imagem
            }

    return None


# ============================================================
# EXTRAIR PRODUTO
# ============================================================

def extrair_produto_html(
    html,
    url_final
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

    jsonld = extrair_produto_jsonld(
        html
    )

    if jsonld:

        titulo = (
            jsonld.get("productName")
            or
            titulo
        )

        imagem = (
            jsonld.get("imageUrl")
            or
            imagem
        )

        preco = (
            jsonld.get("price")
            or
            ""
        )

    # Título HTML
    if not titulo:

        match = re.search(
            r"<title[^>]*>(.*?)</title>",
            html,
            re.IGNORECASE |
            re.DOTALL
        )

        if match:

            titulo = limpar_html_texto(
                match.group(1)
            )

    # ========================================================
    # Preço
    # ========================================================

    if not preco:

        padroes_preco = [

            r'"price"\s*:\s*"([^"]+)"',

            r'"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',

            r'"priceMin"\s*:\s*"([^"]+)"',

            r'"priceMin"\s*:\s*([0-9]+(?:\.[0-9]+)?)',

            r'R\$\s*([0-9]+(?:[.,][0-9]{2})?)'
        ]

        for padrao in padroes_preco:

            match = re.search(
                padrao,
                html,
                re.IGNORECASE
            )

            if match:

                preco = match.group(1)

                break

    titulo = limpar_html_texto(
        titulo
    )

    if not titulo or len(titulo) < 3:
        return None

    # Evita página genérica.
    titulo_lower = titulo.lower()

    termos_genericos = [
        "shopee brasil",
        "ofertas incríveis",
        "ofertas incriveis"
    ]

    if any(
        termo in titulo_lower
        for termo in termos_genericos
    ):

        # Se for somente página genérica,
        # não aceita.
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
            descricao or "",

        "productLink":
            url_final
    }


# ============================================================
# OBTER PRODUTO
# ============================================================

def obter_produto(link):

    print("=" * 60)
    print("[PRODUTO] INICIANDO")
    print("[PRODUTO] LINK:", link)
    print("=" * 60)

    if not url_eh_shopee(link):

        return {
            "ok": False,
            "erro":
                "O link informado não parece ser "
                "uma URL válida da Shopee."
        }

    resolucao = resolver_url_shopee(
        link
    )

    if not resolucao.get("ok"):

        return {
            "ok": False,
            "erro":
                resolucao.get(
                    "erro",
                    "Não foi possível abrir o link."
                )
        }

    url_final = (
        resolucao.get("url")
        or
        link
    )

    html = (
        resolucao.get("html")
        or
        ""
    )

    links_produto = (
        resolucao.get("links_produto")
        or
        []
    )

    print(
        "[PRODUTO] URL FINAL:",
        url_final
    )

    # ========================================================
    # 1. URL final
    # ========================================================

    shop_id, item_id = extrair_ids_shopee(
        url_final
    )

    produto = None
    url_produto = url_final

    # ========================================================
    # 2. Tentar HTML da URL final
    # ========================================================

    if shop_id and item_id:

        produto = extrair_produto_html(
            html,
            url_final
        )

    # ========================================================
    # 3. Procurar URLs internas
    # ========================================================

    if not produto:

        for candidata in links_produto:

            shop_tmp, item_tmp = (
                extrair_ids_shopee(
                    candidata
                )
            )

            if not (
                shop_tmp
                and
                item_tmp
            ):

                continue

            print(
                "[PRODUTO] URL DE PRODUTO ENCONTRADA:",
                candidata
            )

            produto_tmp = extrair_produto_html(
                html,
                candidata
            )

            if produto_tmp:

                produto = produto_tmp
                url_produto = candidata
                shop_id = shop_tmp
                item_id = item_tmp

                break

    # ========================================================
    # 4. Se não achou no HTML, tentar carregar a URL
    #    encontrada pelo Playwright novamente.
    # ========================================================

    if not produto and links_produto:

        for candidata in links_produto:

            shop_tmp, item_tmp = (
                extrair_ids_shopee(
                    candidata
                )
            )

            if not (
                shop_tmp
                and
                item_tmp
            ):

                continue

            try:

                nova_resolucao = (
                    resolver_url_shopee(
                        candidata
                    )
                )

                novo_html = (
                    nova_resolucao.get(
                        "html"
                    )
                    or
                    ""
                )

                produto_tmp = (
                    extrair_produto_html(
                        novo_html,
                        candidata
                    )
                )

                if produto_tmp:

                    produto = produto_tmp
                    url_produto = candidata
                    shop_id = shop_tmp
                    item_id = item_tmp

                    break

            except Exception as erro:

                print(
                    "[PRODUTO] Erro ao carregar candidata:",
                    erro
                )

    if not produto:

        return {

            "ok": False,

            "erro":
                "Não foi possível identificar os dados "
                "do produto no short-link da Shopee.",

            "url_final":
                url_final,

            "links_encontrados":
                links_produto,

            "shopId":
                shop_id,

            "itemId":
                item_id
        }

    # ========================================================
    # 5. Gerar link de afiliado
    # ========================================================

    produto["shopId"] = shop_id
    produto["itemId"] = item_id

    short_result = (
        shopee_generate_short_link(
            url_produto
        )
    )

    if short_result.get("ok"):

        short_link = (
            short_result.get(
                "shortLink"
            )
        )

        produto["offerLink"] = short_link

    else:

        print(
            "[SHOPEE] Não conseguiu gerar "
            "short-link de afiliado:",
            short_result.get("erro")
        )

        produto["offerLink"] = url_produto

        short_link = None

    return {

        "ok": True,

        "produto":
            produto,

        "url_final":
            url_produto,

        "shortLink":
            short_link,

        "metodo":
            "PLAYWRIGHT"
    }


# ============================================================
# PREÇO
# ============================================================

def formatar_preco(valor):

    if valor is None:
        return ""

    texto = str(valor).strip()

    if not texto:
        return ""

    if texto.upper().startswith("R$"):
        return texto

    try:

        numero = float(
            texto.replace(",", ".")
        )

        return (
            "R$ "
            +
            f"{numero:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except Exception:

        return texto


# ============================================================
# OFERTA
# ============================================================

def formatar_oferta(
    produto,
    link
):

    nome = (
        produto.get("productName")
        or
        "Oferta Shopee"
    )

    preco = (
        produto.get("price")
        or
        produto.get("priceMin")
        or
        ""
    )

    imagem = (
        produto.get("imageUrl")
        or
        ""
    )

    offer_link = (
        produto.get("offerLink")
        or
        link
    )

    preco_formatado = formatar_preco(
        preco
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
            "\n".join(linhas),

        "imagem":
            imagem,

        "link":
            offer_link
    }


# ============================================================
# PROCESSAR
# ============================================================

def processar_produto(
    link,
    task_id,
    numero,
    total
):

    print("=" * 60)

    print(
        f"[TASK] PRODUTO {numero}/{total}"
    )

    print(
        "[TASK] LINK:",
        link
    )

    print("=" * 60)

    resultado = obter_produto(
        link
    )

    if not resultado.get("ok"):

        print(
            "[PRODUTO] FALHA:",
            resultado.get("erro")
        )

        return {

            "ok": False,

            "erro":
                resultado.get("erro"),

            "link":
                link,

            "shortLink":
                resultado.get("shortLink")
        }

    produto = (
        resultado["produto"]
    )

    oferta = formatar_oferta(
        produto,
        link
    )

    # ========================================================
    # IMAGEM
    # ========================================================

    if oferta["imagem"]:

        telegram_result = (
            telegram_enviar_foto(
                oferta["imagem"],
                oferta["texto"]
            )
        )

        if telegram_result.get("ok"):

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
            "[TELEGRAM] Falha na imagem."
        )

    # ========================================================
    # FALLBACK TEXTO
    # ========================================================

    telegram_result = (
        telegram_enviar_mensagem(
            oferta["texto"]
        )
    )

    if telegram_result.get("ok"):

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
            "Produto encontrado, mas não foi possível "
            "publicar no Telegram.",

        "produto":
            produto,

        "telegram":
            telegram_result
    }


# ============================================================
# TAREFA
# ============================================================

def executar_tarefa(
    task_id,
    links,
    intervalo,
    quantidade
):

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

        for indice in range(total):

            link = links[indice]

            resultado = processar_produto(
                link,
                task_id,
                indice + 1,
                total
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

                time.sleep(
                    intervalo
                )

        sucessos = sum(
            1
            for resultado in resultados
            if resultado.get("ok")
        )

        falhas = (
            len(resultados)
            - sucessos
        )

        atualizar_tarefa(

            task_id,

            status="concluida",

            sucessos=sucessos,

            falhas=falhas,

            resultados=resultados,

            finalizada_em=int(time.time())
        )

    except Exception as erro:

        print(
            "[TASK] ERRO:",
            erro
        )

        atualizar_tarefa(

            task_id,

            status="erro",

            erro=str(erro),

            resultados=resultados,

            finalizada_em=int(time.time())
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
                "sucesso": False,
                "erro": "JSON inválido ou ausente."
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
                    "O campo links deve ser uma lista."
            }), 400

        links = [
            str(link).strip()
            for link in links
            if str(link).strip()
        ]

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
            intervalo = int(intervalo)

        except Exception:

            return jsonify({
                "sucesso": False,
                "erro": "Intervalo inválido."
            }), 400

        if intervalo not in INTERVALOS_PERMITIDOS:

            return jsonify({
                "sucesso": False,
                "erro": "Intervalo inválido."
            }), 400

        try:
            quantidade = int(quantidade)

        except Exception:

            return jsonify({
                "sucesso": False,
                "erro": "Quantidade inválida."
            }), 400

        if quantidade < 1:

            return jsonify({
                "sucesso": False,
                "erro":
                    "Quantidade mínima é 1."
            }), 400

        if quantidade > len(links):

            return jsonify({
                "sucesso": False,
                "erro":
                    "A quantidade não pode ser maior "
                    "que o número de links."
            }), 400

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

        return jsonify({

            "sucesso": True,

            "mensagem":
                "Automação iniciada.",

            "task_id":
                task_id
        })

    except Exception as erro:

        return jsonify({

            "sucesso": False,

            "erro": str(erro)

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
                "sucesso": False,
                "erro":
                    "Tarefa não encontrada."
            }), 404

        return jsonify(tarefa)


# ============================================================
# DEBUG RESOLVER
# ============================================================

@app.route(
    "/debug-resolver",
    methods=["GET"]
)
def debug_resolver():

    link = (
        request.args.get("link")
        or
        request.args.get("url")
        or
        ""
    ).strip()

    if not link:

        return jsonify({
            "sucesso": False,
            "erro":
                "Informe ?link=https://..."
        }), 400

    resultado = resolver_url_shopee(
        link
    )

    return jsonify({

        "sucesso":
            resultado.get("ok"),

        "url_original":
            link,

        "url_final":
            resultado.get("url"),

        "html_bytes":
            len(
                resultado.get(
                    "html",
                    ""
                )
            ),

        "links_produto":
            resultado.get(
                "links_produto",
                []
            ),

        "erro":
            resultado.get("erro")
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
        request.args.get("link")
        or
        request.args.get("url")
        or
        ""
    ).strip()

    if not link:

        return jsonify({
            "sucesso": False,
            "erro":
                "Informe ?link=https://..."
        }), 400

    resultado = obter_produto(
        link
    )

    return jsonify({

        "sucesso":
            resultado.get("ok"),

        "produto":
            resultado.get("produto"),

        "url_final":
            resultado.get("url_final"),

        "shortLink":
            resultado.get("shortLink"),

        "metodo":
            resultado.get("metodo"),

        "erro":
            resultado.get("erro"),

        "links_encontrados":
            resultado.get(
                "links_encontrados",
                []
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

    resultado = telegram_get_me()

    bot = (
        resultado.get("result")
        if resultado.get("ok")
        else None
    )

    return jsonify({

        "BOT_TOKEN": {
            "existe":
                bool(BOT_TOKEN),
            "tamanho":
                len(BOT_TOKEN),
            "mascara":
                mascara_valor(BOT_TOKEN)
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
                if bot
                else None,

            "username":
                bot.get("username")
                if bot
                else None,

            "first_name":
                bot.get("first_name")
                if bot
                else None
        },

        "erro":
            resultado.get("erro")
            or
            resultado.get("description")
    })


# ============================================================
# DEBUG ENV
# ============================================================

@app.route(
    "/debug-env",
    methods=["GET"]
)
def debug_env():

    return jsonify({

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

    return jsonify({

        "status":
            "ok",

        "service":
            "raposa-cacadora",

        "playwright":
            True,

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
                bool(SHOPEE_SECRET)
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
            bool(BOT_TOKEN),

        "shopee_configurada":
            bool(
                SHOPEE_APP_ID
                and
                SHOPEE_SECRET
            ),

        "playwright":
            True,

        "timestamp":
            int(time.time())
    })


# ============================================================
# PÁGINA
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

            "playwright":
                True
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
