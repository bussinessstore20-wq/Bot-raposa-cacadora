import os
import json
import time
import html
import threading
import hashlib
import hmac
import re

from urllib.parse import (
    parse_qsl,
    urljoin,
    urlparse,
    unquote
)

import requests

from bs4 import BeautifulSoup

from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory
)


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

REQUEST_TIMEOUT = 30


# ============================================================
# SESSÃO HTTP
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 "
        "Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    )
})


# ============================================================
# FLASK
# ============================================================

app = Flask(
    __name__,
    static_folder=BASE_DIR
)


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return """
    <!DOCTYPE html>
    <html lang="pt-BR">

    <head>
        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >

        <title>Raposa Caçadora</title>

        <style>

            body {
                margin: 0;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                background: #05070a;
                color: white;
                font-family: Arial, sans-serif;
            }

            .box {
                width: 90%;
                max-width: 500px;
                padding: 30px;
                text-align: center;
                background: #111827;
                border-radius: 18px;
                box-shadow:
                    0 10px 40px
                    rgba(0,0,0,.5);
            }

            h1 {
                color: #f97316;
            }

            p {
                color: #cbd5e1;
            }

            a {
                color: #fb923c;
            }

        </style>

    </head>

    <body>

        <div class="box">

            <h1>🦊 Raposa Caçadora</h1>

            <p>
                Servidor online.
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
                    health check
                </a>
            </p>

        </div>

    </body>

    </html>
    """


# ============================================================
# MINI APP
# ============================================================

@app.route("/app")
def mini_app():

    print(
        f"📂 Procurando index.html em: {INDEX_FILE}"
    )

    if not os.path.isfile(INDEX_FILE):

        print(
            "❌ index.html NÃO encontrado."
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

                <h2>
                    ❌ Mini App não encontrado
                </h2>

                <p>
                    O arquivo
                    <b>index.html</b>
                    não está junto do main.py.
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

@app.route("/health")
def health():

    return jsonify({
        "ok": True,
        "servico": "Raposa Caçadora",
        "status": "online",
        "mini_app": os.path.isfile(
            INDEX_FILE
        )
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
            in sorted(
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

        return hmac.compare_digest(
            calculado,
            hash_recebido
        )

    except Exception as e:

        print(
            f"⚠️ Erro validando initData: {e}"
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
            f"⚠️ Erro carregando histórico: {e}"
        )

        return set()


def salvar_historico(link):

    try:

        with historico_lock:

            with open(
                ARQUIVO_HISTORICO,
                "a",
                encoding="utf-8"
            ) as arquivo:

                arquivo.write(
                    link + "\n"
                )

    except Exception as e:

        print(
            f"⚠️ Erro salvando histórico: {e}"
        )


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
            timeout=REQUEST_TIMEOUT
        )

        texto = resposta.text

        try:

            resultado = resposta.json()

        except Exception:

            print(
                "❌ Telegram retornou resposta "
                "não-JSON:"
            )

            print(
                texto[:1000]
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

    except requests.RequestException as e:

        print(
            f"❌ Erro de conexão Telegram "
            f"({metodo}): {e}"
        )

        return None

    except Exception as e:

        print(
            f"❌ Erro Telegram "
            f"({metodo}): {e}"
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
            "disable_web_page_preview": False
        }
    )

    return bool(
        resultado
        and resultado.get("ok")
    )


# ============================================================
# ENVIAR OFERTA
# ============================================================

def enviar_oferta(
    foto_url,
    legenda,
    link_afiliado
):

    teclado = {
        "inline_keyboard": [
            [
                {
                    "text":
                        "🛒 COMPRAR NO MERCADO LIVRE",
                    "url":
                        link_afiliado
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
            )
    }

    resultado = telegram_api(
        "sendPhoto",
        dados
    )

    return bool(
        resultado
        and resultado.get("ok")
    )


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
            "Chrome/120.0.0.0 "
            "Safari/537.36"
        ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8",

        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,"
            "image/avif,image/webp,"
            "*/*;q=0.8",

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache"
    }


# ============================================================
# NORMALIZAR URL
# ============================================================

def normalizar_url(url):

    if not url:
        return ""

    url = url.strip()

    if not url:
        return ""

    if not url.startswith(
        ("http://", "https://")
    ):

        url = "https://" + url

    return url


# ============================================================
# EXPANDIR LINK
# ============================================================

def expandir_link(
    url,
    headers
):

    url = normalizar_url(
        url
    )

    if not url:
        return None

    print(
        f"🔗 Expandindo: {url}"
    )

    try:

        resposta = session.get(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"📡 Status expansão: "
            f"{resposta.status_code}"
        )

        print(
            f"🔗 URL final: "
            f"{resposta.url}"
        )

        resposta.raise_for_status()

        return resposta.url

    except Exception as e:

        print(
            f"⚠️ GET com redirects falhou: {e}"
        )

    # --------------------------------------------------------
    # FALLBACK HEAD
    # --------------------------------------------------------

    try:

        resposta = session.head(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"📡 HEAD status: "
            f"{resposta.status_code}"
        )

        print(
            f"🔗 HEAD final: "
            f"{resposta.url}"
        )

        if resposta.url:
            return resposta.url

    except Exception as e:

        print(
            f"⚠️ HEAD falhou: {e}"
        )

    return None


# ============================================================
# VERIFICAR SE É PRODUTO
# ============================================================

def parece_produto_mercadolivre(url):

    if not url:
        return False

    url_lower = url.lower()

    padroes = [

        "produto.mercadolivre.com.br",

        "produto.mercadolivre.com",

        "/p/mlb",

        "/p/MLB".lower(),

        "mlb-",

        "mercadolivre.com.br/p/",

        "mercadolivre.com/p/"
    ]

    return any(
        padrao in url_lower
        for padrao in padroes
    )


# ============================================================
# EXTRAIR IDS MLB DO HTML
# ============================================================

def extrair_ids_mlb(texto):

    if not texto:
        return []

    encontrados = []

    padroes = [

        r"MLB[-_ ]?\d{5,}",

        r"MLB\d{5,}",

        r"mlb[-_ ]?\d{5,}"
    ]

    for padrao in padroes:

        resultados = re.findall(
            padrao,
            texto,
            flags=re.IGNORECASE
        )

        for resultado in resultados:

            valor = resultado.upper()

            valor = re.sub(
                r"[\s_]+",
                "-",
                valor
            )

            if valor.startswith("MLB"):

                if "-" not in valor:

                    valor = (
                        "MLB-"
                        + valor[3:]
                    )

                encontrados.append(
                    valor
                )

    return list(
        dict.fromkeys(
            encontrados
        )
    )


# ============================================================
# DESCOBRIR LINKS DE PRODUTOS
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
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"📡 Status vitrine: "
            f"{resposta.status_code}"
        )

        resposta.raise_for_status()

    except Exception as e:

        print(
            f"❌ Erro ao acessar vitrine: {e}"
        )

        return []

    html_text = resposta.text

    soup = BeautifulSoup(
        html_text,
        "html.parser"
    )

    links = []

    # --------------------------------------------------------
    # LINKS <a>
    # --------------------------------------------------------

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a.get(
            "href",
            ""
        ).strip()

        if not href:
            continue

        href = html.unescape(
            href
        )

        href = urljoin(
            url_vitrine,
            href
        )

        href = href.split(
            "#"
        )[0]

        href = href.strip()

        if parece_produto_mercadolivre(
            href
        ):

            links.append(
                href
            )

    # --------------------------------------------------------
    # ATRIBUTOS
    # --------------------------------------------------------

    for elemento in soup.find_all():

        for atributo in (
            "data-url",
            "data-href",
            "data-link",
            "data-product-url"
        ):

            valor = elemento.get(
                atributo
            )

            if not valor:
                continue

            valor = html.unescape(
                str(valor)
            ).strip()

            valor = urljoin(
                url_vitrine,
                valor
            )

            if parece_produto_mercadolivre(
                valor
            ):

                links.append(
                    valor
                )

    # --------------------------------------------------------
    # URLS ENCONTRADAS NO HTML
    # --------------------------------------------------------

    regex_urls = re.findall(
        r'https?://[^\s"\'<>]+',
        html_text
    )

    for url in regex_urls:

        url = html.unescape(
            url
        )

        url = url.replace(
            "\\/",
            "/"
        )

        if parece_produto_mercadolivre(
            url
        ):

            links.append(
                url
            )

    # --------------------------------------------------------
    # IDS MLB
    # --------------------------------------------------------

    ids = extrair_ids_mlb(
        html_text
    )

    for mlb in ids:

        links.append(
            f"https://produto.mercadolivre.com.br/{mlb}"
        )

    # --------------------------------------------------------
    # NORMALIZAÇÃO
    # --------------------------------------------------------

    resultado = []

    vistos = set()

    for link in links:

        if not link:
            continue

        link = link.strip()

        if link in vistos:
            continue

        vistos.add(
            link
        )

        resultado.append(
            link
        )

    print(
        f"📦 {len(resultado)} "
        f"produtos encontrados."
    )

    # --------------------------------------------------------
    # MOSTRAR ALGUNS LINKS NO LOG
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
            timeout=REQUEST_TIMEOUT
        )

        resposta.raise_for_status()

        url_final = resposta.url

    except Exception as e:

        print(
            f"⚠️ Erro acessando produto: {e}"
        )

        return None

    soup = BeautifulSoup(
        resposta.text,
        "html.parser"
    )

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

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

        if soup.title:

            titulo = soup.title.get_text(
                " ",
                strip=True
            )

    if not titulo:

        titulo = (
            "Oferta Imperdível "
            "Mercado Livre!"
        )

    # --------------------------------------------------------
    # IMAGEM
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # TWITTER IMAGE
    # --------------------------------------------------------

    if not foto_url:

        twitter_image = soup.find(
            "meta",
            attrs={
                "name": "twitter:image"
            }
        )

        if twitter_image:

            foto_url = twitter_image.get(
                "content",
                ""
            ).strip()

    # --------------------------------------------------------
    # IMAGEM UI PDP
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # PRIMEIRA IMAGEM
    # --------------------------------------------------------

    if not foto_url:

        for img in soup.find_all(
            "img"
        ):

            candidato = (

                img.get("src")

                or img.get("data-src")

                or img.get(
                    "data-lazy-src"
                )

                or ""
            )

            candidato = str(
                candidato
            ).strip()

            if candidato.startswith(
                "http"
            ):

                foto_url = candidato

                break

    # --------------------------------------------------------
    # NORMALIZAR IMAGEM
    # --------------------------------------------------------

    if foto_url:

        foto_url = urljoin(
            url_final,
            foto_url
        )

    if not foto_url:

        print(
            "⚠️ Produto sem imagem."
        )

        return None

    # --------------------------------------------------------
    # LIMPAR TÍTULO
    # --------------------------------------------------------

    titulo = re.sub(
        r"\s+",
        " ",
        titulo
    ).strip()

    titulo = html.escape(
        titulo
    )

    # --------------------------------------------------------
    # URL FINAL
    # --------------------------------------------------------

    link_final = url_final

    print(
        f"   📝 Título: "
        f"{html.unescape(titulo)[:100]}"
    )

    print(
        f"   🖼️ Imagem: "
        f"{foto_url[:150]}"
    )

    return {

        "titulo":
            titulo,

        "foto_url":
            foto_url,

        "link":
            link_final
    }


# ============================================================
# PROCESSAR VITRINE
# ============================================================

def processar_e_postar_vitrine(
    url_vitrine,
    quantidade_maxima,
    intervalo_seg
):

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
        f"🔗 Entrada: {url_vitrine}"
    )

    print(
        f"📦 Quantidade: "
        f"{quantidade_maxima}"
    )

    print(
        f"⏱️ Intervalo: "
        f"{intervalo_seg}s"
    )

    # --------------------------------------------------------
    # EXPANDIR LINK
    # --------------------------------------------------------

    url_final = expandir_link(
        url_vitrine,
        headers
    )

    if not url_final:

        enviar_mensagem(
            "❌ <b>Não foi possível acessar o link.</b>\n\n"
            "Verifique se o link da vitrine ou "
            "do produto está correto."
        )

        return

    print(
        f"🔗 URL final: {url_final}"
    )

    # --------------------------------------------------------
    # IDENTIFICAR PRODUTO OU VITRINE
    # --------------------------------------------------------

    if parece_produto_mercadolivre(
        url_final
    ):

        print(
            "🎯 Link identificado como produto."
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

    # --------------------------------------------------------
    # NENHUM PRODUTO
    # --------------------------------------------------------

    if not links_produtos:

        print(
            "⚠️ Nenhum produto encontrado."
        )

        enviar_mensagem(
            "⚠️ <b>Nenhum produto encontrado.</b>\n\n"
            "O link foi acessado, mas não foi "
            "possível identificar os produtos "
            "automaticamente.\n\n"
            "Isso pode acontecer quando a vitrine "
            "é carregada dinamicamente pelo "
            "Mercado Livre."
        )

        return

    # --------------------------------------------------------
    # LIMITAR
    # --------------------------------------------------------

    links_produtos = links_produtos[
        :quantidade_maxima
    ]

    print(
        f"🎯 Serão processados "
        f"{len(links_produtos)} links."
    )

    # --------------------------------------------------------
    # HISTÓRICO
    # --------------------------------------------------------

    historico = carregar_historico()

    postados = 0

    tentativas = 0

    # --------------------------------------------------------
    # LOOP
    # --------------------------------------------------------

    for link in links_produtos:

        if postados >= quantidade_maxima:
            break

        if not link:
            continue

        link = link.strip()

        if not link:
            continue

        if link in historico:

            print(
                f"⏭️ Já postado: {link}"
            )

            continue

        tentativas += 1

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
        ]

        # ----------------------------------------------------
        # LEGENDA
        # ----------------------------------------------------

        legenda = (
            f"🔥 <b>{titulo}</b>\n\n"
            f"⚡ <i>Aproveite esta promoção "
            f"por tempo limitado!</i>\n\n"
            f"🛒 <b>Confira a oferta no "
            f"Mercado Livre.</b>"
        )

        # ----------------------------------------------------
        # PUBLICAR
        # ----------------------------------------------------

        sucesso = enviar_oferta(
            foto_url,
            legenda,
            link_produto
        )

        if sucesso:

            salvar_historico(
                link_produto
            )

            historico.add(
                link_produto
            )

            postados += 1

            print(
                f"✅ POSTADO "
                f"{postados}/{quantidade_maxima}"
            )

            # ------------------------------------------------
            # INTERVALO
            # ------------------------------------------------

            if (
                postados < quantidade_maxima
                and postados < len(
                    links_produtos
                )
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
                "❌ Falha ao publicar produto."
            )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    print(
        "\n" + "=" * 60
    )

    print(
        f"🎯 FINALIZADO: "
        f"{postados} ofertas."
    )

    print(
        f"🔎 Tentativas: "
        f"{tentativas}"
    )

    print(
        "=" * 60
    )

    if postados > 0:

        enviar_mensagem(
            "✅ <b>Postagens finalizadas!</b>\n\n"
            f"🦊 Ofertas publicadas: "
            f"<b>{postados}</b>"
        )

    else:

        enviar_mensagem(
            "⚠️ <b>Processamento finalizado.</b>\n\n"
            "Nenhuma oferta foi publicada.\n\n"
            "Verifique os logs do servidor para "
            "saber quais produtos não puderam "
            "ser extraídos."
        )


# ============================================================
# API CONFIGURAR
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
        "📩 REQUISIÇÃO /api/configurar"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # CONFIGURAÇÃO
    # --------------------------------------------------------

    if not verificar_configuracao():

        return jsonify({
            "ok": False,
            "erro":
                "Bot não configurado no servidor."
        }), 500

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    try:

        dados = request.get_json(
            silent=True
        )

    except Exception as e:

        print(
            f"❌ Erro lendo JSON: {e}"
        )

        dados = None

    if not isinstance(
        dados,
        dict
    ):

        print(
            "❌ Corpo da requisição "
            "não é JSON válido."
        )

        return jsonify({
            "ok": False,
            "erro":
                "Dados inválidos. "
                "A requisição precisa ser JSON."
        }), 400

    # --------------------------------------------------------
    # LINK
    # --------------------------------------------------------

    link = str(
        dados.get(
            "link",
            ""
        )
    ).strip()

    # --------------------------------------------------------
    # INIT DATA
    # --------------------------------------------------------

    init_data = str(
        dados.get(
            "initData",
            ""
        )
    )

    # --------------------------------------------------------
    # INTERVALO
    # --------------------------------------------------------

    try:

        intervalo = int(
            dados.get(
                "intervalo",
                300
            )
        )

    except Exception:

        intervalo = 300

    # --------------------------------------------------------
    # QUANTIDADE
    # --------------------------------------------------------

    try:

        quantidade = int(
            dados.get(
                "quantidade",
                5
            )
        )

    except Exception:

        quantidade = 5

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    print(
        f"🔗 Link recebido: {link}"
    )

    print(
        f"⏱️ Intervalo recebido: "
        f"{intervalo}"
    )

    print(
        f"📦 Quantidade recebida: "
        f"{quantidade}"
    )

    # --------------------------------------------------------
    # VALIDAR INIT DATA
    # --------------------------------------------------------

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

    print(
        "✅ initData válido."
    )

    # --------------------------------------------------------
    # VALIDAR LINK
    # --------------------------------------------------------

    if not link:

        return jsonify({
            "ok": False,
            "erro":
                "Informe o link da vitrine "
                "ou do produto."
        }), 400

    link = normalizar_url(
        link
    )

    if not link:

        return jsonify({
            "ok": False,
            "erro":
                "Link inválido."
        }), 400

    # --------------------------------------------------------
    # INTERVALO
    # --------------------------------------------------------

    intervalo = max(
        intervalo,
        MIN_INTERVALO
    )

    # --------------------------------------------------------
    # QUANTIDADE
    # --------------------------------------------------------

    quantidade = max(
        1,
        min(
            quantidade,
            MAX_QUANTIDADE
        )
    )

    # --------------------------------------------------------
    # AVISO
    # --------------------------------------------------------

    aviso_enviado = enviar_mensagem(
        "🚀 <b>Nova automação iniciada!</b>\n\n"
        f"🔗 Link recebido:\n"
        f"<code>{html.escape(link)}</code>\n\n"
        f"📦 Quantidade: "
        f"<b>{quantidade}</b>\n"
        f"⏱️ Intervalo: "
        f"<b>{intervalo}s</b>"
    )

    if aviso_enviado:

        print(
            "✅ Aviso enviado ao Telegram."
        )

    else:

        print(
            "⚠️ Não foi possível enviar "
            "o aviso ao Telegram."
        )

    # --------------------------------------------------------
    # THREAD
    # --------------------------------------------------------

    try:

        thread = threading.Thread(
            target=processar_e_postar_vitrine,
            args=(
                link,
                quantidade,
                intervalo
            ),
            daemon=True
        )

        thread.start()

        print(
            "✅ Thread de processamento iniciada."
        )

    except Exception as e:

        print(
            f"❌ Erro iniciando thread: {e}"
        )

        return jsonify({
            "ok": False,
            "erro":
                "Não foi possível iniciar "
                "o processamento."
        }), 500

    # --------------------------------------------------------
    # RESPOSTA
    # --------------------------------------------------------

    return jsonify({
        "ok": True,
        "mensagem":
            "Postagens iniciadas.",
        "link":
            link,
        "quantidade":
            quantidade,
        "intervalo":
            intervalo
    }), 200


# ============================================================
# TRATAMENTO DE ERROS
# ============================================================

@app.errorhandler(400)
def erro_400(error):

    return jsonify({
        "ok": False,
        "erro":
            "Requisição inválida."
    }), 400


@app.errorhandler(404)
def erro_404(error):

    # Mantém o endpoint da API sempre em JSON
    if request.path.startswith(
        "/api/"
    ):

        return jsonify({
            "ok": False,
            "erro":
                "Endpoint não encontrado."
        }), 404

    return (
        """
        <!DOCTYPE html>

        <html lang="pt-BR">

        <head>
            <meta charset="UTF-8">
            <title>404</title>
        </head>

        <body
            style="
                background:#05070a;
                color:white;
                font-family:Arial;
                text-align:center;
                padding:40px;
            "
        >

            <h1>404</h1>

            <p>
                Página não encontrada.
            </p>

        </body>

        </html>
        """,
        404
    )


@app.errorhandler(405)
def erro_405(error):

    return jsonify({
        "ok": False,
        "erro":
            "Método HTTP não permitido."
    }), 405


@app.errorhandler(500)
def erro_500(error):

    print(
        f"❌ Erro interno Flask: {error}"
    )

    return jsonify({
        "ok": False,
        "erro":
            "Erro interno do servidor."
    }), 500


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    print(
        "=" * 60
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
        f"📄 index.html: "
        f"{'ENCONTRADO' if os.path.isfile(INDEX_FILE) else 'NÃO ENCONTRADO'}"
    )

    if TELEGRAM_TOKEN:

        print(
            "✅ TELEGRAM_TOKEN configurado."
        )

    else:

        print(
            "❌ TELEGRAM_TOKEN NÃO configurado."
        )

    print(
        f"💬 CHAT_ID: {CHAT_ID}"
    )

    print(
        f"🌐 Porta: {PORT}"
    )

    if WEBAPP_URL:

        print(
            f"📱 Mini App: "
            f"{WEBAPP_URL}/app"
        )

    else:

        print(
            "⚠️ WEBAPP_URL não configurada."
        )

    print(
        "=" * 60
    )

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
