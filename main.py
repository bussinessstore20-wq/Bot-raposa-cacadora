import os
import json
import time
import html
import threading
import hashlib
import hmac
from urllib.parse import parse_qsl, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory


# ============================================================
# CAMINHOS
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

REQUEST_TIMEOUT = 30


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
                max-width: 520px;
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

            <p>Servidor online.</p>

            <p>
                Mini App:
                <a href="/app">
                    abrir painel
                </a>
            </p>

            <p>
                Health:
                <a href="/health">
                    verificar servidor
                </a>
            </p>

            <p>
                API:
                <a href="/api/configurar">
                    /api/configurar
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

    if not os.path.isfile(
        INDEX_FILE
    ):

        print(
            "❌ index.html NÃO encontrado."
        )

        try:

            print(
                "📄 Arquivos encontrados:"
            )

            for arquivo in os.listdir(
                BASE_DIR
            ):

                print(
                    f"   - {arquivo}"
                )

        except Exception as e:

            print(
                f"⚠️ Erro listando arquivos: {e}"
            )

        return """
        <!DOCTYPE html>

        <html lang="pt-BR">

        <head>

            <meta charset="UTF-8">

            <title>Erro</title>

        </head>

        <body>

            <h2>❌ Mini App não encontrado</h2>

            <p>
                O arquivo
                <b>index.html</b>
                não está junto do main.py.
            </p>

        </body>

        </html>
        """, 404

    print(
        "✅ index.html encontrado."
    )

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

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

        "mini_app":
            os.path.isfile(INDEX_FILE),

        "rotas": [

            "/",
            "/app",
            "/health",
            "/api/configurar",
            "/configurar"

        ]

    })


# ============================================================
# TESTE GET /api/configurar
# ============================================================

@app.route(
    "/api/configurar",
    methods=["GET"]
)
def configurar_get():

    return jsonify({

        "ok": False,

        "erro":
            "A rota /api/configurar não aceita o método GET.",

        "metodo_correto":
            "POST",

        "rota":
            "/api/configurar"

    }), 405


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

def validar_init_data(
    init_data
):

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


def salvar_historico(
    link
):

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

        resposta = requests.post(

            url,

            data=dados or {},

            timeout=20

        )

        print(
            f"📡 Telegram HTTP: "
            f"{resposta.status_code}"
        )

        try:

            resultado = resposta.json()

        except Exception:

            print(
                "❌ Telegram retornou resposta não-JSON."
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
            f"❌ Erro conexão Telegram "
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

def enviar_mensagem(
    texto
):

    resultado = telegram_api(

        "sendMessage",

        {
            "chat_id":
                CHAT_ID,

            "text":
                texto,

            "parse_mode":
                "HTML"
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
# ENVIAR OFERTA
# ============================================================

def enviar_oferta(
    foto_url,
    legenda,
    link_afiliado
):

    if not foto_url:

        print(
            "❌ Oferta sem foto."
        )

        return False

    if not link_afiliado:

        print(
            "❌ Oferta sem link."
        )

        return False

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
# HEADERS
# ============================================================

def obter_headers():

    return {

        "User-Agent":
            (
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
            (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "image/avif,image/webp,"
                "*/*;q=0.8"
            ),

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache"

    }


# ============================================================
# VALIDAR URL
# ============================================================

def url_http_valida(
    url
):

    if not url:
        return False

    try:

        url = str(
            url
        ).strip()

        parsed = urlparse(
            url
        )

        if parsed.scheme not in (
            "http",
            "https"
        ):

            return False

        if not parsed.netloc:

            return False

        return True

    except Exception:

        return False


# ============================================================
# EXPANDIR LINK
# ============================================================

def expandir_link(
    url,
    headers
):

    print(
        f"🔗 Expandindo: {url}"
    )

    if not url_http_valida(
        url
    ):

        print(
            f"❌ URL inicial inválida: {url}"
        )

        return None

    try:

        resposta = requests.get(

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
            f"📍 URL final recebida: "
            f"{resposta.url}"
        )

        print(
            f"📄 Content-Type: "
            f"{resposta.headers.get('Content-Type', '')}"
        )

        resposta.raise_for_status()

        url_final = str(
            resposta.url or ""
        ).strip()

        if not url_http_valida(
            url_final
        ):

            print(
                f"❌ URL final inválida: {url_final}"
            )

            return None

        print(
            f"✅ URL final válida: {url_final}"
        )

        return url_final

    except requests.RequestException as e:

        print(
            f"❌ Erro HTTP ao expandir URL: {e}"
        )

        return None

    except Exception as e:

        print(
            f"❌ Erro inesperado ao expandir URL: {e}"
        )

        return None


# ============================================================
# NORMALIZAR URL
# ============================================================

def normalizar_url(
    base_url,
    encontrada
):

    if not encontrada:

        return None

    encontrada = str(
        encontrada
    ).strip()

    if not encontrada:

        return None

    if encontrada.startswith(
        (
            "javascript:",
            "mailto:",
            "tel:",
            "#"
        )
    ):

        return None

    try:

        # URL absoluta
        if encontrada.startswith(
            (
                "http://",
                "https://"
            )
        ):

            resultado = encontrada

        else:

            # Base obrigatoriamente válida
            if not url_http_valida(
                base_url
            ):

                print(
                    f"⚠️ Base inválida para urljoin: "
                    f"{base_url}"
                )

                return None

            resultado = urljoin(
                base_url,
                encontrada
            )

        if not url_http_valida(
            resultado
        ):

            return None

        resultado = resultado.split(
            "#",
            1
        )[0]

        return resultado

    except ValueError as e:

        print(
            f"⚠️ URL ignorada por erro de parsing: "
            f"{encontrada[:200]} | {e}"
        )

        return None

    except Exception as e:

        print(
            f"⚠️ Erro normalizando URL: "
            f"{encontrada[:200]} | {e}"
        )

        return None


# ============================================================
# IDENTIFICAR LINK DE PRODUTO
# ============================================================

def parece_produto(
    url
):

    if not url:
        return False

    texto = url.lower()

    padroes = [

        "produto.mercadolivre.com.br",

        "produto.mercadolibre.com.br",

        "/p/mlb",

        "mlb-",

        "/mlb-",

        "mercadolivre.com.br/mlb-",

        "mercadolibre.com/mlb-"

    ]

    return any(
        padrao in texto
        for padrao in padroes
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

    if not url_http_valida(
        url_vitrine
    ):

        print(
            f"❌ URL da vitrine inválida: "
            f"{url_vitrine}"
        )

        return []

    try:

        resposta = requests.get(

            url_vitrine,

            headers=headers,

            timeout=REQUEST_TIMEOUT,

            allow_redirects=True

        )

        print(
            f"📡 Status vitrine: "
            f"{resposta.status_code}"
        )

        print(
            f"📍 URL realmente acessada: "
            f"{resposta.url}"
        )

        print(
            f"📄 Content-Type: "
            f"{resposta.headers.get('Content-Type', '')}"
        )

        resposta.raise_for_status()

    except requests.RequestException as e:

        print(
            f"❌ Erro ao acessar vitrine: {e}"
        )

        return []

    except Exception as e:

        print(
            f"❌ Erro inesperado acessando vitrine: {e}"
        )

        return []

    # --------------------------------------------------------
    # BASE SEGURA
    # --------------------------------------------------------

    base_url = str(
        resposta.url or url_vitrine
    ).strip()

    if not url_http_valida(
        base_url
    ):

        print(
            f"❌ Base URL inválida: {base_url}"
        )

        return []

    # --------------------------------------------------------
    # ANALISAR HTML
    # --------------------------------------------------------

    try:

        soup = BeautifulSoup(
            resposta.text,
            "html.parser"
        )

    except Exception as e:

        print(
            f"❌ Erro analisando HTML: {e}"
        )

        return []

    links = []

    # --------------------------------------------------------
    # LINKS <A>
    # --------------------------------------------------------

    for a in soup.find_all(
        "a",
        href=True
    ):

        encontrado = a.get(
            "href"
        )

        url_produto = normalizar_url(
            base_url,
            encontrado
        )

        if not url_produto:

            continue

        if parece_produto(
            url_produto
        ):

            links.append(
                url_produto
            )

    # --------------------------------------------------------
    # ATRIBUTOS DE LINKS
    # --------------------------------------------------------

    atributos = [

        "data-href",

        "data-url",

        "data-link",

        "data-product-url",

        "data-product-link",

        "data-item-url"

    ]

    for elemento in soup.find_all(
        True
    ):

        for atributo in atributos:

            encontrado = elemento.get(
                atributo
            )

            if not encontrado:

                continue

            url_produto = normalizar_url(

                base_url,

                encontrado

            )

            if not url_produto:

                continue

            if parece_produto(
                url_produto
            ):

                links.append(
                    url_produto
                )

    # --------------------------------------------------------
    # META / JSON-LD
    # --------------------------------------------------------

    # Alguns layouts carregam URLs de produtos
    # dentro de scripts ou JSON.

    try:

        textos_scripts = soup.find_all(
            "script"
        )

        for script in textos_scripts:

            conteudo = script.string

            if not conteudo:

                continue

            conteudo = str(
                conteudo
            )

            # Procurar ocorrências completas
            # de URLs Mercado Livre.

            partes = conteudo.replace(
                '"',
                " "
            ).replace(
                "'",
                " "
            ).replace(
                "\\/",
                "/"
            ).split()

            for parte in partes:

                if (
                    "mercadolivre.com.br"
                    not in parte.lower()
                    and
                    "mercadolibre.com" 
                    not in parte.lower()
                ):

                    continue

                candidato = parte.strip(
                    " ,;()[]{}<>"
                )

                if not candidato.startswith(
                    (
                        "http://",
                        "https://"
                    )
                ):

                    continue

                if parece_produto(
                    candidato
                ):

                    links.append(
                        candidato
                    )

    except Exception as e:

        print(
            f"⚠️ Erro analisando scripts: {e}"
        )

    # --------------------------------------------------------
    # REMOVER DUPLICADOS
    # --------------------------------------------------------

    links_limpos = []

    vistos = set()

    for link in links:

        if not link:
            continue

        link = str(
            link
        ).strip()

        if not url_http_valida(
            link
        ):

            continue

        chave = link.lower()

        if chave in vistos:

            continue

        vistos.add(
            chave
        )

        links_limpos.append(
            link
        )

    print(
        f"📦 {len(links_limpos)} produtos encontrados."
    )

    for numero, produto in enumerate(
        links_limpos[:20],
        start=1
    ):

        print(
            f"   {numero}. {produto}"
        )

    return links_limpos


# ============================================================
# EXTRAIR PRODUTO
# ============================================================

def extrair_produto(
    link,
    headers
):

    print(
        f"🔍 Extraindo produto: {link}"
    )

    if not url_http_valida(
        link
    ):

        print(
            "⚠️ Link de produto inválido."
        )

        return None

    try:

        resposta = requests.get(

            link,

            headers=headers,

            allow_redirects=True,

            timeout=REQUEST_TIMEOUT

        )

        print(
            f"📡 Produto HTTP: "
            f"{resposta.status_code}"
        )

        print(
            f"📍 Produto URL final: "
            f"{resposta.url}"
        )

        resposta.raise_for_status()

    except requests.RequestException as e:

        print(
            f"⚠️ Erro acessando produto: {e}"
        )

        return None

    except Exception as e:

        print(
            f"⚠️ Erro inesperado acessando produto: {e}"
        )

        return None

    try:

        soup = BeautifulSoup(
            resposta.text,
            "html.parser"
        )

    except Exception as e:

        print(
            f"⚠️ Erro analisando produto: {e}"
        )

        return None

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
                "name":
                    "twitter:image"
            }
        )

        if twitter_image:

            foto_url = twitter_image.get(
                "content",
                ""
            ).strip()

    # --------------------------------------------------------
    # IMG PRINCIPAL
    # --------------------------------------------------------

    if not foto_url:

        elemento_img = soup.find(
            "img",
            class_="ui-pdp-image"
        )

        if elemento_img:

            foto_url = (

                elemento_img.get(
                    "src"
                )

                or

                elemento_img.get(
                    "data-src"
                )

                or

                ""

            ).strip()

    # --------------------------------------------------------
    # QUALQUER IMG
    # --------------------------------------------------------

    if not foto_url:

        for img in soup.find_all(
            "img"
        ):

            candidato = (

                img.get(
                    "src"
                )

                or

                img.get(
                    "data-src"
                )

                or

                img.get(
                    "data-lazy"
                )

                or

                ""

            ).strip()

            if candidato.startswith(
                (
                    "http://",
                    "https://"
                )
            ):

                foto_url = candidato

                break

    if not foto_url:

        print(
            "⚠️ Produto sem imagem."
        )

        return None

    if not url_http_valida(
        foto_url
    ):

        print(
            f"⚠️ Imagem inválida: {foto_url}"
        )

        return None

    # --------------------------------------------------------
    # URL FINAL
    # --------------------------------------------------------

    link_final = str(
        resposta.url or link
    ).strip()

    if not url_http_valida(
        link_final
    ):

        link_final = link

    # --------------------------------------------------------
    # ESCAPAR TÍTULO
    # --------------------------------------------------------

    titulo = html.escape(
        titulo
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
# PROCESSAR E POSTAR VITRINE
# ============================================================

def processar_e_postar_vitrine(
    url_vitrine,
    quantidade_maxima,
    intervalo_seg
):

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

        # ----------------------------------------------------
        # EXPANDIR LINK
        # ----------------------------------------------------

        url_final = expandir_link(

            url_vitrine,

            headers

        )

        if not url_final:

            enviar_mensagem(

                "❌ <b>Não foi possível acessar "
                "a vitrine.</b>\n\n"
                "O link informado não pôde ser "
                "expandido ou acessado."

            )

            return

        print(
            f"🔗 URL final confirmada: "
            f"{url_final}"
        )

        # ----------------------------------------------------
        # IDENTIFICAR PRODUTO
        # ----------------------------------------------------

        if parece_produto(
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
                "🏪 Link identificado como vitrine/lista."
            )

            links_produtos = (
                encontrar_links_produtos(
                    url_final,
                    headers
                )
            )

        # ----------------------------------------------------
        # NENHUM PRODUTO
        # ----------------------------------------------------

        if not links_produtos:

            print(
                "⚠️ Nenhum produto encontrado."
            )

            enviar_mensagem(

                "⚠️ <b>Nenhum produto encontrado.</b>\n\n"

                "O Mercado Livre pode ter carregado "
                "os produtos dinamicamente ou a página "
                "não disponibilizou os links no HTML "
                "recebido pelo servidor.\n\n"

                f"🔗 URL analisada:\n"
                f"{html.escape(url_final)}"

            )

            return

        # ----------------------------------------------------
        # HISTÓRICO
        # ----------------------------------------------------

        historico = carregar_historico()

        postados = 0

        tentados = 0

        # ----------------------------------------------------
        # LOOP
        # ----------------------------------------------------

        for link in links_produtos:

            if postados >= quantidade_maxima:

                break

            if not link:

                continue

            link = str(
                link
            ).strip()

            if not url_http_valida(
                link
            ):

                continue

            if link in historico:

                print(
                    f"⏭️ Já postado: {link}"
                )

                continue

            tentados += 1

            produto = extrair_produto(

                link,

                headers

            )

            if not produto:

                print(
                    "⚠️ Produto ignorado."
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

            legenda = (

                f"🔥 <b>{titulo}</b>\n\n"

                f"⚡ <i>Aproveite esta "
                f"promoção por tempo limitado!</i>\n\n"

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
                    link_produto
                )

                historico.add(
                    link_produto
                )

                # Também marca o link original
                if link_produto != link:

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

                if postados < quantidade_maxima:

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

        # ----------------------------------------------------
        # FINAL
        # ----------------------------------------------------

        print(
            "\n" + "=" * 60
        )

        print(
            f"🎯 FINALIZADO: "
            f"{postados} ofertas."
        )

        print(
            f"🔎 Produtos analisados: "
            f"{tentados}"
        )

        print(
            "=" * 60
        )

        if postados > 0:

            enviar_mensagem(

                "✅ <b>Postagens finalizadas!</b>\n\n"

                f"🦊 Ofertas publicadas: "
                f"<b>{postados}</b>\n"

                f"📦 Solicitação: "
                f"<b>{quantidade_maxima}</b>"

            )

        else:

            enviar_mensagem(

                "⚠️ <b>Automação finalizada.</b>\n\n"

                "Nenhuma oferta foi publicada.\n\n"

                "Verifique os logs do servidor para "
                "identificar os produtos encontrados."

            )

    except Exception as e:

        print(
            "\n❌ ERRO FATAL NA AUTOMAÇÃO:"
        )

        print(
            repr(e)
        )

        import traceback

        traceback.print_exc()

        try:

            enviar_mensagem(

                "❌ <b>Erro durante a automação.</b>\n\n"
                f"{html.escape(str(e))}"

            )

        except Exception:

            pass


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
        "📩 POST /api/configurar RECEBIDO"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # CONFIGURAÇÃO
    # --------------------------------------------------------

    if not verificar_configuracao():

        return jsonify({

            "ok":
                False,

            "erro":
                "Bot não configurado."

        }), 500

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

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

            "ok":
                False,

            "erro":
                "Dados inválidos."

        }), 400

    print(
        "📦 Campos recebidos:"
    )

    print(
        list(
            dados.keys()
        )
    )

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
    # VALIDAR INIT DATA
    # --------------------------------------------------------

    if not validar_init_data(
        init_data
    ):

        print(
            "🚫 initData inválido."
        )

        return jsonify({

            "ok":
                False,

            "erro":
                "Autenticação do Telegram inválida."

        }), 403

    print(
        "✅ initData validado."
    )

    # --------------------------------------------------------
    # VALIDAR LINK
    # --------------------------------------------------------

    if not link:

        return jsonify({

            "ok":
                False,

            "erro":
                "Informe o link da vitrine."

        }), 400

    if not url_http_valida(
        link
    ):

        return jsonify({

            "ok":
                False,

            "erro":
                "O link informado não é uma URL válida."

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
    # LOG
    # --------------------------------------------------------

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
        f"⏱️ Intervalo: {intervalo}s"
    )

    print(
        f"📦 Quantidade: {quantidade}"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # AVISO TELEGRAM
    # --------------------------------------------------------

    aviso = enviar_mensagem(

        "🚀 <b>Nova automação iniciada!</b>\n\n"

        f"📦 Quantidade: <b>{quantidade}</b>\n"

        f"⏱️ Intervalo: <b>{intervalo}s</b>\n\n"

        "🔎 Processando vitrine..."

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
            "✅ Thread da automação iniciada."
        )

    except Exception as e:

        print(
            f"❌ Erro iniciando thread: {e}"
        )

        return jsonify({

            "ok":
                False,

            "erro":
                "Não foi possível iniciar a automação."

        }), 500

    # --------------------------------------------------------
    # RESPOSTA
    # --------------------------------------------------------

    return jsonify({

        "ok":
            True,

        "mensagem":
            "Postagens iniciadas.",

        "link":
            link,

        "intervalo":
            intervalo,

        "quantidade":
            quantidade,

        "telegram_aviso":
            aviso

    }), 200


# ============================================================
# POST /configurar
# ============================================================
#
# Compatibilidade com versões antigas do Mini App.
#
# ============================================================

@app.route(
    "/configurar",
    methods=["POST"]
)
def configurar_compatibilidade():

    print(
        "🔄 POST /configurar recebido."
    )

    return configurar()


# ============================================================
# GET /configurar
# ============================================================

@app.route(
    "/configurar",
    methods=["GET"]
)
def configurar_get():

    return jsonify({

        "ok":
            False,

        "erro":
            "A rota /configurar existe. "
            "Para iniciar uma automação use POST.",

        "metodo":
            "POST",

        "rota_recomendada":
            "/api/configurar",

        "servico":
            "Raposa Caçadora"

    }), 405


# ============================================================
# ERRO 404 JSON PARA API
# ============================================================

@app.errorhandler(404)
def erro_404(e):

    caminho = request.path

    if caminho.startswith(
        "/api/"
    ) or caminho == "/configurar":

        return jsonify({

            "ok":
                False,

            "erro":
                "Rota não encontrada.",

            "rota":
                caminho,

            "metodo":
                request.method,

            "rotas_disponiveis": [

                "/",
                "/app",
                "/health",
                "/api/configurar",
                "/configurar"

            ]

        }), 404

    return e


# ============================================================
# ERRO 405
# ============================================================

@app.errorhandler(405)
def erro_405(e):

    return jsonify({

        "ok":
            False,

        "erro":
            "Método não permitido.",

        "metodo":
            request.method,

        "rota":
            request.path,

        "metodo_correto":
            "POST"

        if request.path in (
            "/api/configurar",
            "/configurar"
        )

        else None

    }), 405


# ============================================================
# ERRO 500
# ============================================================

@app.errorhandler(500)
def erro_500(e):

    print(
        f"❌ Erro interno Flask: {e}"
    )

    return jsonify({

        "ok":
            False,

        "erro":
            "Erro interno no servidor.",

        "detalhe":
            str(e)

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
            "⚠️ TELEGRAM_TOKEN não configurado."
        )

    if CHAT_ID:

        print(
            f"💬 CHAT_ID: {CHAT_ID}"
        )

    else:

        print(
            "⚠️ CHAT_ID não configurado."
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

    print(
        "📌 Rotas:"
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
        "   POST /configurar"
    )

    print(
        "=" * 60
    )

    app.run(

        host="0.0.0.0",

        port=PORT,

        debug=False

    )
