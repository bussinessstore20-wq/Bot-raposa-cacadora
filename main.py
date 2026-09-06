import os
import re
import json
import time
import html
import threading
import hashlib
import hmac
from urllib.parse import (
    parse_qsl,
    urljoin,
    urlparse,
    unquote,
)

import requests
from bs4 import BeautifulSoup
from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
)


# ============================================================
# RAPOSA CAÇADORA
# main.py - versão completa
# ============================================================


# ============================================================
# CAMINHOS
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
# CONFIGURAÇÕES
# ============================================================

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    ""
).strip()

CHAT_ID = os.getenv(
    "CHAT_ID",
    "@raposacacadora"
).strip()

WEBAPP_URL = os.getenv(
    "WEBAPP_URL",
    ""
).strip()

PORT = int(
    os.getenv(
        "PORT",
        "10000"
    )
)

MAX_QUANTIDADE = 50

MIN_INTERVALO = 10

HTTP_TIMEOUT = 30


# ============================================================
# FLASK
# ============================================================

app = Flask(
    __name__,
    static_folder=BASE_DIR
)


# ============================================================
# ESTADO DAS AUTOMAÇÕES
# ============================================================

automacoes_lock = threading.Lock()

automacoes_ativas = 0


# ============================================================
# SESSION HTTP
# ============================================================

session = requests.Session()


# ============================================================
# HEADERS
# ============================================================

def obter_headers():

    return {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/152.0.0.0 "
            "Safari/537.36"
        ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",

        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "image/avif,"
            "image/webp,"
            "image/apng,"
            "*/*;q=0.8"
        ),

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache",

        "Connection":
            "keep-alive",
    }


# ============================================================
# PÁGINA INICIAL
# ============================================================

@app.route("/", methods=["GET"])
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

            * {
                box-sizing: border-box;
            }

            body {
                margin: 0;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                background:
                    radial-gradient(
                        circle at top,
                        #1f2937,
                        #05070a 60%
                    );
                color: white;
                font-family: Arial, sans-serif;
                padding: 20px;
            }

            .box {
                width: 100%;
                max-width: 520px;
                padding: 35px;
                text-align: center;
                background: #111827;
                border: 1px solid #263244;
                border-radius: 20px;
                box-shadow:
                    0 20px 60px rgba(0,0,0,.5);
            }

            h1 {
                margin-top: 0;
                color: #f97316;
            }

            p {
                color: #cbd5e1;
                line-height: 1.6;
            }

            a {
                color: #fb923c;
                text-decoration: none;
                font-weight: bold;
            }

            a:hover {
                text-decoration: underline;
            }

            .online {
                display: inline-block;
                margin: 10px 0 20px;
                padding: 8px 14px;
                border-radius: 999px;
                background: #064e3b;
                color: #6ee7b7;
                font-weight: bold;
            }

        </style>

    </head>

    <body>

        <div class="box">

            <h1>🦊 Raposa Caçadora</h1>

            <div class="online">
                ● SERVIDOR ONLINE
            </div>

            <p>
                Sistema de automação de ofertas.
            </p>

            <p>
                Mini App:
                <a href="/app">
                    abrir painel
                </a>
            </p>

            <p>
                API:
                <a href="/health">
                    verificar saúde
                </a>
            </p>

        </div>

    </body>

    </html>
    """


# ============================================================
# MINI APP
# ============================================================

@app.route("/app", methods=["GET"])
def mini_app():

    print(
        f"📂 Procurando index.html em: {INDEX_FILE}"
    )

    if not os.path.isfile(INDEX_FILE):

        print(
            "❌ index.html NÃO encontrado."
        )

        try:

            print(
                f"📁 BASE_DIR: {BASE_DIR}"
            )

            print(
                "📄 Arquivos encontrados:"
            )

            for arquivo in os.listdir(BASE_DIR):

                print(
                    f"   - {arquivo}"
                )

        except Exception as erro:

            print(
                f"⚠️ Erro listando arquivos: {erro}"
            )

        return (
            """
            <!DOCTYPE html>
            <html lang="pt-BR">

            <head>
                <meta charset="UTF-8">
                <title>Erro</title>
            </head>

            <body>

                <h2>❌ Mini App não encontrado</h2>

                <p>
                    O arquivo index.html não está
                    na mesma pasta do main.py.
                </p>

            </body>

            </html>
            """,
            404
        )

    print(
        "✅ index.html encontrado."
    )

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health", methods=["GET"])
def health():

    with automacoes_lock:

        ativas = automacoes_ativas

    return jsonify({
        "ok": True,
        "servico": "Raposa Caçadora",
        "status": "online",
        "telegram_configurado":
            bool(TELEGRAM_TOKEN),
        "chat_configurado":
            bool(CHAT_ID),
        "mini_app":
            os.path.isfile(INDEX_FILE),
        "automacoes_ativas":
            ativas,
        "rotas": [
            "/",
            "/app",
            "/health",
            "/api/configurar",
            "/configurar",
        ],
    })


# ============================================================
# CONFIGURAÇÃO
# ============================================================

def verificar_configuracao():

    if not TELEGRAM_TOKEN:

        print(
            "❌ TELEGRAM_TOKEN não configurado."
        )

        return False

    if not CHAT_ID:

        print(
            "❌ CHAT_ID não configurado."
        )

        return False

    return True


# ============================================================
# VALIDAR INIT DATA TELEGRAM
# ============================================================

def validar_init_data(init_data):

    if not init_data:
        return False

    if not TELEGRAM_TOKEN:
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
            in sorted(dados.items())
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

        return hmac.compare_digest(
            calculado,
            hash_recebido
        )

    except Exception as erro:

        print(
            f"⚠️ Erro ao validar initData: {erro}"
        )

        return False


# ============================================================
# HISTÓRICO
# ============================================================

historico_lock = threading.Lock()


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

    except Exception as erro:

        print(
            f"⚠️ Erro ao carregar histórico: {erro}"
        )

        return set()


def salvar_historico(link):

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
                    link.strip() + "\n"
                )

        return True

    except Exception as erro:

        print(
            f"⚠️ Erro ao salvar histórico: {erro}"
        )

        return False


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_api(
    metodo,
    dados=None
):

    if not TELEGRAM_TOKEN:

        print(
            "❌ TELEGRAM_TOKEN não configurado."
        )

        return None

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/"
        f"{metodo}"
    )

    try:

        resposta = session.post(
            url,
            data=dados or {},
            timeout=HTTP_TIMEOUT
        )

        print(
            f"📡 Telegram HTTP: "
            f"{resposta.status_code}"
        )

        try:

            resultado = resposta.json()

        except Exception:

            print(
                "❌ Telegram retornou resposta "
                "que não é JSON."
            )

            print(
                resposta.text[:1000]
            )

            return None

        if not resultado.get("ok"):

            print(
                "❌ Telegram retornou erro:"
            )

            print(
                resultado
            )

        return resultado

    except requests.RequestException as erro:

        print(
            f"❌ Erro de conexão Telegram "
            f"({metodo}): {erro}"
        )

        return None

    except Exception as erro:

        print(
            f"❌ Erro Telegram "
            f"({metodo}): {erro}"
        )

        return None


# ============================================================
# ENVIAR MENSAGEM
# ============================================================

def enviar_mensagem(texto):

    resultado = telegram_api(
        "sendMessage",
        {
            "chat_id": CHAT_ID,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
    )

    sucesso = bool(
        resultado
        and resultado.get("ok")
    )

    print(
        f"📨 Aviso enviado: {sucesso}"
    )

    return sucesso


# ============================================================
# LIMPAR URL
# ============================================================

def limpar_url(url):

    if not url:
        return ""

    try:

        url = str(url).strip()

        url = html.unescape(
            url
        )

        url = url.replace(
            "\\/",
            "/"
        )

        url = url.replace(
            "\\u0026",
            "&"
        )

        url = url.replace(
            "&amp;",
            "&"
        )

        url = url.strip(
            "\"'<> \t\r\n"
        )

        return url

    except Exception:

        return ""


# ============================================================
# VALIDAR URL HTTP
# ============================================================

def url_http_valida(url):

    try:

        url = limpar_url(url)

        if not url:
            return False

        parsed = urlparse(
            url
        )

        return (
            parsed.scheme.lower()
            in ("http", "https")
            and bool(parsed.netloc)
        )

    except Exception:

        return False


# ============================================================
# EXPANDIR LINK
# ============================================================

def expandir_link(
    url,
    headers
):

    url = limpar_url(
        url
    )

    if not url_http_valida(
        url
    ):

        print(
            f"❌ URL inválida: {url}"
        )

        return None

    print(
        f"🔗 Expandindo: {url}"
    )

    try:

        resposta = session.get(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=HTTP_TIMEOUT
        )

        resposta.raise_for_status()

        final = limpar_url(
            resposta.url
        )

        print(
            f"🔗 URL final: {final}"
        )

        return final

    except requests.RequestException as erro:

        print(
            f"❌ Erro ao expandir URL: {erro}"
        )

        return None

    except Exception as erro:

        print(
            f"❌ Erro inesperado expandindo URL: "
            f"{erro}"
        )

        return None


# ============================================================
# IDENTIFICAR URL DE PRODUTO
# ============================================================

def parece_produto_mercadolivre(url):

    if not url:
        return False

    texto = url.lower()

    padroes = [
        "produto.mercadolivre.com.br",
        "mercadolivre.com.br/p/",
        "mercadolivre.com.br/up/",
        "/p/mlb",
        "mlb-",
        "item.mercadolivre.com.br",
    ]

    return any(
        padrao in texto
        for padrao in padroes
    )


# ============================================================
# NORMALIZAR LINK DE PRODUTO
# ============================================================

def normalizar_link_produto(
    url,
    base_url
):

    try:

        url = limpar_url(
            url
        )

        if not url:
            return ""

        # ----------------------------------------------------
        # Alguns links vêm codificados
        # ----------------------------------------------------

        if "%" in url:

            try:

                url_decodificada = unquote(
                    url
                )

                if url_decodificada != url:

                    url = url_decodificada

            except Exception:

                pass

        # ----------------------------------------------------
        # Corrigir links relativos
        # ----------------------------------------------------

        if url.startswith("//"):

            url = "https:" + url

        elif url.startswith("/"):

            url = urljoin(
                base_url,
                url
            )

        elif not url_http_valida(
            url
        ):

            return ""

        # ----------------------------------------------------
        # VALIDAÇÃO
        # ----------------------------------------------------

        if not url_http_valida(
            url
        ):

            return ""

        parsed = urlparse(
            url
        )

        # ----------------------------------------------------
        # Segurança contra URL inválida
        # ----------------------------------------------------

        if not parsed.hostname:

            return ""

        # ----------------------------------------------------
        # Só aceitar Mercado Livre
        # ----------------------------------------------------

        hostname = (
            parsed.hostname.lower()
        )

        dominios_validos = [
            "mercadolivre.com.br",
            "www.mercadolivre.com.br",
            "produto.mercadolivre.com.br",
            "item.mercadolivre.com.br",
            "meli.la",
        ]

        valido = (
            hostname in dominios_validos
            or hostname.endswith(
                ".mercadolivre.com.br"
            )
        )

        if not valido:

            return ""

        # ----------------------------------------------------
        # Remover fragmento
        # ----------------------------------------------------

        url = url.split(
            "#"
        )[0]

        return url

    except ValueError as erro:

        print(
            f"⚠️ URL ignorada por erro de parsing: "
            f"{url} | {erro}"
        )

        return ""

    except Exception as erro:

        print(
            f"⚠️ Erro normalizando URL: "
            f"{erro}"
        )

        return ""


# ============================================================
# ADICIONAR LINK
# ============================================================

def adicionar_link(
    links,
    encontrado,
    base_url
):

    try:

        encontrado = limpar_url(
            encontrado
        )

        if not encontrado:
            return

        # ----------------------------------------------------
        # Links que possuem escapes
        # ----------------------------------------------------

        encontrado = encontrado.replace(
            "\\/",
            "/"
        )

        # ----------------------------------------------------
        # Normalização
        # ----------------------------------------------------

        normalizado = normalizar_link_produto(
            encontrado,
            base_url
        )

        if not normalizado:

            return

        if not parece_produto_mercadolivre(
            normalizado
        ):

            return

        if normalizado not in links:

            links.append(
                normalizado
            )

    except Exception as erro:

        print(
            f"⚠️ Erro adicionando link: "
            f"{erro}"
        )


# ============================================================
# EXTRAIR URLS DO HTML
# ============================================================

def extrair_urls_do_html(
    texto,
    base_url
):

    links = []

    # ========================================================
    # 1. HREF
    # ========================================================

    try:

        soup = BeautifulSoup(
            texto,
            "html.parser"
        )

        for a in soup.find_all(
            "a",
            href=True
        ):

            href = a.get(
                "href",
                ""
            )

            adicionar_link(
                links,
                href,
                base_url
            )

    except Exception as erro:

        print(
            f"⚠️ Erro lendo tags <a>: {erro}"
        )

    # ========================================================
    # 2. ATTRIBUTES
    # ========================================================

    try:

        soup = BeautifulSoup(
            texto,
            "html.parser"
        )

        for elemento in soup.find_all():

            for valor in elemento.attrs.values():

                valores = valor

                if not isinstance(
                    valores,
                    list
                ):

                    valores = [
                        valores
                    ]

                for valor_individual in valores:

                    if not isinstance(
                        valor_individual,
                        str
                    ):

                        continue

                    # URLs absolutas
                    encontrados = re.findall(
                        r'https?://[^"\'<>\s]+',
                        valor_individual
                    )

                    for encontrado in encontrados:

                        adicionar_link(
                            links,
                            encontrado,
                            base_url
                        )

    except Exception as erro:

        print(
            f"⚠️ Erro lendo atributos: {erro}"
        )

    # ========================================================
    # 3. TEXTO BRUTO
    # ========================================================

    try:

        padrao = re.compile(
            r'https?://'
            r'(?:www\.)?'
            r'(?:mercadolivre|produto|item)'
            r'\.com\.br'
            r'[^"\'<>\s]+',
            re.IGNORECASE
        )

        for encontrado in padrao.findall(
            texto
        ):

            adicionar_link(
                links,
                encontrado,
                base_url
            )

    except Exception as erro:

        print(
            f"⚠️ Erro procurando URLs no texto: "
            f"{erro}"
        )

    # ========================================================
    # 4. PADRÕES MLB
    # ========================================================

    try:

        padroes = [
            r'https?://[^\s"\']*MLB-\d+[^\s"\']*',
            r'https?://[^\s"\']*/p/MLB[^\s"\']*',
            r'https?://[^\s"\']*/p/mlb[^\s"\']*',
        ]

        for padrao in padroes:

            encontrados = re.findall(
                padrao,
                texto,
                re.IGNORECASE
            )

            for encontrado in encontrados:

                adicionar_link(
                    links,
                    encontrado,
                    base_url
                )

    except Exception as erro:

        print(
            f"⚠️ Erro procurando MLB: {erro}"
        )

    return links


# ============================================================
# ENCONTRAR LINKS DE PRODUTOS
# ============================================================

def encontrar_links_produtos(
    url_vitrine,
    headers
):

    print(
        f"🔎 Acessando vitrine: "
        f"{url_vitrine}"
    )

    try:

        resposta = session.get(
            url_vitrine,
            headers=headers,
            timeout=HTTP_TIMEOUT,
            allow_redirects=True
        )

        resposta.raise_for_status()

    except requests.RequestException as erro:

        print(
            f"❌ Erro ao acessar vitrine: "
            f"{erro}"
        )

        return []

    except Exception as erro:

        print(
            f"❌ Erro inesperado acessando vitrine: "
            f"{erro}"
        )

        return []

    texto = resposta.text or ""

    print(
        f"📄 Página recebida: "
        f"{len(texto)} bytes"
    )

    url_base = limpar_url(
        resposta.url
    )

    # ========================================================
    # IMPORTANTE:
    # Nunca usar diretamente resposta.url em urljoin
    # sem antes validar/tratar.
    # ========================================================

    if not url_http_valida(
        url_base
    ):

        print(
            "⚠️ URL base inválida."
        )

        url_base = url_vitrine

    links = []

    # ========================================================
    # EXTRAÇÃO HTML/JSON/TEXTO
    # ========================================================

    links = extrair_urls_do_html(
        texto,
        url_base
    )

    print(
        f"🔗 Links de produtos encontrados: "
        f"{len(links)}"
    )

    # ========================================================
    # SEGUNDA PASSAGEM:
    # procurar objetos JSON embutidos
    # ========================================================

    try:

        padroes_json_url = [
            r'"url"\s*:\s*"([^"]+)"',
            r'"href"\s*:\s*"([^"]+)"',
            r'"permalink"\s*:\s*"([^"]+)"',
            r'"item_url"\s*:\s*"([^"]+)"',
            r'"link"\s*:\s*"([^"]+)"',
        ]

        for padrao in padroes_json_url:

            encontrados = re.findall(
                padrao,
                texto,
                re.IGNORECASE
            )

            for encontrado in encontrados:

                adicionar_link(
                    links,
                    encontrado,
                    url_base
                )

    except Exception as erro:

        print(
            f"⚠️ Erro procurando JSON: {erro}"
        )

    # ========================================================
    # TERCEIRA PASSAGEM:
    # procurar IDs MLB
    # ========================================================

    try:

        ids = re.findall(
            r'\bMLB[-_]\d{5,}\b',
            texto,
            re.IGNORECASE
        )

        ids_unicos = []

        for item_id in ids:

            item_id = item_id.upper()

            if item_id not in ids_unicos:

                ids_unicos.append(
                    item_id
                )

        for item_id in ids_unicos:

            numero = re.sub(
                r'[^0-9]',
                "",
                item_id
            )

            if not numero:

                continue

            possiveis = [
                f"https://produto.mercadolivre.com.br/MLB-{numero}",
                f"https://www.mercadolivre.com.br/p/MLB{numero}",
            ]

            for possivel in possiveis:

                adicionar_link(
                    links,
                    possivel,
                    url_base
                )

    except Exception as erro:

        print(
            f"⚠️ Erro procurando IDs: {erro}"
        )

    # ========================================================
    # LIMITAR DUPLICADOS
    # ========================================================

    links = list(
        dict.fromkeys(
            links
        )
    )

    print(
        f"📦 {len(links)} produtos encontrados."
    )

    return links


# ============================================================
# EXTRAIR PRODUTO
# ============================================================

def extrair_produto(
    link,
    headers
):

    print(
        f"🔎 Extraindo produto: {link}"
    )

    try:

        resposta = session.get(
            link,
            headers=headers,
            allow_redirects=True,
            timeout=HTTP_TIMEOUT
        )

        resposta.raise_for_status()

    except requests.RequestException as erro:

        print(
            f"⚠️ Erro acessando produto: "
            f"{erro}"
        )

        return None

    except Exception as erro:

        print(
            f"⚠️ Erro inesperado acessando produto: "
            f"{erro}"
        )

        return None

    soup = BeautifulSoup(
        resposta.text,
        "html.parser"
    )

    # ========================================================
    # TÍTULO
    # ========================================================

    titulo = ""

    elemento = soup.find(
        "h1",
        class_="ui-pdp-title"
    )

    if elemento:

        titulo = elemento.get_text(
            " ",
            strip=True
        )

    if not titulo:

        elemento = soup.find(
            "h1"
        )

        if elemento:

            titulo = elemento.get_text(
                " ",
                strip=True
            )

    if not titulo:

        og_title = soup.find(
            "meta",
            property="og:title"
        )

        if og_title:

            titulo = og_title.get(
                "content",
                ""
            ).strip()

    if not titulo:

        meta_title = soup.find(
            "meta",
            attrs={
                "name": "title"
            }
        )

        if meta_title:

            titulo = meta_title.get(
                "content",
                ""
            ).strip()

    if not titulo:

        titulo = (
            "Oferta Imperdível Mercado Livre!"
        )

    # ========================================================
    # IMAGEM
    # ========================================================

    foto_url = ""

    og_image = soup.find(
        "meta",
        property="og:image"
    )

    if og_image:

        foto_url = og_image.get(
            "content",
            ""
        ).strip()

    # ========================================================
    # OUTRAS METAS
    # ========================================================

    if not foto_url:

        meta_image = soup.find(
            "meta",
            attrs={
                "name": "twitter:image"
            }
        )

        if meta_image:

            foto_url = meta_image.get(
                "content",
                ""
            ).strip()

    # ========================================================
    # IMG
    # ========================================================

    if not foto_url:

        elemento_img = soup.find(
            "img",
            class_="ui-pdp-image"
        )

        if elemento_img:

            foto_url = (
                elemento_img.get("src")
                or elemento_img.get("data-src")
                or ""
            )

    # ========================================================
    # QUALQUER IMG ABSOLUTA
    # ========================================================

    if not foto_url:

        for img in soup.find_all(
            "img"
        ):

            candidato = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy")
                or ""
            )

            candidato = limpar_url(
                candidato
            )

            if candidato.startswith(
                "http"
            ):

                foto_url = candidato

                break

    # ========================================================
    # VERIFICAR
    # ========================================================

    if not foto_url:

        print(
            "⚠️ Produto sem imagem."
        )

        return None

    if not url_http_valida(
        foto_url
    ):

        print(
            f"⚠️ Imagem inválida: "
            f"{foto_url}"
        )

        return None

    titulo = html.escape(
        titulo,
        quote=False
    )

    return {
        "titulo": titulo,
        "foto_url": foto_url,
        "link": resposta.url or link,
    }


# ============================================================
# ENVIAR OFERTA
# ============================================================

def enviar_oferta(
    foto_url,
    legenda,
    link_afiliado
):

    if not url_http_valida(
        foto_url
    ):

        print(
            "❌ URL da foto inválida."
        )

        return False

    if not url_http_valida(
        link_afiliado
    ):

        print(
            "❌ URL do botão inválida."
        )

        return False

    teclado = {
        "inline_keyboard": [
            [
                {
                    "text":
                        "🛒 COMPRAR NO MERCADO LIVRE",
                    "url":
                        link_afiliado,
                }
            ]
        ]
    }

    dados = {
        "chat_id":
            CHAT_ID,

        "photo":
            foto_url,

        "caption":
            legenda,

        "parse_mode":
            "HTML",

        "reply_markup":
            json.dumps(
                teclado,
                ensure_ascii=False
            ),
    }

    resultado = telegram_api(
        "sendPhoto",
        dados
    )

    sucesso = bool(
        resultado
        and resultado.get("ok")
    )

    if sucesso:

        print(
            "✅ Oferta enviada ao Telegram."
        )

    else:

        print(
            "❌ Falha enviando oferta."
        )

    return sucesso


# ============================================================
# PROCESSAR AUTOMAÇÃO
# ============================================================

def processar_e_postar_vitrine(
    url_vitrine,
    quantidade_maxima,
    intervalo_seg
):

    global automacoes_ativas

    with automacoes_lock:

        automacoes_ativas += 1

    try:

        headers = obter_headers()

        print(
            "\n" + "=" * 60
        )

        print(
            "🦊 NOVA TAREFA"
        )

        print(
            "=" * 60
        )

        print(
            f"🔗 Vitrine: {url_vitrine}"
        )

        print(
            f"📦 Quantidade: "
            f"{quantidade_maxima}"
        )

        print(
            f"⏱️ Intervalo: "
            f"{intervalo_seg}s"
        )

        print(
            "=" * 60
        )

        # ====================================================
        # EXPANDIR
        # ====================================================

        url_final = expandir_link(
            url_vitrine,
            headers
        )

        if not url_final:

            enviar_mensagem(
                "❌ <b>Não foi possível acessar "
                "a vitrine.</b>"
            )

            return

        # ====================================================
        # IDENTIFICAR PRODUTO OU VITRINE
        # ====================================================

        if parece_produto_mercadolivre(
            url_final
        ):

            print(
                "🛒 Link identificado como produto."
            )

            links_produtos = [
                url_final
            ]

        else:

            print(
                "🏪 Link identificado como "
                "vitrine/lista."
            )

            links_produtos = (
                encontrar_links_produtos(
                    url_final,
                    headers
                )
            )

        # ====================================================
        # NENHUM PRODUTO
        # ====================================================

        if not links_produtos:

            print(
                "⚠️ Nenhum produto encontrado."
            )

            enviar_mensagem(
                "⚠️ <b>Nenhum produto encontrado.</b>\n\n"
                "A página da vitrine foi acessada, "
                "mas não foram encontradas URLs "
                "de produtos.\n\n"
                "O Mercado Livre pode estar entregando "
                "parte do conteúdo de forma dinâmica."
            )

            return

        # ====================================================
        # HISTÓRICO
        # ====================================================

        historico = carregar_historico()

        postados = 0

        # ====================================================
        # LOOP
        # ====================================================

        for link in links_produtos:

            if postados >= quantidade_maxima:

                break

            link = limpar_url(
                link
            )

            if not link:

                continue

            if link in historico:

                print(
                    f"⏭️ Já postado: {link}"
                )

                continue

            print(
                "\n" + "-" * 60
            )

            print(
                f"📦 Processando "
                f"{postados + 1}/"
                f"{quantidade_maxima}"
            )

            print(
                f"🔗 {link}"
            )

            produto = extrair_produto(
                link,
                headers
            )

            if not produto:

                print(
                    "⚠️ Não foi possível extrair "
                    "este produto."
                )

                continue

            titulo = produto[
                "titulo"
            ]

            foto_url = produto[
                "foto_url"
            ]

            link_produto = produto[
                "link"
            ] or link

            legenda = (
                f"🔥 <b>{titulo}</b>\n\n"
                f"⚡ <i>Aproveite esta promoção "
                f"por tempo limitado!</i>\n\n"
                f"👉 <b>Clique abaixo para "
                f"ver a oferta:</b>"
            )

            sucesso = enviar_oferta(
                foto_url,
                legenda,
                link_produto
            )

            if sucesso:

                salvar_historico(
                    link
                )

                historico.add(
                    link
                )

                postados += 1

                print(
                    f"✅ POSTADO "
                    f"{postados}/"
                    f"{quantidade_maxima}"
                )

                if (
                    postados
                    < quantidade_maxima
                ):

                    print(
                        f"⏳ Aguardando "
                        f"{intervalo_seg}s..."
                    )

                    time.sleep(
                        intervalo_seg
                    )

            else:

                print(
                    "❌ Falha ao publicar."
                )

        # ====================================================
        # FINAL
        # ====================================================

        print(
            "\n" + "=" * 60
        )

        print(
            f"🎯 FINALIZADO: "
            f"{postados} ofertas."
        )

        print(
            "=" * 60
        )

        enviar_mensagem(
            "✅ <b>Postagens finalizadas!</b>\n\n"
            f"🦊 Ofertas publicadas: "
            f"<b>{postados}</b>"
        )

    except Exception as erro:

        print(
            "\n" + "=" * 60
        )

        print(
            "❌ ERRO NA AUTOMAÇÃO"
        )

        print(
            f"{type(erro).__name__}: {erro}"
        )

        print(
            "=" * 60
        )

        try:

            enviar_mensagem(
                "❌ <b>A automação encontrou "
                "um erro.</b>\n\n"
                f"<code>{html.escape(str(erro))}</code>"
            )

        except Exception:

            pass

    finally:

        with automacoes_lock:

            automacoes_ativas = max(
                0,
                automacoes_ativas - 1
            )


# ============================================================
# EXECUTAR AUTOMAÇÃO EM THREAD
# ============================================================

def iniciar_automacao(
    link,
    quantidade,
    intervalo
):

    thread = threading.Thread(
        target=processar_e_postar_vitrine,
        args=(
            link,
            quantidade,
            intervalo,
        ),
        daemon=True,
    )

    thread.start()

    print(
        "✅ Thread da automação iniciada."
    )

    return thread


# ============================================================
# POST /api/configurar
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    print(
        "\n" + "=" * 60
    )

    print(
        "📩 NOVA REQUISIÇÃO"
    )

    print(
        f"🌐 Método: {request.method}"
    )

    print(
        f"📍 Rota: {request.path}"
    )

    print(
        "=" * 60
    )

    if not verificar_configuracao():

        return jsonify({
            "ok": False,
            "erro":
                "Bot não configurado."
        }), 500

    dados = request.get_json(
        silent=True
    )

    if not isinstance(
        dados,
        dict
    ):

        print(
            "❌ JSON inválido."
        )

        return jsonify({
            "ok": False,
            "erro":
                "Dados inválidos. "
                "Envie JSON."
        }), 400

    link = str(
        dados.get(
            "link",
            ""
        )
    ).strip()

    init_data = str(
        dados.get(
            "initData",
            ""
        )
    ).strip()

    # ========================================================
    # INTERVALO
    # ========================================================

    try:

        intervalo = int(
            dados.get(
                "intervalo",
                300
            )
        )

    except Exception:

        intervalo = 300

    # ========================================================
    # QUANTIDADE
    # ========================================================

    try:

        quantidade = int(
            dados.get(
                "quantidade",
                5
            )
        )

    except Exception:

        quantidade = 5

    # ========================================================
    # INIT DATA
    # ========================================================

    # Permitir também chamadas internas quando
    # TELEGRAM_INITDATA_REQUIRED estiver explicitamente
    # desativado.
    exigir_init_data = (
        os.getenv(
            "EXIGIR_INIT_DATA",
            "true"
        ).lower()
        not in (
            "false",
            "0",
            "no",
        )
    )

    if exigir_init_data:

        if not validar_init_data(
            init_data
        ):

            print(
                "🚫 initData inválido."
            )

            return jsonify({
                "ok": False,
                "erro":
                    "Autenticação do Telegram inválida."
            }), 403

    # ========================================================
    # LINK
    # ========================================================

    if not link:

        return jsonify({
            "ok": False,
            "erro":
                "Informe o link da vitrine."
        }), 400

    if not url_http_valida(
        link
    ):

        return jsonify({
            "ok": False,
            "erro":
                "O link informado não é uma URL válida."
        }), 400

    # ========================================================
    # INTERVALO
    # ========================================================

    intervalo = max(
        intervalo,
        MIN_INTERVALO
    )

    # ========================================================
    # QUANTIDADE
    # ========================================================

    quantidade = max(
        1,
        min(
            quantidade,
            MAX_QUANTIDADE
        )
    )

    print(
        "\n" + "=" * 60
    )

    print(
        "🚀 ORDEM RECEBIDA"
    )

    print(
        "=" * 60
    )

    print(
        f"🔗 Link: {link}"
    )

    print(
        f"⏱️ Intervalo: "
        f"{intervalo}s"
    )

    print(
        f"📦 Quantidade: "
        f"{quantidade}"
    )

    print(
        "=" * 60
    )

    # ========================================================
    # AVISO TELEGRAM
    # ========================================================

    aviso = enviar_mensagem(
        "🚀 <b>Nova automação iniciada!</b>\n\n"
        f"📦 Quantidade: <b>{quantidade}</b>\n"
        f"⏱️ Intervalo: <b>{intervalo}s</b>\n\n"
        f"🔗 <code>{html.escape(link)}</code>"
    )

    print(
        f"📨 Aviso enviado: {aviso}"
    )

    # ========================================================
    # THREAD
    # ========================================================

    iniciar_automacao(
        link,
        quantidade,
        intervalo
    )

    return jsonify({
        "ok": True,
        "mensagem":
            "Postagens iniciadas.",
        "quantidade":
            quantidade,
        "intervalo":
            intervalo,
    }), 200


# ============================================================
# GET /api/configurar
# ============================================================

# Esta rota NÃO inicia automação.
# Serve apenas para evitar mensagens confusas de 405/404.

@app.route(
    "/api/configurar",
    methods=["GET"]
)
def configurar_get():

    return jsonify({
        "ok": False,
        "erro":
            "A rota /api/configurar "
            "não aceita o método GET.",
        "metodo_correto":
            "POST",
        "rota":
            "/api/configurar",
    }), 405


# ============================================================
# /configurar
# ============================================================

# Mantemos essa rota somente para compatibilidade.
# O Mini App deve usar /api/configurar.

@app.route(
    "/configurar",
    methods=["GET"]
)
def configurar_info():

    return jsonify({
        "ok": False,
        "erro":
            "A rota /configurar existe. "
            "Para iniciar uma automação use POST.",
        "metodo":
            "POST",
        "rota_recomendada":
            "/api/configurar",
        "servico":
            "Raposa Caçadora",
    }), 200


@app.route(
    "/configurar",
    methods=["POST"]
)
def configurar_compatibilidade():

    return configurar()


# ============================================================
# TRATAMENTO 404
# ============================================================

@app.errorhandler(404)
def erro_404(error):

    return jsonify({
        "ok": False,
        "erro":
            "Rota não encontrada.",
        "detalhe":
            f"{request.method} "
            f"{request.path}",
        "rotas_disponiveis": [
            "/",
            "/app",
            "/health",
            "/api/configurar",
            "/configurar",
        ],
    }), 404


# ============================================================
# TRATAMENTO 405
# ============================================================

@app.errorhandler(405)
def erro_405(error):

    return jsonify({
        "ok": False,
        "erro":
            "Método não permitido.",
        "detalhe":
            f"{request.method} "
            f"{request.path}",
        "metodo":
            request.method,
    }), 405


# ============================================================
# TRATAMENTO 500
# ============================================================

@app.errorhandler(500)
def erro_500(error):

    return jsonify({
        "ok": False,
        "erro":
            "Erro interno no servidor.",
        "detalhe":
            str(error),
    }), 500


# ============================================================
# INFORMAÇÕES DE INICIALIZAÇÃO
# ============================================================

def imprimir_status():

    print(
        "\n" + "=" * 60
    )

    print(
        "🦊 RAPOSA CAÇADORA"
    )

    print(
        "=" * 60
    )

    print(
        f"📁 Pasta: {BASE_DIR}"
    )

    print(
        "📄 index.html: "
        +
        (
            "ENCONTRADO"
            if os.path.isfile(INDEX_FILE)
            else "NÃO ENCONTRADO"
        )
    )

    print(
        "🤖 TELEGRAM_TOKEN: "
        +
        (
            "CONFIGURADO"
            if TELEGRAM_TOKEN
            else "NÃO CONFIGURADO"
        )
    )

    print(
        f"💬 CHAT_ID: {CHAT_ID}"
    )

    print(
        f"🌐 PORT: {PORT}"
    )

    print(
        f"🔐 EXIGIR_INIT_DATA: "
        f"{os.getenv('EXIGIR_INIT_DATA', 'true')}"
    )

    if WEBAPP_URL:

        print(
            f"📱 Mini App: "
            f"{WEBAPP_URL.rstrip('/')}/app"
        )

    else:

        print(
            "⚠️ WEBAPP_URL não configurada."
        )

    print(
        "=" * 60
    )

    print(
        "🌐 Rotas:"
    )

    print(
        "   GET  /"
    )

    print(
        "   GET  /app"
    )

    print(
        "   GET  /health"
    )

    print(
        "   POST /api/configurar"
    )

    print(
        "   GET  /api/configurar"
    )

    print(
        "   GET  /configurar"
    )

    print(
        "   POST /configurar"
    )

    print(
        "=" * 60
    )


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    imprimir_status()

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        threaded=True
    )
