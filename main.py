import os
import re
import json
import time
import hashlib
import hmac
import threading

from urllib.parse import parse_qsl

import requests

from bs4 import BeautifulSoup

from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory
)

from flask_cors import CORS


# ============================================================
# RAPOSA CAÇADORA
# main.py
# ============================================================


# ============================================================
# CONFIGURAÇÕES
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


# ============================================================
# LIMITES
# ============================================================

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
# CONTROLE
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

        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36",

        "Accept-Language":
            "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",

        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"

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

        <title>Raposa Caçadora</title>

        <style>

            body {
                background: #05070a;
                color: white;
                font-family: sans-serif;
                text-align: center;
                padding-top: 50px;
            }

            h1 {
                color: #f97316;
            }

            a {
                color: #fb923c;
                text-decoration: none;
                font-weight: bold;
            }

        </style>

    </head>

    <body>

        <h1>
            🦊 Raposa Caçadora VIP
        </h1>

        <p>
            ● SERVIDOR ONLINE E OPERACIONAL
        </p>

        <p>

            <a href="/app">
                Abrir Painel Mini App
            </a>

            |

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

    if not os.path.isfile(INDEX_FILE):

        return (
            "❌ Arquivo index.html não encontrado no servidor.",
            404
        )


    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# ============================================================
# HEALTH CHECK
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
# VALIDAR TELEGRAM INIT DATA
# ============================================================

def validar_init_data(init_data):

    if not init_data:

        print(
            "❌ initData não informado."
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


        if not valido:

            print(
                "❌ initData do Telegram inválido."
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
            ) as f:

                return {
                    linha.strip()

                    for linha in f

                    if linha.strip()
                }


    except Exception as e:

        print(
            f"⚠️ Erro ao carregar histórico: {e}"
        )

        return set()


# ============================================================
# SALVAR HISTÓRICO
# ============================================================

def salvar_historico(link):

    if not link:

        return False


    try:

        with historico_lock:

            with open(
                ARQUIVO_HISTORICO,
                "a",
                encoding="utf-8"
            ) as f:

                f.write(
                    link.strip() + "\n"
                )


        return True


    except Exception as e:

        print(
            f"⚠️ Erro ao salvar histórico: {e}"
        )

        return False


# ============================================================
# ENVIAR OFERTA PARA TELEGRAM
# ============================================================

def enviar_oferta(
    foto_url,
    legenda,
    link_produto
):

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


    url = (
        f"https://api.telegram.org/"
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

        res = session.post(

            url,

            data=payload,

            timeout=HTTP_TIMEOUT

        )


        resultado = res.json()


        if not resultado.get(
            "ok",
            False
        ):

            print(
                "❌ Telegram recusou a postagem:"
            )

            print(
                resultado
            )

            return False


        return True


    except Exception as e:

        print(
            f"❌ Erro ao enviar para o Telegram: {e}"
        )

        return False


# ============================================================
# EXTRAIR DADOS DA NATURA
# ============================================================

def extrair_dados_natura(
    url_produto
):

    headers = obter_headers()


    try:

        res = session.get(

            url_produto,

            headers=headers,

            timeout=HTTP_TIMEOUT

        )


        print(
            f"🌿 Natura HTTP: {res.status_code}"
        )


        soup = BeautifulSoup(
            res.text,
            "html.parser"
        )


        # ------------------------------------------------------
        # TÍTULO
        # ------------------------------------------------------

        og_title = soup.find(
            "meta",
            property="og:title"
        )


        titulo = (

            og_title.get(
                "content",
                ""
            ).strip()

            if og_title

            else ""

        )


        if not titulo:

            h1 = soup.find("h1")

            titulo = (

                h1.get_text(
                    " ",
                    strip=True
                )

                if h1

                else
                "Oferta Exclusiva Natura!"

            )


        # ------------------------------------------------------
        # IMAGEM
        # ------------------------------------------------------

        og_image = soup.find(
            "meta",
            property="og:image"
        )


        foto_url = (

            og_image.get(
                "content",
                ""
            ).strip()

            if og_image

            else ""

        )


        if not foto_url:

            img = soup.find(
                "img",
                src=re.compile(
                    r"natura|product",
                    re.IGNORECASE
                )
            )


            if img:

                foto_url = (
                    img.get("src")
                    or img.get("data-src")
                    or ""
                )


        return (
            titulo,
            foto_url
        )


    except Exception as e:

        print(
            f"⚠️ Erro ao extrair dados da Natura: {e}"
        )

        return (
            None,
            None
        )


# ============================================================
# EXTRAIR PRODUTO MERCADO LIVRE
# ============================================================

def extrair_produto_mercado_livre(
    link
):

    headers = obter_headers()


    try:

        res = session.get(

            link,

            headers=headers,

            allow_redirects=True,

            timeout=HTTP_TIMEOUT

        )


        url_final = res.url


        soup = BeautifulSoup(
            res.text,
            "html.parser"
        )


        # ------------------------------------------------------
        # TÍTULO
        # ------------------------------------------------------

        titulo = ""


        titulo_elem = soup.find(
            "h1",
            class_=re.compile(
                r"ui-pdp-title"
            )
        )


        if titulo_elem:

            titulo = titulo_elem.get_text(
                " ",
                strip=True
            )


        if not titulo:

            meta_title = soup.find(
                "meta",
                property="og:title"
            )


            if meta_title:

                titulo = meta_title.get(
                    "content",
                    ""
                ).strip()


        if not titulo:

            titulo = (
                "Oferta Imperdível "
                "Mercado Livre!"
            )


        # ------------------------------------------------------
        # IMAGEM
        # ------------------------------------------------------

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

            foto_elem = soup.find(
                "img",
                class_=re.compile(
                    r"ui-pdp-image"
                )
            )


            if foto_elem:

                foto_url = (

                    foto_elem.get("src")

                    or

                    foto_elem.get(
                        "data-src"
                    )

                    or ""

                )


        return {

            "titulo":
                titulo,

            "foto":
                foto_url,

            "url":
                url_final

        }


    except Exception as e:

        print(
            f"⚠️ Erro ao extrair produto ML: {e}"
        )

        return None


# ============================================================
# PROCESSAR NATURA
# ============================================================

def processar_natura(
    url_vitrine
):

    print(
        "🌿 Processando Natura..."
    )


    titulo, foto_url = (
        extrair_dados_natura(
            url_vitrine
        )
    )


    if not titulo:

        print(
            "❌ Não foi possível obter o título da Natura."
        )

        return


    if not foto_url:

        print(
            "❌ Não foi possível obter a imagem da Natura."
        )

        return


    legenda = (

        f"🌿 <b>{titulo}</b>\n\n"

        f"✨ <i>Aproveite esta oferta!</i>\n\n"

        f"👉 <b>Clique abaixo para ver a oferta:</b>"

    )


    if enviar_oferta(

        foto_url,

        legenda,

        url_vitrine

    ):

        salvar_historico(
            url_vitrine
        )


        print(
            "✅ Oferta Natura postada com sucesso!"
        )

    else:

        print(
            "❌ Falha ao publicar oferta Natura."
        )


# ============================================================
# PROCESSAR MERCADO LIVRE
# ============================================================

def processar_mercado_livre(
    url_vitrine,
    quantidade_maxima,
    intervalo_seg
):

    print(
        "🛒 Processando Mercado Livre..."
    )


    headers = obter_headers()


    try:

        # ------------------------------------------------------
        # EXPANDIR LINK
        # ------------------------------------------------------

        res_redir = session.get(

            url_vitrine,

            headers=headers,

            allow_redirects=True,

            timeout=HTTP_TIMEOUT

        )


        url_final = res_redir.url


        print(
            f"🔗 Link expandido: {url_final}"
        )


    except Exception as e:

        print(
            f"❌ Erro ao expandir link ML: {e}"
        )

        return


    # ----------------------------------------------------------
    # SE FOR PRODUTO DIRETO
    # ----------------------------------------------------------

    if (
        "/p/MLB" in url_final

        or

        "produto.mercadolivre.com.br"
        in url_final

        or

        re.search(
            r"MLB-\d+",
            url_final
        )
    ):

        produto = (
            extrair_produto_mercado_livre(
                url_final
            )
        )


        if not produto:

            return


        if not produto["foto"]:

            print(
                "❌ Produto sem imagem."
            )

            return


        legenda = (

            f"🔥 <b>{produto['titulo']}</b>\n\n"

            f"⚡ <i>Aproveite esta promoção "
            f"no Mercado Livre!</i>\n\n"

            f"👉 <b>Clique abaixo para ver a oferta:</b>"

        )


        if enviar_oferta(

            produto["foto"],

            legenda,

            url_vitrine

        ):

            salvar_historico(
                url_vitrine
            )


            print(
                "✅ Produto ML postado!"
            )


        return


    # ----------------------------------------------------------
    # PÁGINA / VITRINE
    # ----------------------------------------------------------

    try:

        res = session.get(

            url_final,

            headers=headers,

            timeout=HTTP_TIMEOUT

        )


        print(
            f"🛒 Mercado Livre HTTP: {res.status_code}"
        )


        soup = BeautifulSoup(
            res.text,
            "html.parser"
        )


    except Exception as e:

        print(
            f"❌ Erro ao acessar página ML: {e}"
        )

        return


    # ----------------------------------------------------------
    # ENCONTRAR LINKS
    # ----------------------------------------------------------

    links_encontrados = []


    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a["href"]


        if any(

            p in href

            for p in [

                "produto.mercadolivre.com.br",

                "/p/MLB",

                "MLB-",

                "/sec/"

            ]

        ):

            href = href.split(
                "#"
            )[0]


            if href not in links_encontrados:

                links_encontrados.append(
                    href
                )


    # ----------------------------------------------------------
    # PRODUTO DIRETO
    # ----------------------------------------------------------

    if not links_encontrados:

        if any(

            p in url_final

            for p in [

                "produto.mercadolivre.com.br",

                "/p/MLB",

                "MLB-"

            ]

        ):

            links_encontrados.append(
                url_final
            )


    # ----------------------------------------------------------
    # HISTÓRICO
    # ----------------------------------------------------------

    historico = carregar_historico()


    postados = 0


    print(
        f"🔎 Produtos encontrados: "
        f"{len(links_encontrados)}"
    )


    # ----------------------------------------------------------
    # PROCESSAR PRODUTOS
    # ----------------------------------------------------------

    for link in links_encontrados:

        if postados >= quantidade_maxima:

            break


        if link in historico:

            print(
                "⏭️ Produto já publicado:"
                f" {link}"
            )

            continue


        produto = (
            extrair_produto_mercado_livre(
                link
            )
        )


        if not produto:

            continue


        titulo = produto["titulo"]

        foto_url = produto["foto"]


        if not foto_url:

            print(
                f"⚠️ Sem imagem: {titulo}"
            )

            continue


        legenda = (

            f"🔥 <b>{titulo}</b>\n\n"

            f"⚡ <i>Aproveite esta promoção "
            f"no Mercado Livre!</i>\n\n"

            f"👉 <b>Clique abaixo para ver a oferta:</b>"

        )


        # ------------------------------------------------------
        # PUBLICAR
        # ------------------------------------------------------

        if enviar_oferta(

            foto_url,

            legenda,

            link

        ):

            salvar_historico(
                link
            )


            postados += 1


            print(

                f"✅ [POSTADO "
                f"{postados}/{quantidade_maxima}] "
                f"{titulo[:60]}..."

            )


            # --------------------------------------------------
            # INTERVALO
            # --------------------------------------------------

            if (
                postados < quantidade_maxima
                and intervalo_seg > 0
            ):

                print(
                    f"⏳ Aguardando "
                    f"{intervalo_seg} segundos..."
                )


                time.sleep(
                    intervalo_seg
                )


    print(
        f"🏁 Processamento finalizado. "
        f"Postados: {postados}"
    )


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

        print(
            "\n"
            "========================================"
        )

        print(
            "🦊 NOVA AUTOMAÇÃO"
        )

        print(
            f"🔗 URL: {url_vitrine}"
        )

        print(
            f"📦 Quantidade: {quantidade_maxima}"
        )

        print(
            f"⏱️ Intervalo: {intervalo_seg}s"
        )

        print(
            "========================================"
        )


        # ------------------------------------------------------
        # EXP
