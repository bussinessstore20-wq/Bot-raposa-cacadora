import os
import re
import json
import time
import threading
import hashlib
import hmac
from urllib.parse import parse_qsl, urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS


# ============================================================
# RAPOSA CAÇADORA
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
# CONTROLES
# ============================================================

automacoes_lock = threading.Lock()

automacoes_ativas = 0

historico_lock = threading.Lock()

session = requests.Session()


# ============================================================
# HEADERS
# ============================================================

def obter_headers():

    return {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Linux; Android 15) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0.0.0 "
            "Mobile Safari/537.36"
        ),

        "Accept-Language": (
            "pt-BR,pt;q=0.9,"
            "en-US;q=0.8,en;q=0.7"
        ),

        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "image/avif,image/webp,"
            "*/*;q=0.8"
        ),

        "Cache-Control": "no-cache",

        "Pragma": "no-cache",

        "Connection": "keep-alive"
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

        <title>
            Raposa Caçadora
        </title>

        <style>

            body {
                background:#05070a;
                color:white;
                font-family:Arial,sans-serif;
                text-align:center;
                padding-top:50px;
            }

            h1 {
                color:#f97316;
            }

            a {
                color:#fb923c;
                text-decoration:none;
                font-weight:bold;
            }

            .online {
                color:#22c55e;
            }

        </style>

    </head>

    <body>

        <h1>
            🦊 Raposa Caçadora VIP
        </h1>

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

        "ok": True,

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
# TELEGRAM WEB APP
# ============================================================

def validar_init_data(
    init_data
):

    if not init_data:

        print(
            "⚠️ initData não informado."
        )

        return False

    if not TELEGRAM_TOKEN:

        print(
            "⚠️ TELEGRAM_TOKEN não configurado."
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
                "⚠️ Hash não encontrado."
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

        if not valido:

            print(
                "⚠️ initData inválido."
            )

        return valido

    except Exception as e:

        print(
            f"⚠️ Erro Telegram: {e}"
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
            f"⚠️ Erro histórico: {e}"
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
            f"⚠️ Erro ao salvar histórico: {e}"
        )

        return False


# ============================================================
# TELEGRAM
# ============================================================

def enviar_oferta(
    foto_url,
    legenda,
    link_produto
):

    if not TELEGRAM_TOKEN:

        print(
            "❌ TELEGRAM_TOKEN ausente."
        )

        return False

    if not foto_url:

        print(
            "❌ Imagem ausente."
        )

        return False

    if not link_produto:

        print(
            "❌ Link ausente."
        )

        return False

    url = (
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
                        link_produto
                }
            ]
        ]
    }

    payload = {

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
                keyboard
            )
    }

    try:

        resposta = session.post(
            url,
            data=payload,
            timeout=HTTP_TIMEOUT
        )

        resultado = resposta.json()

        if resultado.get("ok"):

            print(
                "✅ Telegram publicou."
            )

            return True

        print(
            "❌ Telegram rejeitou:"
        )

        print(resultado)

        return False

    except Exception as e:

        print(
            f"❌ Erro Telegram: {e}"
        )

        return False


# ============================================================
# NORMALIZAR URL
# ============================================================

def normalizar_url(
    url,
    base_url
):

    if not url:

        return ""

    url = url.strip()

    url = html_unescape(
        url
    )

    if url.startswith("//"):

        url = "https:" + url

    elif url.startswith("/"):

        url = urljoin(
            base_url,
            url
        )

    elif not url.startswith(
        ("http://", "https://")
    ):

        return ""

    return url.split(
        "#"
    )[0]


def html_unescape(
    texto
):

    import html

    return html.unescape(
        texto
    )


# ============================================================
# IDENTIFICAR LINK DE PRODUTO
# ============================================================

def parece_link_produto(
    url
):

    if not url:

        return False

    url_lower = (
        unquote(url)
        .lower()
    )

    padroes = [

        "/p/mlb",

        "mlb-",

        "produto.mercadolivre.com.br",

        "mercadolivre.com.br/up/",

        "/up/",

        "mercadolibre.com/p/",

        "mercadolibre.com.ar/p/"

    ]

    return any(
        padrao in url_lower
        for padrao in padroes
    )


# ============================================================
# EXTRAIR LINKS DO HTML
# ============================================================

def extrair_links_do_html(
    html,
    base_url
):

    encontrados = []

    # --------------------------------------------------------
    # BeautifulSoup
    # --------------------------------------------------------

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # --------------------------------------------------------
    # <a href>
    # --------------------------------------------------------

    for tag in soup.find_all(
        "a",
        href=True
    ):

        href = normalizar_url(
            tag.get("href"),
            base_url
        )

        if parece_link_produto(
            href
        ):

            encontrados.append(
                href
            )

    # --------------------------------------------------------
    # <link>
    # --------------------------------------------------------

    for tag in soup.find_all(
        "link",
        href=True
    ):

        href = normalizar_url(
            tag.get("href"),
            base_url
        )

        if parece_link_produto(
            href
        ):

            encontrados.append(
                href
            )

    # --------------------------------------------------------
    # JSON / SCRIPT
    # --------------------------------------------------------

    padroes = [

        r'https?://[^"\']+',

        r'//[^"\']+',

        r'\/p\/MLB[0-9]+',

        r'\/MLB-[0-9]+',

        r'\/up\/[^"\']+',

        r'\/sec\/[^"\']+'

    ]

    for padrao in padroes:

        try:

            resultados = re.findall(
                padrao,
                html,
                re.IGNORECASE
            )

        except Exception:

            resultados = []

        for item in resultados:

            url = normalizar_url(
                item,
                base_url
            )

            if parece_link_produto(
                url
            ):

                encontrados.append(
                    url
                )

    # --------------------------------------------------------
    # LIMPAR
    # --------------------------------------------------------

    resultado = []

    vistos = set()

    for link in encontrados:

        link = link.replace(
            "\\/",
            "/"
        )

        if link in vistos:
            continue

        vistos.add(link)

        resultado.append(
            link
        )

    return resultado


# ============================================================
# BUSCAR PRODUTOS DA VITRINE
# ============================================================

def obter_produtos_da_vitrine(
    url_vitrine
):

    headers = obter_headers()

    print("")
    print(
        "🔎 INICIANDO LEITURA DA VITRINE"
    )
    print(
        f"🔗 {url_vitrine}"
    )

    # --------------------------------------------------------
    # PRIMEIRA REQUISIÇÃO
    # --------------------------------------------------------

    try:

        inicio = time.time()

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

    except requests.exceptions.Timeout:

        print(
            "❌ Timeout na vitrine."
        )

        return []

    except requests.exceptions.RequestException as e:

        print(
            f"❌ Erro HTTP vitrine: {e}"
        )

        return []

    # --------------------------------------------------------
    # 403
    # --------------------------------------------------------

    if resposta.status_code == 403:

        print(
            "⚠️ Mercado Livre retornou 403."
        )

        print(
            "⚠️ O servidor bloqueou a "
            "requisição automatizada."
        )

        return []

    # --------------------------------------------------------
    # EXTRAIR LINKS
    # --------------------------------------------------------

    links = extrair_links_do_html(
        resposta.text,
        resposta.url
    )

    print(
        f"🔎 Produtos encontrados "
        f"no HTML: {len(links)}"
    )

    # --------------------------------------------------------
    # SE NÃO ACHOU, PROCURAR REDIRECIONAMENTOS
    # --------------------------------------------------------

    if not links:

        for redirect in resposta.history:

            location = redirect.headers.get(
                "location",
                ""
            )

            location = normalizar_url(
                location,
                url_vitrine
            )

            if parece_link_produto(
                location
            ):

                links.append(
                    location
                )

    # --------------------------------------------------------
    # DEDUPLICAR
    # --------------------------------------------------------

    resultado = []

    vistos = set()

    for link in links:

        # Remover parâmetros que
        # não são necessários para
        # identificar o destino.

        chave = link

        if chave in vistos:
            continue

        vistos.add(chave)

        resultado.append(
            link
        )

    print(
        f"🎯 Produtos únicos: "
        f"{len(resultado)}"
    )

    # --------------------------------------------------------
    # MOSTRAR ALGUNS LINKS PARA DEBUG
    # --------------------------------------------------------

    for i, link in enumerate(
        resultado[:10],
        start=1
    ):

        print(
            f"   {i}. {link}"
        )

    return resultado


# ============================================================
# EXTRAIR PRODUTO
# ============================================================

def extrair_dados_produto(
    url_produto
):

    headers = obter_headers()

    try:

        resposta = session.get(
            url_produto,
            headers=headers,
            allow_redirects=True,
            timeout=HTTP_TIMEOUT
        )

        print(
            f"📦 Produto HTTP "
            f"{resposta.status_code}: "
            f"{resposta.url}"
        )

        if resposta.status_code >= 400:

            print(
                "⚠️ Produto retornou "
                f"{resposta.status_code}"
            )

            return None

        soup = BeautifulSoup(
            resposta.text,
            "html.parser"
        )

        # ----------------------------------------------------
        # TÍTULO
        # ----------------------------------------------------

        titulo = ""

        og_title = soup.find(
            "meta",
            property="og:title"
        )

        if og_title:

            titulo = (
                og_title.get(
                    "content",
                    ""
                ).strip()
            )

        if not titulo:

            h1 = soup.find(
                "h1"
            )

            if h1:

                titulo = h1.get_text(
                    " ",
                    strip=True
                )

        if not titulo:

            titulo = (
                "🔥 Oferta "
                "Imperdível!"
            )

        # ----------------------------------------------------
        # IMAGEM
        # ----------------------------------------------------

        imagem = ""

        og_image = soup.find(
            "meta",
            property="og:image"
        )

        if og_image:

            imagem = (
                og_image.get(
                    "content",
                    ""
                ).strip()
            )

        if not imagem:

            imagem_tag = soup.find(
                "img"
            )

            if imagem_tag:

                imagem = (
                    imagem_tag.get(
                        "src",
                        ""
                    )
                    or
                    imagem_tag.get(
                        "data-src",
                        ""
                    )
                )

        # ----------------------------------------------------
        # PREÇO
        # ----------------------------------------------------

        preco = ""

        meta_preco = soup.find(
            "meta",
            property="product:price:amount"
        )

        if meta_preco:

            preco = (
                meta_preco.get(
                    "content",
                    ""
                ).strip()
            )

        if not preco:

            elemento_preco = soup.find(
                class_=re.compile(
                    r"andes-money-amount"
                )
            )

            if elemento_preco:

                preco = elemento_preco.get_text(
                    " ",
                    strip=True
                )

        return {

            "titulo":
                titulo,

            "imagem":
                imagem,

            "preco":
                preco,

            "url":
                resposta.url

        }

    except Exception as e:

        print(
            f"⚠️ Erro produto: {e}"
        )

        return None


# ============================================================
# PROCESSAR VITRINE
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

        print("")
        print("=" * 60)

        print(
            "🦊 RAPOSA CAÇADORA"
        )

        print(
            f"🔗 Vitrine: "
            f"{url_vitrine}"
        )

        print("=" * 60)

        # ----------------------------------------------------
        # PRODUTOS
        # ----------------------------------------------------

        produtos = (
            obter_produtos_da_vitrine(
                url_vitrine
            )
        )

        if not produtos:

            print("")
            print(
                "❌ Nenhum produto foi "
                "encontrado na vitrine."
            )

            print(
                "⚠️ Isso significa que o "
                "Mercado Livre não entregou "
                "os links dos produtos "
                "para o nosso servidor."
            )

            return

        historico = (
            carregar_historico()
        )

        publicados = 0

        # ----------------------------------------------------
        # PRODUTOS
        # ----------------------------------------------------

        for link in produtos:

            if publicados >= quantidade_maxima:

                break

            if link in historico:

                print(
                    "⏭️ Já publicado:"
                )

                print(link)

                continue

            print("")
            print(
                "--------------------------------"
            )

            print(
                f"🛒 Produto "
                f"{publicados + 1}/"
                f"{quantidade_maxima}"
            )

            print(
                f"🔗 {link}"
            )

            dados = (
                extrair_dados_produto(
                    link
                )
            )

            if not dados:

                print(
                    "⚠️ Não foi possível "
                    "obter dados."
                )

                continue

            titulo = dados.get(
                "titulo",
                "Oferta imperdível!"
            )

            imagem = dados.get(
                "imagem",
                ""
            )

            if not imagem:

                print(
                    "⚠️ Produto sem imagem."
                )

                continue

            legenda = (
                f"🔥 <b>{titulo}</b>\n\n"
                f"⚡ <i>Oferta encontrada "
                f"pela Raposa Caçadora!</i>\n\n"
                f"🛒 <b>Confira no Mercado Livre:</b>"
            )

            # ------------------------------------------------
            # PUBLICAR
            # ------------------------------------------------

            sucesso = enviar_oferta(
                imagem,
                legenda,
                link
            )

            if sucesso:

                salvar_historico(
                    link
                )

                publicados += 1

                print(
                    f"✅ PUBLICADO "
                    f"{publicados}/"
                    f"{quantidade_maxima}"
                )

                if publicados < quantidade_maxima:

                    print(
                        f"⏳ Aguardando "
                        f"{intervalo_seg}s..."
                    )

                    time.sleep(
                        intervalo_seg
                    )

        print("")
        print("=" * 60)

        print(
            f"🏁 FINALIZADO"
        )

        print(
            f"📦 Publicados: "
            f"{publicados}"
        )

        print("=" * 60)

    except Exception as e:

        print(
            f"❌ Erro geral: {e}"
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
        print("=" * 60)

        print(
            "📥 NOVA CONFIGURAÇÃO"
        )

        print("=" * 60)

        # ----------------------------------------------------
        # LINK
        # ----------------------------------------------------

        link = str(
            dados.get(
                "link",
                dados.get(
                    "linkCanal",
                    ""
                )
            )
        ).strip()

        # ----------------------------------------------------
        # INTERVALO
        # ----------------------------------------------------

        try:

            intervalo = int(
                dados.get(
                    "intervalo",
                    300
                )
            )

        except Exception:

            intervalo = 300

        # ----------------------------------------------------
        # QUANTIDADE
        # ----------------------------------------------------

        try:

            quantidade = int(
                dados.get(
                    "quantidade",
                    5
                )
            )

        except Exception:

            quantidade = 5

        # ----------------------------------------------------
        # TELEGRAM
        # ----------------------------------------------------

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
            f"⏱️ Intervalo: {intervalo}s"
        )

        # ----------------------------------------------------
        # VALIDAÇÕES
        # ----------------------------------------------------

        if not link:

            return jsonify({

                "erro":
                    "O link da vitrine "
                    "é obrigatório."

            }), 400

        if quantidade < 1:

            quantidade = 1

        if quantidade > MAX_QUANTIDADE:

            quantidade = (
                MAX_QUANTIDADE
            )

        if intervalo < MIN_INTERVALO:

            intervalo = (
                MIN_INTERVALO
            )

        # ----------------------------------------------------
        # TELEGRAM
        # ----------------------------------------------------

        if not validar_init_data(
            init_data
        ):

            return jsonify({

                "erro":
                    "Autenticação do Telegram "
                    "inválida ou expirada."

            }), 403

        # ----------------------------------------------------
        # THREAD
        # ----------------------------------------------------

        thread = threading.Thread(

            target=
                processar_e_postar_vitrine,

            args=(
                link,
                quantidade,
                intervalo
            ),

            daemon=True
        )

        thread.start()

        print(
            "🚀 Automação iniciada."
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

            "intervalo":
                intervalo

        }), 200

    except Exception as e:

        print(
            f"❌ Erro API: {e}"
        )

        return jsonify({

            "erro":
                f"Erro interno: {e}"

        }), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("")
    print("=" * 60)

    print(
        "🦊 RAPOSA CAÇADORA"
    )

    print("=" * 60)

    print(
        f"🌐 Porta: {PORT}"
    )

    print(
        f"🤖 Telegram: "
        f"{bool(TELEGRAM_TOKEN)}"
    )

    print(
        f"📢 Chat: "
        f"{bool(CHAT_ID)}"
    )

    print(
        "🌐 CORS: Vercel autorizado"
    )

    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=PORT
    )
