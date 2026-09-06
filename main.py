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


# ============================================================
# FLASK
# ============================================================

app = Flask(
    __name__,
    static_folder=BASE_DIR
)


# ============================================================
# LOG INICIAL DAS ROTAS
# ============================================================

print("=" * 70)
print("🦊 RAPOSA CAÇADORA - INICIANDO SERVIDOR")
print("=" * 70)

print(
    f"📁 BASE_DIR: {BASE_DIR}"
)

print(
    f"📄 INDEX_FILE: {INDEX_FILE}"
)

print(
    f"📄 index.html: "
    f"{'OK' if os.path.isfile(INDEX_FILE) else 'NÃO ENCONTRADO'}"
)

print(
    f"🤖 TELEGRAM_TOKEN: "
    f"{'CONFIGURADO' if TELEGRAM_TOKEN else 'NÃO CONFIGURADO'}"
)

print(
    f"💬 CHAT_ID: {CHAT_ID}"
)

print(
    f"🌐 PORTA: {PORT}"
)

print("=" * 70)


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
                max-width: 550px;
                padding: 30px;
                text-align: center;
                background: #111827;
                border-radius: 18px;
                box-shadow: 0 10px 40px rgba(0,0,0,.5);
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

            .ok {
                color: #4ade80;
            }

        </style>

    </head>

    <body>

        <div class="box">

            <h1>🦊 Raposa Caçadora</h1>

            <p class="ok">
                ✅ Servidor online
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
                    verificar
                </a>
            </p>

            <p>
                API:
                <a href="/api/configurar">
                    testar /api/configurar
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
        f"📂 Solicitação do Mini App: {INDEX_FILE}"
    )

    if not os.path.isfile(INDEX_FILE):

        print(
            "❌ index.html NÃO encontrado."
        )

        return jsonify({

            "ok": False,

            "erro":
                "index.html não encontrado.",

            "arquivo":
                INDEX_FILE

        }), 404

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


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

        "api_configurar":
            True

    }), 200


# ============================================================
# TESTE DA API
#
# IMPORTANTE:
# GET serve apenas para confirmar que a rota existe.
# O Mini App usa POST.
# ============================================================

@app.route(
    "/api/configurar",
    methods=["GET"]
)
def testar_api_configurar():

    print(
        "🧪 TESTE GET /api/configurar"
    )

    return jsonify({

        "ok":
            True,

        "rota":
            "/api/configurar",

        "metodo":
            "GET",

        "mensagem":
            "A rota da API está funcionando. "
            "Use POST para iniciar uma automação."

    }), 200


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

        print(
            "❌ initData vazio."
        )

        return False

    if not TELEGRAM_TOKEN:

        print(
            "❌ TELEGRAM_TOKEN ausente."
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
                "❌ hash não encontrado no initData."
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
            f"🔐 initData válido: {valido}"
        )

        return valido

    except Exception as e:

        print(
            f"⚠️ Erro ao validar initData: {e}"
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
            f"⚠️ Erro ao carregar histórico: {e}"
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
            f"⚠️ Erro ao salvar histórico: {e}"
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

            timeout=30

        )

        print(
            f"📡 Telegram {metodo}: "
            f"HTTP {resposta.status_code}"
        )

        resultado = resposta.json()

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

            "chat_id":
                CHAT_ID,

            "text":
                texto,

            "parse_mode":
                "HTML"

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

        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/124.0.0.0 "
                "Safari/537.36"
            ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8",

        "Accept":
            (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/avif,"
                "image/webp,*/*;q=0.8"
            ),

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache"

    }


# ============================================================
# EXPANDIR LINK
# ============================================================

def expandir_link(
    url,
    headers
):

    try:

        print(
            f"🔗 Expandindo: {url}"
        )

        resposta = requests.get(

            url,

            headers=headers,

            allow_redirects=True,

            timeout=30

        )

        print(
            f"🔗 HTTP expansão: "
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
            f"❌ Erro ao expandir URL: {e}"
        )

        return None


# ============================================================
# NORMALIZAR LINK
# ============================================================

def normalizar_link(
    link,
    base_url
):

    try:

        link = urljoin(
            base_url,
            link
        )

        link = link.strip()

        link = link.split("#")[0]

        return link

    except Exception:

        return ""


# ============================================================
# É PRODUTO MERCADO LIVRE?
# ============================================================

def parece_produto_mercado_livre(url):

    if not url:

        return False

    url_lower = url.lower()

    padroes = [

        "produto.mercadolivre.com.br",

        "mercadolivre.com.br/p/",

        "mercadolivre.com.br/mlb-",

        "mercadolivre.com.br/mlb",

        "/p/mlb",

        "/mlb-"

    ]

    return any(
        padrao in url_lower
        for padrao in padroes
    )


# ============================================================
# EXTRAIR ID MLB
# ============================================================

def extrair_id_mlb(url):

    if not url:

        return ""

    padroes = [

        r"MLB[-_]?(\d+)",

        r"mlb[-_]?(\d+)"

    ]

    for padrao in padroes:

        encontrado = re.search(
            padrao,
            url
        )

        if encontrado:

            return (
                "MLB-"
                + encontrado.group(1)
            )

    return ""


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

        resposta = requests.get(

            url_vitrine,

            headers=headers,

            timeout=30,

            allow_redirects=True

        )

        print(
            f"🔎 HTTP vitrine: "
            f"{resposta.status_code}"
        )

        print(
            f"🔎 URL final vitrine: "
            f"{resposta.url}"
        )

        resposta.raise_for_status()

    except Exception as e:

        print(
            f"❌ Erro ao acessar vitrine: {e}"
        )

        return []


    html_pagina = resposta.text

    print(
        f"📄 Tamanho HTML: "
        f"{len(html_pagina)} caracteres"
    )


    soup = BeautifulSoup(
        html_pagina,
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

        href = normalizar_link(
            href,
            resposta.url
        )

        if parece_produto_mercado_livre(
            href
        ):

            links.append(
                href
            )


    # --------------------------------------------------------
    # META / JSON / HTML
    #
    # Algumas páginas modernas do Mercado Livre
    # colocam os links dentro de scripts.
    # --------------------------------------------------------

    padroes_url = [

        r'https?://[^"\']*mercadolivre\.com\.br/MLB[-_]\d+[^"\']*',

        r'https?://[^"\']*mercadolivre\.com\.br/p/MLB[-_]\d+[^"\']*',

        r'https?://[^"\']*mercadolivre\.com\.br/[^"\']*MLB[-_]\d+[^"\']*',

        r'//[^"\']*mercadolivre\.com\.br/MLB[-_]\d+[^"\']*',

        r'//[^"\']*mercadolivre\.com\.br/p/MLB[-_]\d+[^"\']*'

    ]


    for padrao in padroes_url:

        encontrados = re.findall(
            padrao,
            html_pagina,
            flags=re.IGNORECASE
        )

        for encontrado in encontrados:

            link = encontrado

            if link.startswith("//"):

                link = "https:" + link

            link = normalizar_link(
                link,
                resposta.url
            )

            if parece_produto_mercado_livre(
                link
            ):

                links.append(
                    link
                )


    # --------------------------------------------------------
    # REMOVER DUPLICADOS
    # --------------------------------------------------------

    links_limpos = []

    vistos = set()

    for link in links:

        link_sem_query = link.split("?")[0]

        if link_sem_query in vistos:

            continue

        vistos.add(
            link_sem_query
        )

        links_limpos.append(
            link
        )


    print(
        f"📦 {len(links_limpos)} "
        f"produtos encontrados."
    )


    for i, link in enumerate(
        links_limpos[:20],
        start=1
    ):

        print(
            f"   {i}. {link}"
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
        f"🔎 Extraindo produto: {link}"
    )

    try:

        resposta = requests.get(

            link,

            headers=headers,

            allow_redirects=True,

            timeout=30

        )

        print(
            f"📄 Produto HTTP: "
            f"{resposta.status_code}"
        )

        print(
            f"📄 URL produto final: "
            f"{resposta.url}"
        )

        resposta.raise_for_status()

    except Exception as e:

        print(
            f"⚠️ Erro acessando produto: {e}"
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


    if not foto_url:

        elemento_img = soup.find(
            "img",
            class_="ui-pdp-image"
        )

        if elemento_img:

            foto_url = (

                elemento_img.get("src")

                or

                elemento_img.get(
                    "data-src"
                )

                or

                ""

            )


    # ========================================================
    # IMAGENS EM META
    # ========================================================

    if not foto_url:

        for meta in soup.find_all(
            "meta"
        ):

            propriedade = (
                meta.get("property")
                or meta.get("name")
                or ""
            ).lower()

            if propriedade in (
                "og:image",
                "twitter:image"
            ):

                candidato = (
                    meta.get(
                        "content",
                        ""
                    )
                    .strip()
                )

                if candidato.startswith(
                    "http"
                ):

                    foto_url = candidato

                    break


    # ========================================================
    # QUALQUER IMG
    # ========================================================

    if not foto_url:

        for img in soup.find_all(
            "img"
        ):

            candidato = (

                img.get("src")

                or

                img.get(
                    "data-src"
                )

                or

                img.get(
                    "data-lazy-src"
                )

                or

                ""

            )


            if candidato.startswith(
                "http"
            ):

                foto_url = candidato

                break


    # ========================================================
    # LIMPAR TÍTULO
    # ========================================================

    titulo = html.escape(
        titulo
    )


    # ========================================================
    # SEM FOTO
    # ========================================================

    if not foto_url:

        print(
            "⚠️ Produto sem imagem."
        )

        return None


    return {

        "titulo":
            titulo,

        "foto_url":
            foto_url,

        "link":
            resposta.url,

        "id":
            extrair_id_mlb(
                resposta.url
            )

    }


# ============================================================
# PROCESSAR E POSTAR VITRINE
# ============================================================

def processar_e_postar_vitrine(
    url_vitrine,
    quantidade_maxima,
    intervalo_seg
):

    headers = obter_headers()


    print(
        "\n" + "=" * 70
    )

    print(
        "🦊 NOVA TAREFA"
    )

    print(
        "=" * 70
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

    print(
        "=" * 70
    )


    # ========================================================
    # EXPANDIR
    # ========================================================

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


    # ========================================================
    # IDENTIFICAR PRODUTO OU VITRINE
    # ========================================================

    if parece_produto_mercado_livre(
        url_final
    ):

        print(
            "🎯 Link identificado como PRODUTO."
        )

        links_produtos = [
            url_final
        ]

    else:

        print(
            "🏪 Link identificado como VITRINE/LISTA."
        )

        links_produtos = (
            encontrar_links_produtos(
                url_final,
                headers
            )
        )


    # ========================================================
    # NENHUM PRODUTO
    # ========================================================

    if not links_produtos:

        enviar_mensagem(

            "⚠️ <b>Nenhum produto encontrado.</b>\n\n"

            "O link foi acessado, porém não "
            "foi possível encontrar produtos "
            "na página.\n\n"

            "Isso pode acontecer quando o Mercado "
            "Livre carrega os produtos dinamicamente "
            "ou quando a vitrine não está pública."

        )

        return


    # ========================================================
    # HISTÓRICO
    # ========================================================

    historico = carregar_historico()


    postados = 0


    # ========================================================
    # LOOP
    # ========================================================

    for link in links_produtos:


        if postados >= quantidade_maxima:

            break


        if not link:

            continue


        link = link.strip()


        # ----------------------------------------------------
        # HISTÓRICO
        # ----------------------------------------------------

        if link in historico:

            print(
                f"⏭️ Já postado: {link}"
            )

            continue


        # ----------------------------------------------------
        # EXTRAIR
        # ----------------------------------------------------

        produto = extrair_produto(

            link,

            headers

        )


        if not produto:

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

            f"🛒 <b>Oferta encontrada pela "
            f"Raposa Caçadora!</b>\n\n"

            f"👇 <b>Confira o produto:</b>"

        )


        # ----------------------------------------------------
        # ENVIAR
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


            # Também guarda o link original
            # caso seja diferente da URL final.

            if link != link_produto:

                salvar_historico(
                    link
                )

                historico.add(
                    link
                )


            postados += 1


            print(
                f"✅ POSTADO "
                f"{postados}/{quantidade_maxima}"
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
                "❌ Falha ao publicar."
            )


    # ========================================================
    # FINAL
    # ========================================================

    print(
        "\n" + "=" * 70
    )

    print(
        f"🎯 FINALIZADO: "
        f"{postados} ofertas."
    )

    print(
        "=" * 70
    )


    if postados > 0:

        enviar_mensagem(

            "✅ <b>Postagens finalizadas!</b>\n\n"

            f"🦊 Ofertas publicadas: "
            f"<b>{postados}</b>"

        )

    else:

        enviar_mensagem(

            "⚠️ <b>Automação finalizada.</b>\n\n"

            "Nenhuma nova oferta foi publicada."

        )


# ============================================================
# API /api/configurar
#
# POST usado pelo Mini App
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    print(
        "\n" + "=" * 70
    )

    print(
        "📩 POST /api/configurar RECEBIDO"
    )

    print(
        "=" * 70
    )


    # ========================================================
    # CONFIGURAÇÃO
    # ========================================================

    if not verificar_configuracao():

        print(
            "❌ Bot não configurado."
        )

        return jsonify({

            "ok":
                False,

            "erro":
                "Bot não configurado. "
                "Verifique TELEGRAM_TOKEN e CHAT_ID."

        }), 500


    # ========================================================
    # JSON
    # ========================================================

    dados = request.get_json(
        silent=True
    )


    print(
        f"📦 Dados recebidos: "
        f"{bool(dados)}"
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
                "Dados inválidos. "
                "Envie JSON."

        }), 400


    # ========================================================
    # LINK
    # ========================================================

    link = str(

        dados.get(
            "link",
            ""
        )

    ).strip()


    # ========================================================
    # INIT DATA
    # ========================================================

    init_data = str(

        dados.get(
            "initData",
            ""
        )

    )


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


    print(
        f"🔗 Link: {link}"
    )

    print(
        f"⏱️ Intervalo recebido: "
        f"{intervalo}"
    )

    print(
        f"📦 Quantidade recebida: "
        f"{quantidade}"
    )

    print(
        f"🔐 initData recebido: "
        f"{'SIM' if init_data else 'NÃO'}"
    )


    # ========================================================
    # INIT DATA
    # ========================================================

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


    # ========================================================
    # LINK
    # ========================================================

    if not link:

        print(
            "❌ Link vazio."
        )

        return jsonify({

            "ok":
                False,

            "erro":
                "Informe o link da vitrine ou do produto."

        }), 400


    # ========================================================
    # VALIDAR URL
    # ========================================================

    try:

        parsed = urlparse(
            link
        )

        if parsed.scheme not in (
            "http",
            "https"
        ):

            return jsonify({

                "ok":
                    False,

                "erro":
                    "O link precisa começar com "
                    "http:// ou https://."

            }), 400

    except Exception:

        return jsonify({

            "ok":
                False,

            "erro":
                "Link inválido."

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


    # ========================================================
    # AVISO NO CANAL
    # ========================================================

    aviso_ok = enviar_mensagem(

        "🚀 <b>Nova automação iniciada!</b>\n\n"

        f"📦 Quantidade: "
        f"<b>{quantidade}</b>\n"

        f"⏱️ Intervalo: "
        f"<b>{intervalo}s</b>\n\n"

        "🔎 O sistema está pesquisando "
        "a vitrine/produto..."

    )


    print(
        f"📢 Aviso Telegram enviado: "
        f"{aviso_ok}"
    )


    # ========================================================
    # THREAD
    # ========================================================

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


        print(
            f"🧵 Thread iniciada: "
            f"{thread.name}"
        )


    except Exception as e:

        print(
            f"❌ Erro ao iniciar thread: {e}"
        )

        return jsonify({

            "ok":
                False,

            "erro":
                "Não foi possível iniciar "
                "o processamento.",

            "detalhe":
                str(e)

        }), 500


    # ========================================================
    # RESPOSTA
    # ========================================================

    resposta = {

        "ok":
            True,

        "mensagem":
            "Postagens iniciadas.",

        "quantidade":
            quantidade,

        "intervalo":
            intervalo

    }


    print(
        f"✅ Respondendo ao Mini App: "
        f"{resposta}"
    )


    return jsonify(
        resposta
    ), 200


# ============================================================
# ERRO 404
# ============================================================

@app.errorhandler(404)
def erro_404(e):

    print(
        f"❌ 404: {request.method} {request.path}"
    )

    return jsonify({

        "ok":
            False,

        "erro":
            "Rota não encontrada.",

        "detalhe":
            f"{request.method} {request.path}",

        "rotas_disponiveis": [

            "/",

            "/app",

            "/health",

            "/api/configurar"

        ]

    }), 404


# ============================================================
# ERRO 405
# ============================================================

@app.errorhandler(405)
def erro_405(e):

    print(
        f"❌ 405: {request.method} {request.path}"
    )

    return jsonify({

        "ok":
            False,

        "erro":
            "Método HTTP não permitido.",

        "detalhe":
            f"{request.method} {request.path}"

    }), 405


# ============================================================
# ERRO 500
# ============================================================

@app.errorhandler(500)
def erro_500(e):

    print(
        f"❌ 500: {e}"
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
# LISTAR ROTAS
# ============================================================

def mostrar_rotas():

    print(
        "\n📋 ROTAS REGISTRADAS:"
    )

    for regra in app.url_map.iter_rules():

        print(
            f"   {sorted(regra.methods)} "
            f"{regra}"
        )

    print()


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    mostrar_rotas()


    print(
        "=" * 70
    )

    print(
        "🦊 RAPOSA CAÇADORA"
    )

    print(
        "=" * 70
    )

    print(
        f"📁 Pasta: {BASE_DIR}"
    )

    print(
        f"📄 index.html: "
        f"{'ENCONTRADO' if os.path.isfile(INDEX_FILE) else 'NÃO ENCONTRADO'}"
    )

    print(
        f"🤖 Telegram: "
        f"{'CONFIGURADO' if TELEGRAM_TOKEN else 'NÃO CONFIGURADO'}"
    )

    print(
        f"💬 CHAT_ID: {CHAT_ID}"
    )

    print(
        f"🌐 Porta: {PORT}"
    )

    print(
        "🌐 API: /api/configurar"
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
        "=" * 70
    )


    app.run(

        host="0.0.0.0",

        port=PORT,

        debug=False

    )
