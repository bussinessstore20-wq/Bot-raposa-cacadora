import os
import json
import time
import html
import threading
import hashlib
import hmac

from urllib.parse import parse_qsl, urljoin

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory

try:
    from flask_cors import CORS
except ImportError:
    CORS = None


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

if CORS:

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": "*"
            },
            r"/configurar": {
                "origins": "*"
            }
        },
        methods=[
            "GET",
            "POST",
            "OPTIONS"
        ],
        allow_headers=[
            "Content-Type",
            "Authorization"
        ]
    )


# ============================================================
# HEADERS CORS MANUAIS
# ============================================================

@app.after_request
def adicionar_cors(response):

    response.headers[
        "Access-Control-Allow-Origin"
    ] = "*"

    response.headers[
        "Access-Control-Allow-Methods"
    ] = "GET, POST, OPTIONS"

    response.headers[
        "Access-Control-Allow-Headers"
    ] = "Content-Type, Authorization"

    return response


# ============================================================
# PÁGINA INICIAL
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

        </div>

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

    print(
        f"📂 Procurando index.html em: {INDEX_FILE}"
    )

    if not os.path.isfile(INDEX_FILE):

        print(
            "❌ index.html NÃO encontrado."
        )

        try:

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

        return """
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
        """, 404

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

@app.route(
    "/health",
    methods=["GET"]
)
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
# VALIDAR INIT DATA DO TELEGRAM
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

        return valido

    except Exception as erro:

        print(
            f"⚠️ Erro validando initData: {erro}"
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

    except Exception as erro:

        print(
            f"⚠️ Erro carregando histórico: {erro}"
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

    except Exception as erro:

        print(
            f"⚠️ Erro salvando histórico: {erro}"
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
            f"📡 Telegram HTTP: "
            f"{resposta.status_code}"
        )

        resultado = resposta.json()

        if not resultado.get(
            "ok",
            False
        ):

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
                "HTML",

            "disable_web_page_preview":
                False
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
                "Chrome/131.0.0.0 "
                "Safari/537.36"
            ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8",

        "Accept":
            (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "image/avif,"
                "image/webp,"
                "*/*;q=0.8"
            ),

        "Connection":
            "keep-alive"

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

        resposta.raise_for_status()

        print(
            f"🔗 URL final: {resposta.url}"
        )

        return resposta.url

    except Exception as erro:

        print(
            f"❌ Erro expandindo URL: {erro}"
        )

        return None


# ============================================================
# IDENTIFICAR LINK DE PRODUTO
# ============================================================

def eh_link_produto(
    url
):

    url_lower = (
        url or ""
    ).lower()

    padroes = [

        "produto.mercadolivre.com.br",

        "/p/mlb",

        "mlb-",

        "mercadolivre.com.br/p/"

    ]

    return any(
        padrao in url_lower
        for padrao in padroes
    )


# ============================================================
# EXTRAIR ID DO PRODUTO
# ============================================================

def extrair_id_produto(
    url
):

    if not url:

        return ""

    texto = url.upper()

    partes = texto.replace(
        "?",
        "/"
    ).split("/")

    for parte in partes:

        if parte.startswith(
            "MLB-"
        ):

            return parte.split(
                "-"
            )[0] + "-" + parte.split(
                "-"
            )[1]

        if parte.startswith(
            "MLB"
        ) and len(parte) >= 10:

            return parte

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
            timeout=30
        )

        resposta.raise_for_status()

    except Exception as erro:

        print(
            f"❌ Erro acessando vitrine: {erro}"
        )

        return []

    html_pagina = resposta.text

    print(
        f"📄 Página recebida: "
        f"{len(html_pagina)} bytes"
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

        href = urljoin(
            resposta.url,
            href
        )

        href = href.split(
            "#"
        )[0]

        href_lower = href.lower()

        if (

            "produto.mercadolivre.com.br"
            in href_lower

            or "/p/mlb"
            in href_lower

            or "mlb-"
            in href_lower

        ):

            links.append(
                href
            )

    # --------------------------------------------------------
    # META / CANONICAL
    # --------------------------------------------------------

    for tag in soup.find_all(
        [
            "link",
            "meta"
        ]
    ):

        valor = (
            tag.get("href")
            or tag.get("content")
            or ""
        )

        if not valor:

            continue

        valor = urljoin(
            resposta.url,
            valor
        )

        valor_lower = valor.lower()

        if (

            "produto.mercadolivre.com.br"
            in valor_lower

            or "/p/mlb"
            in valor_lower

            or "mlb-"
            in valor_lower

        ):

            links.append(
                valor
            )

    # --------------------------------------------------------
    # URLS ENCONTRADAS NO HTML
    # --------------------------------------------------------

    import re

    padroes_url = [

        r'https?://[^\s"\'<>]+',

        r'/p/MLB[0-9A-Za-z_-]+',

        r'https?://produto\.mercadolivre\.com\.br/[^\s"\'<>]+'

    ]

    for padrao in padroes_url:

        encontrados = re.findall(
            padrao,
            html_pagina,
            flags=re.IGNORECASE
        )

        for encontrado in encontrados:

            encontrado = (
                encontrado
                .replace(
                    "\\/",
                    "/"
                )
            )

            encontrado = urljoin(
                resposta.url,
                encontrado
            )

            encontrado = encontrado.split(
                "#"
            )[0]

            if eh_link_produto(
                encontrado
            ):

                links.append(
                    encontrado
                )

    # --------------------------------------------------------
    # LIMPAR
    # --------------------------------------------------------

    links_limpos = []

    vistos = set()

    for link in links:

        link = link.strip()

        if not link:

            continue

        if link in vistos:

            continue

        vistos.add(
            link
        )

        links_limpos.append(
            link
        )

    print(
        f"📦 {len(links_limpos)} "
        f"produtos encontrados."
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

        resposta.raise_for_status()

    except Exception as erro:

        print(
            f"⚠️ Erro acessando produto: {erro}"
        )

        return None

    soup = BeautifulSoup(
        resposta.text,
        "html.parser"
    )

    # --------------------------------------------------------
    # URL FINAL
    # --------------------------------------------------------

    link_final = resposta.url

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
                "name":
                    "title"
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
    # IMAGEM OG
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
    # IMAGEM TWITTER
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
    # IMAGEM PDP
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
                or elemento_img.get(
                    "data-src"
                )
                or ""
            )

    # --------------------------------------------------------
    # QUALQUER IMAGEM
    # --------------------------------------------------------

    if not foto_url:

        for img in soup.find_all(
            "img"
        ):

            candidato = (

                img.get(
                    "src"
                )

                or img.get(
                    "data-src"
                )

                or img.get(
                    "data-lazy"
                )

                or ""

            )

            if candidato.startswith(
                "http"
            ):

                foto_url = candidato

                break

    # --------------------------------------------------------
    # VALIDAR FOTO
    # --------------------------------------------------------

    if not foto_url:

        print(
            "⚠️ Produto sem imagem."
        )

        return None

    # --------------------------------------------------------
    # LIMPAR URL DA IMAGEM
    # --------------------------------------------------------

    foto_url = foto_url.strip()

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

    # --------------------------------------------------------
    # EXPANDIR
    # --------------------------------------------------------

    url_final = expandir_link(
        url_vitrine,
        headers
    )

    if not url_final:

        enviar_mensagem(
            "❌ <b>Não foi possível acessar "
            "o link informado.</b>\n\n"
            "Verifique se o link está correto."
        )

        return

    # --------------------------------------------------------
    # IDENTIFICAR PRODUTO OU VITRINE
    # --------------------------------------------------------

    if eh_link_produto(
        url_final
    ):

        print(
            "🛒 Link identificado "
            "como produto."
        )

        links_produtos = [
            url_final
        ]

    else:

        print(
            "🏪 Link identificado "
            "como vitrine/lista."
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

        enviar_mensagem(

            "⚠️ <b>Nenhum produto encontrado.</b>\n\n"

            "O link foi acessado, mas não "
            "foi possível encontrar produtos "
            "publicáveis nessa página.\n\n"

            "Isso pode acontecer quando o "
            "Mercado Livre entrega a vitrine "
            "de forma dinâmica."
        )

        return

    # --------------------------------------------------------
    # HISTÓRICO
    # --------------------------------------------------------

    historico = carregar_historico()

    postados = 0

    tentados = 0

    # --------------------------------------------------------
    # LOOP
    # --------------------------------------------------------

    for link in links_produtos:

        if postados >= quantidade_maxima:

            break

        if not link:

            continue

        link = link.strip()

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
            f"oferta por tempo limitado!</i>\n\n"

            f"🛒 <b>Mercado Livre</b>\n\n"

            f"👇 <b>CLIQUE NO BOTÃO "
            f"PARA VER A OFERTA</b>"

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
                "❌ Falha ao publicar "
                "produto."
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
        "=" * 60
    )

    enviar_mensagem(

        "✅ <b>Postagens finalizadas!</b>\n\n"

        f"🦊 Ofertas publicadas: "
        f"<b>{postados}</b>\n\n"

        f"🔎 Produtos analisados: "
        f"<b>{tentados}</b>"

    )


# ============================================================
# RECEBER DADOS
# ============================================================

def obter_dados_requisicao():

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    dados = request.get_json(
        silent=True
    )

    if isinstance(
        dados,
        dict
    ):

        return dados

    # --------------------------------------------------------
    # FORM
    # --------------------------------------------------------

    if request.form:

        return request.form.to_dict()

    # --------------------------------------------------------
    # VAZIO
    # --------------------------------------------------------

    return {}


# ============================================================
# ROTA OPTIONS
# ============================================================

@app.route(
    "/api/configurar",
    methods=["OPTIONS"]
)
def configurar_options():

    resposta = jsonify({
        "ok": True,
        "metodo": "OPTIONS",
        "mensagem":
            "Pré-verificação CORS aceita."
    })

    resposta.status_code = 200

    return resposta


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
        "📩 POST /api/configurar"
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
    # DADOS
    # --------------------------------------------------------

    dados = obter_dados_requisicao()

    print(
        f"📦 Dados recebidos: "
        f"{list(dados.keys())}"
    )

    if not isinstance(
        dados,
        dict
    ):

        return jsonify({

            "ok":
                False,

            "erro":
                "Dados inválidos."

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
        "✅ initData válido."
    )

    # --------------------------------------------------------
    # VALIDAR LINK
    # --------------------------------------------------------

    if not link:

        return jsonify({

            "ok":
                False,

            "erro":
                "Informe o link da vitrine ou produto."

        }), 400

    # --------------------------------------------------------
    # VALIDAR HTTP
    # --------------------------------------------------------

    if not (
        link.startswith(
            "http://"
        )
        or
        link.startswith(
            "https://"
        )
    ):

        return jsonify({

            "ok":
                False,

            "erro":
                "Informe uma URL válida."

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

    aviso_enviado = enviar_mensagem(

        "🚀 <b>Nova automação iniciada!</b>\n\n"

        f"📦 Quantidade: "
        f"<b>{quantidade}</b>\n"

        f"⏱️ Intervalo: "
        f"<b>{intervalo}s</b>\n\n"

        "🔎 O sistema está pesquisando "
        "os produtos..."

    )

    print(
        f"📨 Aviso enviado: "
        f"{aviso_enviado}"
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

        print(
            "✅ Thread da automação iniciada."
        )

    except Exception as erro:

        print(
            f"❌ Erro iniciando thread: {erro}"
        )

        return jsonify({

            "ok":
                False,

            "erro":
                "Não foi possível iniciar a automação.",

            "detalhe":
                str(erro)

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

        "quantidade":
            quantidade,

        "intervalo":
            intervalo

    }), 200


# ============================================================
# ROTA /CONFIGURAR
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
# POST /CONFIGURAR
# ============================================================

@app.route(
    "/configurar",
    methods=["POST"]
)
def configurar_alias():

    print(
        "🔄 POST /configurar recebido."
    )

    return configurar()


# ============================================================
# 404 PERSONALIZADO
# ============================================================

@app.errorhandler(404)
def erro_404(erro):

    print(
        f"❌ Rota não encontrada: "
        f"{request.method} "
        f"{request.path}"
    )

    return jsonify({

        "ok":
            False,

        "erro":
            "Rota não encontrada.",

        "rota":
            request.path,

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


# ============================================================
# 405 PERSONALIZADO
# ============================================================

@app.errorhandler(405)
def erro_405(erro):

    print(
        f"⚠️ Método não permitido: "
        f"{request.method} "
        f"{request.path}"
    )

    return jsonify({

        "ok":
            False,

        "erro":
            "Método não permitido.",

        "rota":
            request.path,

        "metodo":
            request.method,

        "metodo_correto":
            "POST"

        if request.path
        in [
            "/api/configurar",
            "/configurar"
        ]

        else "GET"

    }), 405


# ============================================================
# ERRO INTERNO
# ============================================================

@app.errorhandler(500)
def erro_500(erro):

    print(
        f"❌ ERRO 500: {erro}"
    )

    return jsonify({

        "ok":
            False,

        "erro":
            "Erro interno no servidor.",

        "detalhe":
            str(erro)

    }), 500


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

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

    if CHAT_ID:

        print(
            f"💬 CHAT_ID: {CHAT_ID}"
        )

    else:

        print(
            "❌ CHAT_ID não configurado."
        )

    if WEBAPP_URL:

        print(
            f"🌐 WEBAPP_URL: {WEBAPP_URL}"
        )

        print(
            f"📱 Mini App: "
            f"{WEBAPP_URL}/app"
        )

    else:

        print(
            "⚠️ WEBAPP_URL não configurada."
        )

    print(
        f"🌐 Porta: {PORT}"
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

        host=
            "0.0.0.0",

        port=
            PORT,

        debug=
            False

    )
