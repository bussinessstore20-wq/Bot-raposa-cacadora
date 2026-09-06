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

# Tempo máximo para uma tarefa de scraping
REQUEST_TIMEOUT = 30


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
        "Chrome/120.0.0.0 "
        "Safari/537.36"
    ),
    "Accept-Language":
        "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept":
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8",
})


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
                max-width: 500px;
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

@app.route("/app", methods=["GET"])
def mini_app():

    print(
        f"📂 Procurando index.html em: {INDEX_FILE}"
    )

    if not os.path.isfile(INDEX_FILE):

        print(
            "❌ index.html NÃO encontrado."
        )

        print(
            f"📁 BASE_DIR: {BASE_DIR}"
        )

        try:

            print(
                "📄 Arquivos encontrados:"
            )

            for arquivo in os.listdir(BASE_DIR):

                print(
                    f"   - {arquivo}"
                )

        except Exception as e:

            print(
                f"⚠️ Não foi possível listar arquivos: {e}"
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
                O arquivo <b>index.html</b>
                não está junto do main.py.
            </p>

            <p>
                Coloque os dois arquivos na mesma pasta.
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

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "ok": True,
        "servico": "Raposa Caçadora",
        "status": "online",
        "mini_app": os.path.isfile(INDEX_FILE),
        "telegram_configurado": bool(
            TELEGRAM_TOKEN
        ),
        "chat_configurado": bool(
            CHAT_ID
        ),
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
            "❌ ERRO: TELEGRAM_TOKEN não configurado."
        )

        return False

    if not CHAT_ID:

        print(
            "❌ ERRO: CHAT_ID não configurado."
        )

        return False

    return True


# ============================================================
# VALIDAR INIT DATA DO TELEGRAM
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
            TELEGRAM_TOKEN.encode("utf-8"),
            hashlib.sha256
        ).digest()

        calculado = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        resultado = hmac.compare_digest(
            calculado,
            hash_recebido
        )

        print(
            f"🔐 Validação initData: "
            f"{'OK' if resultado else 'INVÁLIDA'}"
        )

        return resultado

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
            timeout=20
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
            "chat_id": CHAT_ID,
            "text": texto,
            "parse_mode": "HTML"
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
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
    }


# ============================================================
# NORMALIZAR LINK
# ============================================================

def normalizar_link(url):

    if not url:

        return ""

    url = str(url).strip()

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

    try:

        url = normalizar_link(
            url
        )

        print(
            f"🔗 Expandindo: {url}"
        )

        resposta = session.get(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT
        )

        resposta.raise_for_status()

        print(
            f"🔗 URL final: {resposta.url}"
        )

        return resposta.url

    except Exception as e:

        print(
            f"❌ Erro ao expandir URL: {e}"
        )

        return None


# ============================================================
# VERIFICAR SE É PRODUTO
# ============================================================

def parece_produto_mercado_livre(url):

    if not url:

        return False

    url_lower = url.lower()

    padroes = [
        "produto.mercadolivre.com.br",
        "produto.mercadolivre.com",
        "/p/mlb",
        "/p/MLB".lower(),
        "mlb-"
    ]

    return any(
        padrao in url_lower
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

    try:

        resposta = session.get(
            url_vitrine,
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )

        resposta.raise_for_status()

    except Exception as e:

        print(
            f"❌ Erro ao acessar vitrine: {e}"
        )

        return []

    print(
        f"🌐 Página retornou HTTP "
        f"{resposta.status_code}"
    )

    soup = BeautifulSoup(
        resposta.text,
        "html.parser"
    )

    links = []

    padroes = [
        "produto.mercadolivre.com.br",
        "produto.mercadolivre.com",
        "/p/mlb",
        "mlb-"
    ]

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
            url_vitrine,
            href
        )

        href = href.split(
            "#"
        )[0]

        href = href.strip()

        href_lower = href.lower()

        if any(
            padrao in href_lower
            for padrao in padroes
        ):

            links.append(
                href
            )

    # --------------------------------------------------------
    # LINKS EM TAGS COM DATA-HREF
    # --------------------------------------------------------

    for elemento in soup.find_all():

        for atributo in [
            "data-href",
            "data-url",
            "data-link"
        ]:

            valor = elemento.get(
                atributo
            )

            if not valor:

                continue

            valor = str(
                valor
            ).strip()

            valor = urljoin(
                url_vitrine,
                valor
            )

            valor = valor.split(
                "#"
            )[0]

            valor_lower = valor.lower()

            if any(
                padrao in valor_lower
                for padrao in padroes
            ):

                links.append(
                    valor
                )

    # --------------------------------------------------------
    # REMOVER DUPLICADOS
    # --------------------------------------------------------

    links = list(
        dict.fromkeys(
            links
        )
    )

    print(
        f"📦 {len(links)} produtos encontrados."
    )

    # --------------------------------------------------------
    # DEBUG
    # --------------------------------------------------------

    if links:

        print(
            "🔎 Primeiros links encontrados:"
        )

        for link in links[:10]:

            print(
                f"   • {link}"
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
        f"🔎 Processando produto: {link}"
    )

    try:

        resposta = session.get(
            link,
            headers=headers,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT
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

        elemento_title = soup.find(
            "title"
        )

        if elemento_title:

            titulo = elemento_title.get_text(
                " ",
                strip=True
            )

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
    # IMAGEM DO PRODUTO
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
    # OUTRAS IMAGENS
    # --------------------------------------------------------

    if not foto_url:

        for img in soup.find_all(
            "img"
        ):

            candidato = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy-src")
                or ""
            )

            if candidato.startswith(
                "http"
            ):

                foto_url = candidato

                break

    # --------------------------------------------------------
    # NORMALIZA IMAGEM
    # --------------------------------------------------------

    if foto_url:

        foto_url = urljoin(
            link_final,
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

    titulo = " ".join(
        titulo.split()
    ).strip()

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
        f"📦 Quantidade: {quantidade_maxima}"
    )

    print(
        f"⏱️ Intervalo: {intervalo_seg}s"
    )

    print(
        "=" * 60
    )

    try:

        # ----------------------------------------------------
        # EXPANDIR
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # IDENTIFICAR PRODUTO OU VITRINE
        # ----------------------------------------------------

        if parece_produto_mercado_livre(
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

            enviar_mensagem(
                "⚠️ <b>Nenhum produto encontrado.</b>\n\n"
                "O link foi acessado, mas não foi "
                "possível localizar produtos na página."
            )

            return

        # ----------------------------------------------------
        # HISTÓRICO
        # ----------------------------------------------------

        historico = carregar_historico()

        postados = 0

        encontrados = len(
            links_produtos
        )

        print(
            f"📦 Produtos disponíveis: {encontrados}"
        )

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
                    f"⏭️ Já postado: {link}"
                )

                continue

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
            "=" * 60
        )

        enviar_mensagem(
            "✅ <b>Postagens finalizadas!</b>\n\n"
            f"🦊 Ofertas publicadas: "
            f"<b>{postados}</b>"
        )

    except Exception as e:

        print(
            "❌ ERRO GERAL NA TAREFA:"
        )

        print(
            repr(e)
        )

        try:

            enviar_mensagem(
                "❌ <b>Erro durante o processamento.</b>\n\n"
                f"<code>{html.escape(str(e))}</code>"
            )

        except Exception:

            pass


# ============================================================
# PROCESSAR DADOS DA API
# ============================================================

def processar_configuracao():

    # --------------------------------------------------------
    # CONFIGURAÇÃO DO BOT
    # --------------------------------------------------------

    if not verificar_configuracao():

        return jsonify({
            "ok": False,
            "erro":
                "Bot não configurado."
        }), 500

    # --------------------------------------------------------
    # LER JSON
    # --------------------------------------------------------

    dados = request.get_json(
        silent=True
    )

    # --------------------------------------------------------
    # FALLBACK PARA FORM DATA
    # --------------------------------------------------------

    if dados is None:

        dados = {}

        try:

            dados.update(
                request.form.to_dict()
            )

        except Exception:

            pass

    if not isinstance(
        dados,
        dict
    ):

        return jsonify({
            "ok": False,
            "erro":
                "Dados inválidos."
        }), 400

    print(
        "\n📩 Dados recebidos:"
    )

    print(
        json.dumps(
            {
                k:
                    (
                        "***"
                        if k == "initData"
                        else v
                    )
                for k, v in dados.items()
            },
            ensure_ascii=False
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

    if not link:

        return jsonify({
            "ok": False,
            "erro":
                "Informe o link da vitrine."
        }), 400

    link = normalizar_link(
        link
    )

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
            "ok": False,
            "erro":
                "Autenticação do Telegram inválida."
        }), 403

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
        "📩 ORDEM RECEBIDA"
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
    # AVISO
    # --------------------------------------------------------

    aviso_enviado = enviar_mensagem(
        "🚀 <b>Nova automação iniciada!</b>\n\n"
        f"📦 Quantidade: <b>{quantidade}</b>\n"
        f"⏱️ Intervalo: <b>{intervalo}s</b>"
    )

    print(
        f"📨 Aviso Telegram: "
        f"{'OK' if aviso_enviado else 'FALHOU'}"
    )

    # --------------------------------------------------------
    # THREAD
    # --------------------------------------------------------

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
        "🧵 Thread da automação iniciada."
    )

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
# API PRINCIPAL
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar_api():

    print(
        "➡️ POST /api/configurar"
    )

    return processar_configuracao()


# ============================================================
# ROTA COMPATÍVEL
# ============================================================
#
# Esta rota resolve o problema:
#
# GET /configurar
#
# e também aceita:
#
# POST /configurar
#
# O POST funciona exatamente igual ao
# /api/configurar.
#
# ============================================================

@app.route(
    "/configurar",
    methods=["GET", "POST"]
)
def configurar_compatibilidade():

    print(
        f"➡️ {request.method} /configurar"
    )

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    if request.method == "GET":

        return jsonify({
            "ok": True,
            "servico":
                "Raposa Caçadora",
            "mensagem":
                "A rota /configurar existe. "
                "Para iniciar uma automação use POST.",
            "metodo":
                "POST",
            "rota_recomendada":
                "/api/configurar"
        }), 200

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    return processar_configuracao()


# ============================================================
# TRATAMENTO 404
# ============================================================

@app.errorhandler(404)
def erro_404(e):

    print(
        f"❌ 404: {request.method} {request.path}"
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
# TRATAMENTO 500
# ============================================================

@app.errorhandler(500)
def erro_500(e):

    print(
        "❌ ERRO INTERNO:"
    )

    print(
        repr(e)
    )

    return jsonify({
        "ok": False,
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
        "\n📌 ROTAS DISPONÍVEIS:"
    )

    for regra in app.url_map.iter_rules():

        print(
            f"   {sorted(regra.methods)} "
            f"{regra}"
        )


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
        f"📁 Pasta do programa: "
        f"{BASE_DIR}"
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

    mostrar_rotas()

    print(
        "=" * 60
    )

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
