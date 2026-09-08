import os
import re
import json
import time
import html
import threading
import hashlib
import hmac
import random

import requests

from bs4 import BeautifulSoup

from urllib.parse import (
    parse_qsl,
    urljoin,
    urlparse,
    unquote
)

from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory
)

from flask_cors import CORS


# ============================================================
# RAPOSA CAÇADORA
# Mercado Livre / meli.la
# ============================================================


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

INDEX_FILE = os.path.join(
    BASE_DIR,
    "index.html"
)

ARQUIVO_HISTORICO = os.path.join(
    BASE_DIR,
    "produtos_postados.txt"
)


# ============================================================
# VARIÁVEIS DE AMBIENTE
# ============================================================

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    ""
).strip()

CHAT_ID = os.getenv(
    "CHAT_ID",
    "@raposacacadora"
).strip()

PORT = int(
    os.getenv(
        "PORT",
        "10000"
    )
)


# ============================================================
# CONFIGURAÇÕES
# ============================================================

MAX_QUANTIDADE = 50

MIN_INTERVALO_MINUTOS = 1

HTTP_TIMEOUT = 15


# ============================================================
# FLASK
# ============================================================

app = Flask(
    __name__,
    static_folder=BASE_DIR
)


# ============================================================
# CORS
# ============================================================

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "https://bot-raposa-cacadora.vercel.app"
            ]
        }
    },
    methods=[
        "GET",
        "POST",
        "OPTIONS"
    ],
    allow_headers=[
        "Content-Type"
    ]
)


# ============================================================
# LOCKS / CONTROLE
# ============================================================

automacoes_lock = threading.Lock()

historico_lock = threading.Lock()

automacoes_ativas = 0


# ============================================================
# SESSÃO HTTP
# ============================================================

session = requests.Session()


# ============================================================
# USER AGENTS
# ============================================================

USER_AGENTS = [

    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),

    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),

    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

]


# ============================================================
# HEADERS
# ============================================================

def obter_headers():

    user_agent = random.choice(
        USER_AGENTS
    )

    return {

        "User-Agent":
            user_agent,

        "Accept":
            (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "image/avif,image/webp,"
                "*/*;q=0.8"
            ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",

        "Accept-Encoding":
            "gzip, deflate, br",

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache",

        "Upgrade-Insecure-Requests":
            "1",

        "Sec-Fetch-Dest":
            "document",

        "Sec-Fetch-Mode":
            "navigate",

        "Sec-Fetch-Site":
            "none",

        "Sec-Fetch-User":
            "?1",

        "Connection":
            "keep-alive"

    }


# ============================================================
# HOME
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return """
    <!DOCTYPE html>
    <html lang="pt-BR">

    <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width,
            initial-scale=1.0"
        >

        <title>Raposa Caçadora</title>

        <style>

            body {
                background:#05070a;
                color:#fff;
                font-family:Arial,sans-serif;
                text-align:center;
                padding-top:50px;
            }

            h1 {
                color:#f97316;
            }

            .online {
                color:#22c55e;
                font-weight:bold;
            }

            a {
                color:#fb923c;
                text-decoration:none;
                font-weight:bold;
            }

        </style>

    </head>

    <body>

        <h1>🦊 Raposa Caçadora</h1>

        <p class="online">
            ● SERVIDOR ONLINE
        </p>

        <p>
            <a href="/app">
                Abrir Mini App
            </a>
        </p>

        <p>
            <a href="/health">
                Health Check
            </a>
        </p>

    </body>

    </html>
    """


# ============================================================
# MINI APP
# ============================================================

@app.route(
    "/app",
    methods=["GET"]
)
def mini_app():

    if not os.path.isfile(
        INDEX_FILE
    ):

        return (
            "❌ index.html não encontrado.",
            404
        )

    return send_from_directory(
        BASE_DIR,
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

    with automacoes_lock:

        ativas = automacoes_ativas

    return jsonify({

        "ok":
            True,

        "servico":
            "Raposa Caçadora",

        "status":
            "online",

        "telegram_configurado":
            bool(TELEGRAM_TOKEN),

        "chat_configurado":
            bool(CHAT_ID),

        "automacoes_ativas":
            ativas

    })


# ============================================================
# VALIDAR TELEGRAM WEB APP
# ============================================================

def validar_init_data(
    init_data
):

    if not init_data:

        print(
            "❌ initData vazio."
        )

        return False

    if not TELEGRAM_TOKEN:

        print(
            "❌ TELEGRAM_TOKEN não configurado."
        )

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

            print(
                "❌ Hash do Telegram não encontrado."
            )

            return False

        data_check_string = "\n".join(
            f"{k}={v}"
            for k, v in sorted(
                dados.items()
            )
        )

        secret_key = hmac.new(
            b"WebAppData",
            TELEGRAM_TOKEN.encode(
                "utf-8"
            ),
            hashlib.sha256
        ).digest()

        calculado = hmac.new(
            secret_key,
            data_check_string.encode(
                "utf-8"
            ),
            hashlib.sha256
        ).hexdigest()

        valido = hmac.compare_digest(
            calculado,
            hash_recebido
        )

        if valido:

            print(
                "✅ Telegram initData válido."
            )

        else:

            print(
                "❌ Telegram initData inválido."
            )

        return valido

    except Exception as e:

        print(
            f"❌ Erro na validação Telegram: {e}"
        )

        return False


# ============================================================
# HISTÓRICO
# ============================================================

def carregar_historico():

    if not os.path.exists(
        ARQUIVO_HISTORICO
    ):

        return set()

    try:

        with historico_lock:

            with open(
                ARQUIVO_HISTORICO,
                "r",
                encoding="utf-8"
            ) as arquivo:

                return {
                    linha.strip()
                    for linha in arquivo
                    if linha.strip()
                }

    except Exception as e:

        print(
            f"⚠️ Erro lendo histórico: {e}"
        )

        return set()


def salvar_historico(
    link
):

    if not link:

        return False

    try:

        with historico_lock:

            with open(
                ARQUIVO_HISTORICO,
                "a",
                encoding="utf-8"
            ) as arquivo:

                arquivo.write(
                    link.strip()
                    + "\n"
                )

        return True

    except Exception as e:

        print(
            f"⚠️ Erro salvando histórico: {e}"
        )

        return False


def limpar_historico():

    try:

        with historico_lock:

            if os.path.exists(
                ARQUIVO_HISTORICO
            ):

                os.remove(
                    ARQUIVO_HISTORICO
                )

        print(
            "🔄 Histórico resetado."
        )

    except Exception as e:

        print(
            f"⚠️ Erro resetando histórico: {e}"
        )


# ============================================================
# CONVERTER PREÇO
# ============================================================

def converter_preco_float(
    preco_str
):

    if not preco_str:

        return 0.0

    try:

        limpo = (
            preco_str
            .replace(
                "R$",
                ""
            )
            .replace(
                " ",
                ""
            )
            .replace(
                ".",
                ""
            )
            .replace(
                ",",
                "."
            )
        )

        return float(
            limpo
        )

    except Exception:

        return 0.0


# ============================================================
# NORMALIZAR URL
# ============================================================

def normalizar_url(
    url,
    base_url=""
):

    if not url:

        return ""

    try:

        url = html.unescape(
            str(url).strip()
        )

        url = url.replace(
            "\\/",
            "/"
        )

        url = unquote(
            url
        )

        if url.startswith(
            "//"
        ):

            url = (
                "https:"
                + url
            )

        elif url.startswith(
            "/"
        ):

            url = urljoin(
                base_url,
                url
            )

        elif not url.startswith(
            (
                "http://",
                "https://"
            )
        ):

            return ""

        return url.split(
            "#"
        )[0]

    except Exception:

        return ""


# ============================================================
# IDENTIFICAR PRODUTO MERCADO LIVRE
# ============================================================

def parece_produto_mercado_livre(
    url
):

    if not url:

        return False

    texto = unquote(
        url
    ).lower()

    padroes = [

        "produto.mercadolivre.com.br",

        "produto.mercadolibre.com",

        "/p/mlb",

        "/p/mlb-",

        "mlb-",

        "mlb_",

        "/up/mlb",

        "/up/mlb-",

        "mercadolivre.com.br/p/",

        "mercadolibre.com/p/"

    ]

    return any(
        padrao in texto
        for padrao in padroes
    )


# ============================================================
# EXTRAIR ID MLB
# ============================================================

def extrair_id_mlb(
    url
):

    if not url:

        return None

    texto = unquote(
        url
    ).upper()

    padroes = [

        r"\bMLB[-_]?(\d{6,15})\b",

        r"/P/(MLB[-_]?\d{6,15})",

        r"/UP/(MLB[-_]?\d{6,15})"

    ]

    for padrao in padroes:

        resultado = re.search(
            padrao,
            texto
        )

        if resultado:

            numero = resultado.group(
                1
            )

            numero = re.sub(
                r"[^0-9]",
                "",
                numero
            )

            return (
                "MLB"
                + numero
            )

    return None


# ============================================================
# ENCONTRAR LINKS NO HTML
# ============================================================

def extrair_links_html(
    soup,
    base_url
):

    links = []

    # --------------------------------------------------------
    # LINKS <a>
    # --------------------------------------------------------

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = normalizar_url(
            a.get("href"),
            base_url
        )

        if not href:

            continue

        if parece_produto_mercado_livre(
            href
        ):

            links.append(
                href
            )

    # --------------------------------------------------------
    # DATA-HREF
    # --------------------------------------------------------

    for tag in soup.find_all():

        for atributo in [
            "data-href",
            "data-url",
            "data-link",
            "data-product-url"
        ]:

            valor = tag.get(
                atributo
            )

            if not valor:

                continue

            valor = normalizar_url(
                valor,
                base_url
            )

            if parece_produto_mercado_livre(
                valor
            ):

                links.append(
                    valor
                )

    return links


# ============================================================
# EXTRAIR LINKS POR REGEX
# ============================================================

def extrair_links_regex(
    texto,
    base_url
):

    links = []

    # URLs completas
    urls = re.findall(
        r'https?://[^"\'>\s]+',
        texto,
        re.IGNORECASE
    )

    for url in urls:

        url = normalizar_url(
            url,
            base_url
        )

        if parece_produto_mercado_livre(
            url
        ):

            links.append(
                url
            )

    # IDs MLB
    ids = re.findall(
        r"\bMLB[-_]?\d{6,15}\b",
        texto,
        re.IGNORECASE
    )

    for item in ids:

        numero = re.sub(
            r"[^0-9]",
            "",
            item
        )

        if not numero:

            continue

        link = (
            "https://www.mercadolivre.com.br/p/"
            "MLB"
            + numero
        )

        links.append(
            link
        )

    return links


# ============================================================
# EXTRAIR PRODUTOS DA VITRINE
# ============================================================

def extrair_produtos_da_pagina(
    texto,
    url_base
):

    if not texto:

        return []

    produtos = []

    try:

        soup = BeautifulSoup(
            texto,
            "html.parser"
        )

    except Exception as e:

        print(
            f"❌ Erro BeautifulSoup: {e}"
        )

        return []

    # ========================================================
    # MÉTODO 1
    # CLASSES DO SEU CÓDIGO ANTIGO
    # ========================================================

    seletores = [

        "li.ui-search-layout__item",

        "div.poly-card",

        "div.ui-search-result__wrapper",

        "div.poly-card--list",

        "div.poly-card--grid"

    ]

    itens = []

    for seletor in seletores:

        encontrados = soup.select(
            seletor
        )

        if encontrados:

            print(
                f"✅ Seletor encontrado:"
                f" {seletor}"
                f" -> {len(encontrados)}"
            )

            itens.extend(
                encontrados
            )

    # Dedupe dos cards
    cards_unicos = []

    ids_cards = set()

    for card in itens:

        identificador = id(
            card
        )

        if identificador in ids_cards:

            continue

        ids_cards.add(
            identificador
        )

        cards_unicos.append(
            card
        )

    print(
        f"📦 Cards detectados:"
        f" {len(cards_unicos)}"
    )

    # ========================================================
    # PROCESSAR CARDS
    # ========================================================

    for item in cards_unicos:

        link_produto = ""

        # ----------------------------------------------------
        # LINK
        # ----------------------------------------------------

        link_elem = item.find(
            "a",
            href=True
        )

        if link_elem:

            link_produto = normalizar_url(
                link_elem.get("href"),
                url_base
            )

        # Procurar qualquer A caso o primeiro não seja produto
        if not parece_produto_mercado_livre(
            link_produto
        ):

            for a in item.find_all(
                "a",
                href=True
            ):

                candidato = normalizar_url(
                    a.get("href"),
                    url_base
                )

                if parece_produto_mercado_livre(
                    candidato
                ):

                    link_produto = candidato

                    break

        if not link_produto:

            continue

        # ----------------------------------------------------
        # TÍTULO
        # ----------------------------------------------------

        titulo = ""

        titulo_elem = (
            item.find(
                "h2"
            )
            or
            item.find(
                "h3"
            )
            or
            item.find(
                "a",
                class_="poly-component__title"
            )
        )

        if titulo_elem:

            titulo = titulo_elem.get_text(
                " ",
                strip=True
            )

        if not titulo:

            aria = link_elem.get(
                "aria-label",
                ""
            ) if link_elem else ""

            titulo = aria.strip()

        if not titulo:

            titulo = (
                "Oportunidade Imperdível "
                "no Mercado Livre"
            )

        # ----------------------------------------------------
        # PREÇO ATUAL
        # ----------------------------------------------------

        preco_atual = ""

        preco_atual_elem = item.find(
            "span",
            class_="andes-money-amount__fraction"
        )

        centavos_atual_elem = item.find(
            "span",
            class_="andes-money-amount__cents"
        )

        if preco_atual_elem:

            preco_atual = (
                "R$ "
                + preco_atual_elem.get_text(
                    strip=True
                )
            )

            if centavos_atual_elem:

                preco_atual += (
                    ","
                    + centavos_atual_elem.get_text(
                        strip=True
                    )
                )

            else:

                preco_atual += ",00"

        # ----------------------------------------------------
        # PREÇO ANTIGO
        # ----------------------------------------------------

        preco_antigo = ""

        antigo_container = (
            item.find(
                "s",
                class_="andes-money-amount"
            )
            or
            item.find(
                "span",
                class_="andes-money-amount--previous"
            )
            or
            item.find(
                class_=re.compile(
                    "previous"
                )
            )
        )

        if antigo_container:

            frac_antigo = antigo_container.find(
                "span",
                class_="andes-money-amount__fraction"
            )

            cents_antigo = antigo_container.find(
                "span",
                class_="andes-money-amount__cents"
            )

            if frac_antigo:

                preco_antigo = (
                    "R$ "
                    + frac_antigo.get_text(
                        strip=True
                    )
                )

                if cents_antigo:

                    preco_antigo += (
                        ","
                        + cents_antigo.get_text(
                            strip=True
                        )
                    )

                else:

                    preco_antigo += ",00"

        # ----------------------------------------------------
        # CUPOM
        # ----------------------------------------------------

        cupom = ""

        for tag in item.find_all(
            [
                "span",
                "div",
                "p"
            ]
        ):

            texto_tag = tag.get_text(
                " ",
                strip=True
            )

            texto_upper = (
                texto_tag.upper()
            )

            if (
                "CUPOM"
                in texto_upper
                or
                "OFF"
                in texto_upper
            ):

                if (
                    3
                    <= len(texto_tag)
                    <= 60
                ):

                    cupom = texto_tag

                    break

        # ----------------------------------------------------
        # IMAGEM
        # ----------------------------------------------------

        foto_url = ""

        img = item.find(
            "img"
        )

        if img:

            for atributo in [
                "data-src",
                "src",
                "data-lazy-src",
                "data-lazy-icon"
            ]:

                valor = img.get(
                    atributo
                )

                if valor:

                    foto_url = normalizar_url(
                        valor,
                        url_base
                    )

                    if foto_url:

                        break

        # ----------------------------------------------------
        # SALVAR
        # ----------------------------------------------------

        produtos.append({

            "link":
                link_produto,

            "titulo":
                titulo,

            "preco_atual":
                preco_atual,

            "preco_antigo":
                preco_antigo,

            "cupom":
                cupom,

            "imagem":
                foto_url

        })

    # ========================================================
    # SEGUNDA TENTATIVA:
    # LINKS DIRETOS NO HTML
    # ========================================================

    links_diretos = (
        extrair_links_html(
            soup,
            url_base
        )
    )

    # ========================================================
    # TERCEIRA TENTATIVA:
    # REGEX
    # ========================================================

    links_regex = (
        extrair_links_regex(
            texto,
            url_base
        )
    )

    todos_links = (
        links_diretos
        + links_regex
    )

    # ========================================================
    # ADICIONAR LINKS QUE NÃO ESTAVAM NOS CARDS
    # ========================================================

    existentes = set()

    for produto in produtos:

        mlb = extrair_id_mlb(
            produto["link"]
        )

        if mlb:

            existentes.add(
                mlb
            )

        else:

            existentes.add(
                produto["link"]
            )

    for link in todos_links:

        mlb = extrair_id_mlb(
            link
        )

        chave = (
            mlb
            if mlb
            else link
        )

        if chave in existentes:

            continue

        produtos.append({

            "link":
                link,

            "titulo":
                "Oferta Imperdível "
                "no Mercado Livre",

            "preco_atual":
                "",

            "preco_antigo":
                "",

            "cupom":
                "",

            "imagem":
                ""

        })

        existentes.add(
            chave
        )

    # ========================================================
    # DEDUPLICAR
    # ========================================================

    resultado = []

    vistos = set()

    for produto in produtos:

        link = produto.get(
            "link",
            ""
        )

        mlb = extrair_id_mlb(
            link
        )

        chave = (
            mlb
            if mlb
            else link
        )

        if not chave:

            continue

        if chave in vistos:

            continue

        vistos.add(
            chave
        )

        resultado.append(
            produto
        )

    print(
        f"🎯 Produtos encontrados:"
        f" {len(resultado)}"
    )

    return resultado


# ============================================================
# ACESSAR VITRINE
# ============================================================

def acessar_vitrine(
    url_vitrine
):

    print("")
    print(
        "=========================================="
    )

    print(
        "🔎 ACESSANDO VITRINE"
    )

    print(
        "=========================================="
    )

    print(
        f"🔗 {url_vitrine}"
    )

    headers = obter_headers()

    inicio = time.time()

    try:

        resposta = session.get(

            url_vitrine,

            headers=headers,

            allow_redirects=True,

            timeout=HTTP_TIMEOUT

        )

        tempo = (
            time.time()
            - inicio
        )

        print(
            f"⏱️ Resposta em "
            f"{tempo:.2f}s"
        )

        print(
            f"📊 HTTP: "
            f"{resposta.status_code}"
        )

        print(
            f"🔗 URL final: "
            f"{resposta.url}"
        )

        print(
            f"📄 HTML: "
            f"{len(resposta.text)} bytes"
        )

        # ----------------------------------------------------
        # 403
        # ----------------------------------------------------

        if resposta.status_code == 403:

            print("")
            print(
                "⚠️ MERCADO LIVRE RETORNOU 403."
            )

            print(
                "⚠️ O acesso automatizado "
                "foi bloqueado."
            )

            # Mesmo com 403, tentamos extrair
            # alguma informação do HTML.
            produtos = (
                extrair_produtos_da_pagina(
                    resposta.text,
                    resposta.url
                )
            )

            if produtos:

                print(
                    "⚠️ Apesar do 403, "
                    "foram encontrados "
                    "produtos no HTML."
                )

                return (
                    resposta,
                    produtos
                )

            return (
                resposta,
                []
            )

        # ----------------------------------------------------
        # OUTROS ERROS
        # ----------------------------------------------------

        if resposta.status_code >= 400:

            print(
                f"❌ HTTP {resposta.status_code}"
            )

            return (
                resposta,
                []
            )

        # ----------------------------------------------------
        # OK
        # ----------------------------------------------------

        produtos = (
            extrair_produtos_da_pagina(
                resposta.text,
                resposta.url
            )
        )

        return (
            resposta,
            produtos
        )

    except requests.exceptions.Timeout:

        print(
            "❌ Timeout acessando a vitrine."
        )

        return (
            None,
            []
        )

    except requests.exceptions.RequestException as e:

        print(
            f"❌ Erro HTTP: {e}"
        )

        return (
            None,
            []
        )

    except Exception as e:

        print(
            f"❌ Erro inesperado: {e}"
        )

        return (
            None,
            []
        )


# ============================================================
# BUSCAR DADOS INDIVIDUAIS DO PRODUTO
# ============================================================

def completar_dados_produto(
    produto
):

    link = produto.get(
        "link",
        ""
    )

    if not link:

        return produto

    # Se já temos imagem e preço,
    # não precisamos acessar novamente.
    if (
        produto.get("imagem")
        and
        produto.get("preco_atual")
    ):

        return produto

    print(
        f"🔍 Complementando:"
        f" {link}"
    )

    headers = obter_headers()

    try:

        resposta = session.get(

            link,

            headers=headers,

            allow_redirects=True,

            timeout=HTTP_TIMEOUT

        )

        if resposta.status_code >= 400:

            print(
                f"⚠️ Produto retornou "
                f"HTTP {resposta.status_code}"
            )

            return produto

        soup = BeautifulSoup(
            resposta.text,
            "html.parser"
        )

        # ----------------------------------------------------
        # TÍTULO
        # ----------------------------------------------------

        if not produto.get(
            "titulo"
        ):

            og_title = soup.find(
                "meta",
                property="og:title"
            )

            if og_title:

                produto["titulo"] = (
                    og_title.get(
                        "content",
                        ""
                    ).strip()
                )

        # ----------------------------------------------------
        # IMAGEM
        # ----------------------------------------------------

        if not produto.get(
            "imagem"
        ):

            og_image = soup.find(
                "meta",
                property="og:image"
            )

            if og_image:

                produto["imagem"] = (
                    og_image.get(
                        "content",
                        ""
                    ).strip()
                )

        # ----------------------------------------------------
        # PREÇO
        # ----------------------------------------------------

        if not produto.get(
            "preco_atual"
        ):

            preco_elem = soup.find(
                "span",
                class_="andes-money-amount__fraction"
            )

            cents_elem = soup.find(
                "span",
                class_="andes-money-amount__cents"
            )

            if preco_elem:

                preco = (
                    "R$ "
                    + preco_elem.get_text(
                        strip=True
                    )
                )

                if cents_elem:

                    preco += (
                        ","
                        + cents_elem.get_text(
                            strip=True
                        )
                    )

                else:

                    preco += ",00"

                produto[
                    "preco_atual"
                ] = preco

        return produto

    except Exception as e:

        print(
            f"⚠️ Erro complementando produto:"
            f" {e}"
        )

        return produto


# ============================================================
# ENVIAR PARA TELEGRAM
# ============================================================

def enviar_oferta(
    produto
):

    if not TELEGRAM_TOKEN:

        print(
            "❌ TELEGRAM_TOKEN não configurado."
        )

        return False

    link = produto.get(
        "link",
        ""
    )

    titulo = produto.get(
        "titulo",
        "Oferta Imperdível "
        "no Mercado Livre"
    )

    imagem = produto.get(
        "imagem",
        ""
    )

    preco_atual = produto.get(
        "preco_atual",
        ""
    )

    preco_antigo = produto.get(
        "preco_antigo",
        ""
    )

    cupom = produto.get(
        "cupom",
        ""
    )

    # --------------------------------------------------------
    # ESCAPAR HTML
    # --------------------------------------------------------

    titulo = html.escape(
        titulo
    )

    # --------------------------------------------------------
    # PREÇOS
    # --------------------------------------------------------

    atual_float = (
        converter_preco_float(
            preco_atual
        )
    )

    antigo_float = (
        converter_preco_float(
            preco_antigo
        )
    )

    if (
        antigo_float > atual_float
        and
        antigo_float > 0
        and
        atual_float > 0
    ):

        bloco_preco = (

            f"❌ <s>De: "
            f"{html.escape(preco_antigo)}"
            f"</s>\n"

            f"🔥 <b>POR APENAS:</b> "
            f"<code>"
            f"{html.escape(preco_atual)}"
            f"</code>\n"

        )

    elif preco_atual:

        bloco_preco = (

            f"💥 <b>POR APENAS:</b> "
            f"<code>"
            f"{html.escape(preco_atual)}"
            f"</code>\n"

        )

    else:

        bloco_preco = ""

    # --------------------------------------------------------
    # CUPOM
    # --------------------------------------------------------

    bloco_cupom = ""

    if cupom:

        bloco_cupom = (

            f"🎟️ <b>CUPOM EXTRA:</b> "
            f"<i>"
            f"{html.escape(cupom)}"
            f"</i>\n"

        )

    # --------------------------------------------------------
    # LEGENDA
    # --------------------------------------------------------

    legenda = (

        "🚨 <b>OFERTA RELÂMPAGO DO DIA</b> 🚨\n"

        "━━━━━━━━━━━━━━━━━━━━\n\n"

        f"📦 <b>{titulo}</b>\n\n"

        f"{bloco_preco}"

        f"{bloco_cupom}"

        "🚚 <i>Frete Rápido &amp; "
        "Compra 100% Segura</i>\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"

        "👇 <b>GARANTA O SEU ANTES QUE ACABE:</b>\n\n"

        "📌 <i>Canal Oficial "
        "@raposacacadora</i>"

    )

    # ========================================================
    # TELEGRAM API
    # ========================================================

    try:

        # ----------------------------------------------------
        # COM FOTO
        # ----------------------------------------------------

        if (
            imagem
            and
            imagem.startswith(
                "http"
            )
        ):

            api_url = (
                "https://api.telegram.org/"
                f"bot{TELEGRAM_TOKEN}/sendPhoto"
            )

            keyboard = {

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

            payload = {

                "chat_id":
                    CHAT_ID,

                "photo":
                    imagem,

                "caption":
                    legenda,

                "parse_mode":
                    "HTML",

                "reply_markup":
                    json.dumps(
                        keyboard
                    )

            }

        # ----------------------------------------------------
        # SEM FOTO
        # ----------------------------------------------------

        else:

            api_url = (
                "https://api.telegram.org/"
                f"bot{TELEGRAM_TOKEN}/sendMessage"
            )

            keyboard = {

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

            payload = {

                "chat_id":
                    CHAT_ID,

                "text":
                    legenda,

                "parse_mode":
                    "HTML",

                "reply_markup":
                    json.dumps(
                        keyboard
                    )

            }

        resposta = session.post(

            api_url,

            data=payload,

            timeout=HTTP_TIMEOUT

        )

        if resposta.status_code == 200:

            resultado = resposta.json()

            if resultado.get(
                "ok"
            ):

                print(
                    "✅ Oferta enviada "
                    "ao Telegram."
                )

                return True

        print(
            "❌ Erro Telegram:"
        )

        print(
            resposta.text[:2000]
        )

        return False

    except Exception as e:

        print(
            f"❌ Erro enviando Telegram:"
            f" {e}"
        )

        return False


# ============================================================
# PROCESSAR VITRINE
# ============================================================

def processar_e_postar_vitrine(
    url_vitrine,
    quantidade,
    intervalo_minutos
):

    global automacoes_ativas

    with automacoes_lock:

        automacoes_ativas += 1

    try:

        print("")
        print(
            "============================================================"
        )

        print(
            "🦊 RAPOSA CAÇADORA"
        )

        print(
            "============================================================"
        )

        print(
            f"🔗 Vitrine: {url_vitrine}"
        )

        print(
            f"📦 Quantidade: {quantidade}"
        )

        print(
            f"⏱️ Intervalo: "
            f"{intervalo_minutos} minuto(s)"
        )

        # ====================================================
        # ACESSAR VITRINE
        # ====================================================

        resposta, produtos = (
            acessar_vitrine(
                url_vitrine
            )
        )

        # ====================================================
        # NENHUM PRODUTO
        # ====================================================

        if not produtos:

            print("")
            print(
                "❌ NENHUM PRODUTO FOI ENCONTRADO."
            )

            if resposta is not None:

                print(
                    f"📊 HTTP recebido:"
                    f" {resposta.status_code}"
                )

            print(
                "🛑 Automação encerrada."
            )

            return

        # ====================================================
        # HISTÓRICO
        # ====================================================

        historico = (
            carregar_historico()
        )

        print(
            f"📚 Histórico:"
            f" {len(historico)} itens"
        )

        # ====================================================
        # FILTRAR PRODUTOS
        # ====================================================

        produtos_ineditos = []

        for produto in produtos:

            link = produto.get(
                "link",
                ""
            )

            mlb = extrair_id_mlb(
                link
            )

            chave = (
                mlb
                if mlb
                else link
            )

            if not chave:

                continue

            if chave in historico:

                continue

            produtos_ineditos.append(
                produto
            )

        print(
            f"🆕 Produtos inéditos:"
            f" {len(produtos_ineditos)}"
        )

        # ====================================================
        # SE ACABARAM OS PRODUTOS
        # ====================================================

        if not produtos_ineditos:

            print(
                "🔄 Todos os produtos já "
                "foram publicados."
            )

            print(
                "♻️ Resetando histórico."
            )

            limpar_historico()

            produtos_ineditos = produtos

        # ====================================================
        # LIMITAR QUANTIDADE
        # ====================================================

        produtos_para_postar = (
            produtos_ineditos[
                :quantidade
            ]
        )

        print(
            f"📋 Serão processados:"
            f" {len(produtos_para_postar)}"
        )

        publicados = 0

        # ====================================================
        # LOOP
        # ====================================================

        for indice, produto in enumerate(
            produtos_para_postar,
            start=1
        ):

            print("")
            print(
                "--------------------------------------------"
            )

            print(
                f"🛒 Produto "
                f"{indice}/"
                f"{len(produtos_para_postar)}"
            )

            print(
                f"🔗 {produto.get('link')}"
            )

            # ------------------------------------------------
            # COMPLETAR DADOS
            # ------------------------------------------------

            produto = (
                completar_dados_produto(
                    produto
                )
            )

            # ------------------------------------------------
            # ENVIAR
            # ------------------------------------------------

            sucesso = (
                enviar_oferta(
                    produto
                )
            )

            if sucesso:

                link = produto.get(
                    "link",
                    ""
                )

                mlb = extrair_id_mlb(
                    link
                )

                chave = (
                    mlb
                    if mlb
                    else link
                )

                salvar_historico(
                    chave
                )

                publicados += 1

                print(
                    f"✅ Publicado:"
                    f" {produto.get('titulo', '')[:60]}"
                )

                # ------------------------------------------------
                # INTERVALO
                # ------------------------------------------------

                if (
                    indice
                    <
                    len(produtos_para_postar)
                ):

                    segundos = (
                        intervalo_minutos
                        * 60
                    )

                    print(
                        f"⏳ Aguardando "
                        f"{intervalo_minutos} "
                        f"minuto(s)..."
                    )

                    time.sleep(
                        segundos
                    )

            else:

                print(
                    "⚠️ Produto não publicado."
                )

        # ====================================================
        # FINAL
        # ====================================================

        print("")
        print(
            "============================================================"
        )

        print(
            "🏁 AUTOMAÇÃO FINALIZADA"
        )

        print(
            f"📦 Produtos publicados:"
            f" {publicados}"
        )

        print(
            "============================================================"
        )

    except Exception as e:

        print("")
        print(
            f"❌ ERRO NA AUTOMAÇÃO:"
            f" {e}"
        )

    finally:

        with automacoes_lock:

            automacoes_ativas -= 1

        print(
            "🦊 Thread encerrada."
        )


# ============================================================
# API CONFIGURAR
# ============================================================

@app.route(
    "/api/configurar",
    methods=[
        "POST",
        "OPTIONS"
    ]
)
@app.route(
    "/configurar",
    methods=[
        "POST",
        "OPTIONS"
    ]
)
def api_configurar():

    if request.method == "OPTIONS":

        return "", 200

    try:

        dados = (
            request.get_json(
                silent=True
            )
            or {}
        )

        print("")
        print(
            "============================================================"
        )

        print(
            "📥 NOVA CONFIGURAÇÃO"
        )

        print(
            "============================================================"
        )

        # ====================================================
        # LINK
        # ====================================================

        link = str(
            dados.get(
                "link",
                dados.get(
                    "linkCanal",
                    ""
                )
            )
        ).strip()

        # ====================================================
        # INTERVALO
        # ====================================================

        try:

            intervalo_minutos = int(
                dados.get(
                    "intervalo",
                    30
                )
            )

        except Exception:

            intervalo_minutos = 30

        # ====================================================
        # QUANTIDADE
        # ====================================================

        try:

            quantidade = int(
                dados.get(
                    "quantidade",
                    5
                )
            )

        except Exception:

            quantidade = 5

        # ====================================================
        # INIT DATA
        # ====================================================

        init_data = str(
            dados.get(
                "initData",
                ""
            )
        ).strip()

        print(
            f"🔗 Link: {link}"
        )

        print(
            f"📦 Quantidade: {quantidade}"
        )

        print(
            f"⏱️ Intervalo:"
            f" {intervalo_minutos} minuto(s)"
        )

        # ====================================================
        # VALIDAR LINK
        # ====================================================

        if not link:

            return jsonify({

                "erro":
                    "O link da vitrine "
                    "é obrigatório."

            }), 400

        # ====================================================
        # VALIDAR INTERVALO
        # ====================================================

        if (
            intervalo_minutos
            <
            MIN_INTERVALO_MINUTOS
        ):

            intervalo_minutos = (
                MIN_INTERVALO_MINUTOS
            )

        # ====================================================
        # VALIDAR QUANTIDADE
        # ====================================================

        if quantidade < 1:

            quantidade = 1

        if quantidade > MAX_QUANTIDADE:

            quantidade = (
                MAX_QUANTIDADE
            )

        # ====================================================
        # VALIDAR TELEGRAM
        # ====================================================

        if not validar_init_data(
            init_data
        ):

            return jsonify({

                "erro":
                    "Autenticação do Telegram "
                    "inválida ou expirada."

            }), 403

        # ====================================================
        # INICIAR THREAD
        # ====================================================

        thread = threading.Thread(

            target=
                processar_e_postar_vitrine,

            args=(

                link,

                quantidade,

                intervalo_minutos

            ),

            daemon=True

        )

        thread.start()

        print(
            "🚀 Automação iniciada "
            "em segundo plano."
        )

        print(
            "============================================================"
        )

        return jsonify({

            "sucesso":
                True,

            "mensagem":
                "🦊 Automação iniciada "
                "com sucesso!",

            "link":
                link,

            "quantidade":
                quantidade,

            "intervalo_minutos":
                intervalo_minutos

        }), 200

    except Exception as e:

        print(
            f"❌ Erro API:"
            f" {e}"
        )

        return jsonify({

            "erro":
                f"Erro interno: {e}"

        }), 500


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    print("")
    print(
        "============================================================"
    )

    print(
        "🦊 RAPOSA CAÇADORA"
    )

    print(
        "============================================================"
    )

    print(
        f"🌐 Porta: {PORT}"
    )

    print(
        f"🤖 Telegram configurado:"
        f" {bool(TELEGRAM_TOKEN)}"
    )

    print(
        f"📢 Chat configurado:"
        f" {bool(CHAT_ID)}"
    )

    print(
        "============================================================"
    )

    app.run(
        host="0.0.0.0",
        port=PORT
    )
