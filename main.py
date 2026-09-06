import os
import json
import time
import html
import threading
import hashlib
import hmac
import re

from urllib.parse import parse_qsl, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory


# ============================================================
# RAPOSA CAÇADORA
# main.py
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

TIMEOUT = 30


# ============================================================
# FLASK
# ============================================================

app = Flask(
    __name__,
    static_folder=BASE_DIR
)


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
        "Chrome/131.0.0.0 "
        "Safari/537.36"
    ),
    "Accept-Language":
        "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept":
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
})


# ============================================================
# LOCKS
# ============================================================

historico_lock = threading.Lock()

tarefas_lock = threading.Lock()

tarefas_ativas = 0


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
                line-height: 1.6;
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
                Health:
                <a href="/health">
                    verificar servidor
                </a>
            </p>

            <p>
                API:
                <b>/api/configurar</b>
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
        f"📂 Procurando index.html em: {INDEX_FILE}",
        flush=True
    )

    if not os.path.isfile(INDEX_FILE):

        print(
            "❌ index.html NÃO encontrado.",
            flush=True
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
                O arquivo index.html
                não está junto do main.py.
            </p>

        </body>

        </html>
        """, 404

    print(
        "✅ index.html encontrado.",
        flush=True
    )

    resposta = send_from_directory(
        BASE_DIR,
        "index.html"
    )

    # Evita cache agressivo do Telegram/browser.
    resposta.headers[
        "Cache-Control"
    ] = (
        "no-store, no-cache, "
        "must-revalidate, max-age=0"
    )

    resposta.headers[
        "Pragma"
    ] = "no-cache"

    resposta.headers[
        "Expires"
    ] = "0"

    return resposta


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({

        "ok": True,

        "servico":
            "Raposa Caçadora",

        "status":
            "online",

        "mini_app":
            os.path.isfile(INDEX_FILE),

        "telegram_configurado":
            bool(TELEGRAM_TOKEN),

        "chat_configurado":
            bool(CHAT_ID),

        "rotas": [
            "/",
            "/app",
            "/health",
            "/api/configurar",
            "/configurar"
        ]

    })


# ============================================================
# CONFIGURAÇÃO
# ============================================================

def verificar_configuracao():

    erros = []

    if not TELEGRAM_TOKEN:
        erros.append(
            "TELEGRAM_TOKEN não configurado"
        )

    if not CHAT_ID:
        erros.append(
            "CHAT_ID não configurado"
        )

    return erros


# ============================================================
# VALIDAR INIT DATA TELEGRAM
# ============================================================

def validar_init_data(init_data):

    if not init_data:
        print(
            "❌ initData vazio.",
            flush=True
        )
        return False

    if not TELEGRAM_TOKEN:
        print(
            "❌ TELEGRAM_TOKEN ausente.",
            flush=True
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
                "❌ Hash do initData ausente.",
                flush=True
            )

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

        valido = hmac.compare_digest(
            calculado,
            hash_recebido
        )

        print(
            f"🔐 initData válido: {valido}",
            flush=True
        )

        return valido

    except Exception as erro:

        print(
            f"⚠️ Erro validando initData: {erro}",
            flush=True
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
            f"⚠️ Erro carregando histórico: {erro}",
            flush=True
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

    except Exception as erro:

        print(
            f"⚠️ Erro salvando histórico: {erro}",
            flush=True
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
            "❌ TELEGRAM_TOKEN não configurado.",
            flush=True
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
            timeout=TIMEOUT
        )

        print(
            f"📡 Telegram {metodo}: "
            f"HTTP {resposta.status_code}",
            flush=True
        )

        resultado = resposta.json()

        if not resultado.get("ok"):

            print(
                "❌ Telegram retornou:",
                resultado,
                flush=True
            )

        return resultado

    except Exception as erro:

        print(
            f"❌ Erro Telegram {metodo}: {erro}",
            flush=True
        )

        return None


# ============================================================
# TELEGRAM - MENSAGEM
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
# TELEGRAM - FOTO
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
            "Chrome/131.0.0.0 "
            "Safari/537.36"
        ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8",

        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8",

        "Referer":
            "https://www.mercadolivre.com.br/"
    }


# ============================================================
# NORMALIZAR URL
# ============================================================

def normalizar_url(url):

    if not url:
        return ""

    url = url.strip()

    if not url.startswith(
        ("http://", "https://")
    ):
        return ""

    return url


# ============================================================
# EXPANDIR LINK
# ============================================================

def expandir_link(
    url,
    headers
):

    print(
        f"🔗 Expandindo URL: {url}",
        flush=True
    )

    try:

        resposta = session.get(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=TIMEOUT
        )

        print(
            f"🔗 HTTP expansão: "
            f"{resposta.status_code}",
            flush=True
        )

        print(
            f"🔗 URL final: "
            f"{resposta.url}",
            flush=True
        )

        resposta.raise_for_status()

        return resposta.url

    except Exception as erro:

        print(
            f"❌ Erro expandindo URL: {erro}",
            flush=True
        )

        return None


# ============================================================
# DETECTAR PRODUTO
# ============================================================

def parece_produto_mercadolivre(url):

    if not url:
        return False

    url_lower = url.lower()

    padroes = [

        "produto.mercadolivre.com.br",

        "mercadolivre.com.br/p/mlb",

        "mercadolivre.com.br/mlb-",

        "/p/mlb",

        "mlb-"

    ]

    return any(
        padrao in url_lower
        for padrao in padroes
    )


# ============================================================
# EXTRAIR LINKS DO HTML
# ============================================================

def extrair_links_do_html(
    html_texto,
    url_base
):

    soup = BeautifulSoup(
        html_texto,
        "html.parser"
    )

    encontrados = []

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

        href = urljoin(
            url_base,
            href
        )

        href = href.split("#")[0]

        if parece_produto_mercadolivre(
            href
        ):

            encontrados.append(
                href
            )

    # --------------------------------------------------------
    # URLS EMBUTIDAS EM SCRIPTS
    # --------------------------------------------------------

    padroes_regex = [

        r'https?://[^"\']*mercadolivre\.com\.br[^"\']*MLB-[0-9]+[^"\']*',

        r'https?://[^"\']*mercadolivre\.com\.br[^"\']*/p/MLB[0-9]+[^"\']*',

        r'https?://[^"\']*produto\.mercadolivre\.com\.br[^"\']*',

    ]

    for script in soup.find_all(
        "script"
    ):

        conteudo = script.string or script.get_text()

        if not conteudo:
            continue

        for padrao in padroes_regex:

            encontrados.extend(
                re.findall(
                    padrao,
                    conteudo,
                    flags=re.IGNORECASE
                )
            )

    # --------------------------------------------------------
    # NORMALIZAÇÃO
    # --------------------------------------------------------

    resultado = []

    vistos = set()

    for link in encontrados:

        link = html.unescape(
            link
        )

        link = link.replace(
            "\\/",
            "/"
        )

        link = link.strip(
            " \t\r\n\"'"
        )

        if not link.startswith(
            "http"
        ):
            continue

        if not parece_produto_mercadolivre(
            link
        ):
            continue

        # Remove parâmetros desnecessários
        try:

            partes = urlparse(link)

            link_limpo = (
                f"{partes.scheme}://"
                f"{partes.netloc}"
                f"{partes.path}"
            )

        except Exception:

            link_limpo = link

        if link_limpo not in vistos:

            vistos.add(
                link_limpo
            )

            resultado.append(
                link_limpo
            )

    return resultado


# ============================================================
# DESCOBRIR LINKS DE PRODUTOS
# ============================================================

def encontrar_links_produtos(
    url_vitrine,
    headers
):

    print(
        "🔎 Acessando vitrine...",
        flush=True
    )

    try:

        resposta = session.get(
            url_vitrine,
            headers=headers,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        print(
            f"🌐 Vitrine HTTP: "
            f"{resposta.status_code}",
            flush=True
        )

        print(
            f"🌐 URL final: "
            f"{resposta.url}",
            flush=True
        )

        resposta.raise_for_status()

    except Exception as erro:

        print(
            f"❌ Erro acessando vitrine: {erro}",
            flush=True
        )

        return []

    links = extrair_links_do_html(
        resposta.text,
        resposta.url
    )

    print(
        f"📦 Produtos encontrados no HTML: "
        f"{len(links)}",
        flush=True
    )

    return links


# ============================================================
# EXTRAIR PREÇO
# ============================================================

def extrair_preco(
    soup
):

    seletores = [

        (
            "meta",
            {
                "property":
                    "product:price:amount"
            }
        ),

        (
            "meta",
            {
                "itemprop":
                    "price"
            }
        )

    ]

    for tag, atributos in seletores:

        elemento = soup.find(
            tag,
            atributos
        )

        if elemento:

            valor = (
                elemento.get("content")
                or ""
            ).strip()

            if valor:
                return valor

    # Tentativa por JSON-LD

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        try:

            dados = json.loads(
                script.string or ""
            )

            blocos = (
                dados
                if isinstance(dados, list)
                else [dados]
            )

            for bloco in blocos:

                if not isinstance(
                    bloco,
                    dict
                ):
                    continue

                offers = bloco.get(
                    "offers"
                )

                if isinstance(
                    offers,
                    dict
                ):

                    preco = offers.get(
                        "price"
                    )

                    if preco:
                        return str(
                            preco
                        )

        except Exception:
            continue

    return ""


# ============================================================
# EXTRAIR PRODUTO
# ============================================================

def extrair_produto(
    link,
    headers
):

    print(
        f"🔎 Extraindo produto: {link}",
        flush=True
    )

    try:

        resposta = session.get(
            link,
            headers=headers,
            allow_redirects=True,
            timeout=TIMEOUT
        )

        print(
            f"📄 Produto HTTP: "
            f"{resposta.status_code}",
            flush=True
        )

        resposta.raise_for_status()

    except Exception as erro:

        print(
            f"⚠️ Erro acessando produto: {erro}",
            flush=True
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

        titulo = (
            "Oferta Imperdível Mercado Livre!"
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

            if candidato.startswith(
                "http"
            ):

                foto_url = candidato

                break

    if not foto_url:

        print(
            "⚠️ Produto sem imagem.",
            flush=True
        )

        return None

    # --------------------------------------------------------
    # PREÇO
    # --------------------------------------------------------

    preco = extrair_preco(
        soup
    )

    # --------------------------------------------------------
    # LIMPEZA
    # --------------------------------------------------------

    titulo_original = titulo

    titulo = html.escape(
        titulo
    )

    foto_url = html.unescape(
        foto_url
    )

    return {

        "titulo":
            titulo,

        "titulo_original":
            titulo_original,

        "foto_url":
            foto_url,

        "preco":
            preco,

        "link":
            link

    }


# ============================================================
# MONTAR LEGENDA
# ============================================================

def montar_legenda(
    produto
):

    titulo = produto.get(
        "titulo",
        "Oferta Imperdível"
    )

    preco = produto.get(
        "preco",
        ""
    )

    texto = (
        f"🔥 <b>{titulo}</b>\n\n"
    )

    if preco:

        texto += (
            f"💰 <b>Preço:</b> "
            f"R$ {html.escape(preco)}\n\n"
        )

    texto += (
        "⚡ <i>Aproveite esta oferta "
        "por tempo limitado!</i>\n\n"
        "👉 <b>Clique abaixo para "
        "ver a oferta:</b>"
    )

    return texto


# ============================================================
# PROCESSAR E POSTAR VITRINE
# ============================================================

def processar_e_postar_vitrine(
    url_vitrine,
    quantidade_maxima,
    intervalo_seg
):

    global tarefas_ativas

    try:

        headers = obter_headers()

        print(
            "\n" + "=" * 60,
            flush=True
        )

        print(
            "🦊 NOVA TAREFA",
            flush=True
        )

        print(
            "=" * 60,
            flush=True
        )

        print(
            f"🔗 Entrada: {url_vitrine}",
            flush=True
        )

        print(
            f"📦 Quantidade: "
            f"{quantidade_maxima}",
            flush=True
        )

        print(
            f"⏱️ Intervalo: "
            f"{intervalo_seg}s",
            flush=True
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
                "o link informado.</b>"
            )

            return

        print(
            f"🔗 URL final: {url_final}",
            flush=True
        )

        # ----------------------------------------------------
        # IDENTIFICAR PRODUTO OU VITRINE
        # ----------------------------------------------------

        if parece_produto_mercadolivre(
            url_final
        ):

            print(
                "🛒 Link identificado como produto.",
                flush=True
            )

            links_produtos = [
                url_final
            ]

        else:

            print(
                "🏪 Link identificado como vitrine/lista.",
                flush=True
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

            enviar_mensagem(
                "⚠️ <b>Nenhum produto encontrado.</b>\n\n"
                "O link foi acessado, mas não foi "
                "possível localizar produtos no "
                "conteúdo retornado pelo Mercado Livre.\n\n"
                "Verifique se a vitrine é pública."
            )

            return

        print(
            f"📦 Total descoberto: "
            f"{len(links_produtos)}",
            flush=True
        )

        # ----------------------------------------------------
        # HISTÓRICO
        # ----------------------------------------------------

        historico = carregar_historico()

        postados = 0

        # ----------------------------------------------------
        # LOOP
        # ----------------------------------------------------

        for link in links_produtos:

            if postados >= quantidade_maxima:
                break

            if not link:
                continue

            link = link.strip()

            if link in historico:

                print(
                    f"⏭️ Já postado: {link}",
                    flush=True
                )

                continue

            produto = extrair_produto(
                link,
                headers
            )

            if not produto:

                print(
                    "⚠️ Produto ignorado.",
                    flush=True
                )

                continue

            legenda = montar_legenda(
                produto
            )

            sucesso = enviar_oferta(
                produto["foto_url"],
                legenda,
                produto["link"]
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
                    f"{quantidade_maxima}",
                    flush=True
                )

                if (
                    postados <
                    quantidade_maxima
                ):

                    print(
                        f"⏳ Aguardando "
                        f"{intervalo_seg}s...",
                        flush=True
                    )

                    time.sleep(
                        intervalo_seg
                    )

            else:

                print(
                    "❌ Falha ao publicar oferta.",
                    flush=True
                )

        # ----------------------------------------------------
        # FINAL
        # ----------------------------------------------------

        print(
            "\n" + "=" * 60,
            flush=True
        )

        print(
            f"🎯 FINALIZADO: "
            f"{postados} ofertas.",
            flush=True
        )

        print(
            "=" * 60,
            flush=True
        )

        enviar_mensagem(
            "✅ <b>Postagens finalizadas!</b>\n\n"
            f"🦊 Ofertas publicadas: "
            f"<b>{postados}</b>"
        )

    except Exception as erro:

        print(
            "🔥 ERRO NA TAREFA:",
            flush=True
        )

        print(
            repr(erro),
            flush=True
        )

        try:

            enviar_mensagem(
                "❌ <b>Erro durante a automação.</b>\n\n"
                f"<code>{html.escape(str(erro))}</code>"
            )

        except Exception:
            pass

    finally:

        with tarefas_lock:

            tarefas_ativas = max(
                0,
                tarefas_ativas - 1
            )


# ============================================================
# VALIDAR REQUISIÇÃO
# ============================================================

def ler_configuracao_request():

    print(
        "\n📩 POST RECEBIDO",
        flush=True
    )

    print(
        f"🌐 URL: {request.url}",
        flush=True
    )

    print(
        f"📍 ROTA: {request.path}",
        flush=True
    )

    print(
        f"📡 MÉTODO: {request.method}",
        flush=True
    )

    print(
        f"📦 Content-Type: "
        f"{request.content_type}",
        flush=True
    )

    try:

        dados = request.get_json(
            silent=True
        )

    except Exception as erro:

        print(
            f"⚠️ Erro lendo JSON: {erro}",
            flush=True
        )

        dados = None

    if not isinstance(
        dados,
        dict
    ):

        print(
            "⚠️ JSON inválido ou ausente.",
            flush=True
        )

        return None

    print(
        "✅ JSON recebido.",
        flush=True
    )

    # Não imprime initData por segurança.

    print(
        f"🔗 Link recebido: "
        f"{dados.get('link', '')}",
        flush=True
    )

    print(
        f"⏱️ Intervalo recebido: "
        f"{dados.get('intervalo', '')}",
        flush=True
    )

    print(
        f"📦 Quantidade recebida: "
        f"{dados.get('quantidade', '')}",
        flush=True
    )

    return dados


# ============================================================
# PROCESSAR CONFIGURAÇÃO
# ============================================================

def processar_configuracao():

    global tarefas_ativas

    # --------------------------------------------------------
    # CONFIGURAÇÃO DO BOT
    # --------------------------------------------------------

    erros_config = verificar_configuracao()

    if erros_config:

        print(
            "❌ Configuração inválida:",
            erros_config,
            flush=True
        )

        return jsonify({

            "ok": False,

            "erro":
                "Bot não configurado.",

            "detalhes":
                erros_config

        }), 500

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    dados = ler_configuracao_request()

    if dados is None:

        return jsonify({

            "ok": False,

            "erro":
                "JSON inválido. "
                "Envie Content-Type: application/json."

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

    link = normalizar_url(
        link
    )

    if not link:

        return jsonify({

            "ok": False,

            "erro":
                "Informe um link HTTP/HTTPS válido."

        }), 400

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

    intervalo = max(
        intervalo,
        MIN_INTERVALO
    )

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

    quantidade = max(
        1,
        min(
            quantidade,
            MAX_QUANTIDADE
        )
    )

    # --------------------------------------------------------
    # INIT DATA
    # --------------------------------------------------------

    init_data = str(
        dados.get(
            "initData",
            ""
        )
    ).strip()

    # --------------------------------------------------------
    # VALIDA TELEGRAM
    # --------------------------------------------------------

    if not validar_init_data(
        init_data
    ):

        print(
            "🚫 initData inválido.",
            flush=True
        )

        return jsonify({

            "ok": False,

            "erro":
                "Autenticação do Telegram inválida."

        }), 403

    # --------------------------------------------------------
    # EVITAR EXCESSO DE TAREFAS
    # --------------------------------------------------------

    with tarefas_lock:

        if tarefas_ativas >= 3:

            return jsonify({

                "ok": False,

                "erro":
                    "Já existem muitas automações "
                    "em execução. Aguarde."

            }), 429

        tarefas_ativas += 1

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    print(
        "\n" + "=" * 60,
        flush=True
    )

    print(
        "🚀 ORDEM ACEITA",
        flush=True
    )

    print(
        "=" * 60,
        flush=True
    )

    print(
        f"🔗 Link: {link}",
        flush=True
    )

    print(
        f"⏱️ Intervalo: {intervalo}s",
        flush=True
    )

    print(
        f"📦 Quantidade: {quantidade}",
        flush=True
    )

    print(
        "=" * 60,
        flush=True
    )

    # --------------------------------------------------------
    # AVISO
    # --------------------------------------------------------

    try:

        enviar_mensagem(

            "🚀 <b>Nova automação iniciada!</b>\n\n"

            f"🔗 Link recebido:\n"
            f"<code>{html.escape(link)}</code>\n\n"

            f"📦 Quantidade: "
            f"<b>{quantidade}</b>\n"

            f"⏱️ Intervalo: "
            f"<b>{intervalo}s</b>"

        )

    except Exception as erro:

        print(
            f"⚠️ Não foi possível enviar aviso: "
            f"{erro}",
            flush=True
        )

    # --------------------------------------------------------
    # THREAD
    # --------------------------------------------------------

    try:

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

    except Exception as erro:

        with tarefas_lock:

            tarefas_ativas = max(
                0,
                tarefas_ativas - 1
            )

        print(
            f"❌ Erro criando thread: {erro}",
            flush=True
        )

        return jsonify({

            "ok": False,

            "erro":
                "Não foi possível iniciar "
                "a automação.",

            "detalhe":
                str(erro)

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
            intervalo,

        "rota":
            "/api/configurar"

    }), 200


# ============================================================
# API PRINCIPAL
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar_api():

    try:

        return processar_configuracao()

    except Exception as erro:

        print(
            "🔥 ERRO FATAL /api/configurar:",
            repr(erro),
            flush=True
        )

        return jsonify({

            "ok": False,

            "erro":
                "Erro interno no servidor.",

            "detalhe":
                str(erro)

        }), 500


# ============================================================
# ROTA DE COMPATIBILIDADE
# ============================================================

@app.route(
    "/configurar",
    methods=["POST"]
)
def configurar_compatibilidade():

    print(
        "⚠️ POST recebido em /configurar.",
        flush=True
    )

    print(
        "➡️ Redirecionando internamente para "
        "/api/configurar.",
        flush=True
    )

    try:

        return processar_configuracao()

    except Exception as erro:

        print(
            "🔥 ERRO /configurar:",
            repr(erro),
            flush=True
        )

        return jsonify({

            "ok": False,

            "erro":
                "Erro interno no servidor.",

            "detalhe":
                str(erro)

        }), 500


# ============================================================
# GET /configurar
# ============================================================

@app.route(
    "/configurar",
    methods=["GET"]
)
def configurar_get():

    return jsonify({

        "ok": True,

        "mensagem":
            "A rota /configurar existe. "
            "Para iniciar uma automação use POST.",

        "metodo":
            "POST",

        "rota_recomendada":
            "/api/configurar",

        "servico":
            "Raposa Caçadora"

    })


# ============================================================
# ERRO 404
# ============================================================

@app.errorhandler(404)
def erro_404(erro):

    print(
        f"❌ 404: {request.method} "
        f"{request.path}",
        flush=True
    )

    return jsonify({

        "ok": False,

        "erro":
            "Rota não encontrada.",

        "detalhe":
            f"{request.method} {request.path}",

        "rotas_disponiveis": [

            "/",
            "/app",
            "/health",
            "/api/configurar",
            "/configurar"

        ]

    }), 404


# ============================================================
# ERRO 405
# ============================================================

@app.errorhandler(405)
def erro_405(erro):

    print(
        f"⚠️ 405: {request.method} "
        f"{request.path}",
        flush=True
    )

    return jsonify({

        "ok": False,

        "erro":
            "Método não permitido.",

        "detalhe":
            (
                f"A rota {request.path} "
                f"não aceita o método "
                f"{request.method}."
            ),

        "metodo_correto":
            "POST",

        "rota":
            "/api/configurar"

    }), 405


# ============================================================
# ERRO 500
# ============================================================

@app.errorhandler(500)
def erro_500(erro):

    print(
        "🔥 ERRO 500:",
        repr(erro),
        flush=True
    )

    return jsonify({

        "ok": False,

        "erro":
            "Erro interno no servidor.",

        "detalhe":
            str(erro)

    }), 500


# ============================================================
# INFORMAÇÕES DE INICIALIZAÇÃO
# ============================================================

def imprimir_configuracao():

    print(
        "\n" + "=" * 60,
        flush=True
    )

    print(
        "🦊 RAPOSA CAÇADORA",
        flush=True
    )

    print(
        "=" * 60,
        flush=True
    )

    print(
        f"📁 Pasta: {BASE_DIR}",
        flush=True
    )

    print(
        f"📄 index.html: "
        f"{'ENCONTRADO' if os.path.isfile(INDEX_FILE) else 'NÃO ENCONTRADO'}",
        flush=True
    )

    print(
        f"🤖 Telegram: "
        f"{'CONFIGURADO' if TELEGRAM_TOKEN else 'NÃO CONFIGURADO'}",
        flush=True
    )

    print(
        f"💬 CHAT_ID: "
        f"{CHAT_ID if CHAT_ID else 'NÃO CONFIGURADO'}",
        flush=True
    )

    print(
        f"🌐 PORT: {PORT}",
        flush=True
    )

    print(
        "📱 Mini App: /app",
        flush=True
    )

    print(
        "❤️ Health: /health",
        flush=True
    )

    print(
        "🚀 POST principal: /api/configurar",
        flush=True
    )

    print(
        "🔄 POST compatibilidade: /configurar",
        flush=True
    )

    print(
        "=" * 60,
        flush=True
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    imprimir_configuracao()

    app.run(

        host="0.0.0.0",

        port=PORT,

        debug=False,

        threaded=True

    )
