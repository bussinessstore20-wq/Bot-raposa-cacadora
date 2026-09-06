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
# PÁGINA INICIAL
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

@app.route("/app")
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

@app.route("/health")
def health():

    return jsonify({
        "ok": True,
        "servico": "Raposa Caçadora",
        "status": "online",
        "mini_app": os.path.isfile(INDEX_FILE)
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

        return hmac.compare_digest(
            calculado,
            hash_recebido
        )

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

        resposta.raise_for_status()

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
                    "text": "🛒 COMPRAR NO MERCADO LIVRE",
                    "url": link_afiliado
                }
            ]
        ]
    }

    dados = {
        "chat_id": CHAT_ID,
        "photo": foto_url,
        "caption": legenda,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(
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
# EXPANDIR LINK
# ============================================================

def expandir_link(
    url,
    headers
):

    try:

        resposta = requests.get(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=20
        )

        resposta.raise_for_status()

        return resposta.url

    except Exception as e:

        print(
            f"❌ Erro ao expandir URL: {e}"
        )

        return None


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
            timeout=20
        )

        resposta.raise_for_status()

    except Exception as e:

        print(
            f"❌ Erro ao acessar vitrine: {e}"
        )

        return []

    soup = BeautifulSoup(
        resposta.text,
        "html.parser"
    )

    links = []

    padroes = [
        "produto.mercadolivre.com.br",
        "/p/MLB",
        "MLB-"
    ]

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

        href = href.split("#")[0]

        if any(
            padrao in href
            for padrao in padroes
        ):

            links.append(
                href
            )

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

    try:

        resposta = requests.get(
            link,
            headers=headers,
            allow_redirects=True,
            timeout=20
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
                or ""
            )

            if candidato.startswith(
                "http"
            ):

                foto_url = candidato

                break

    if not foto_url:

        print(
            "⚠️ Produto sem imagem."
        )

        return None

    titulo = html.escape(
        titulo
    )

    return {

        "titulo":
            titulo,

        "foto_url":
            foto_url,

        "link":
            link
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
            "a vitrine.</b>"
        )

        return

    print(
        f"🔗 URL final: {url_final}"
    )

    # --------------------------------------------------------
    # IDENTIFICAR PRODUTO OU VITRINE
    # --------------------------------------------------------

    padroes_produto = [
        "produto.mercadolivre.com.br",
        "/p/MLB",
        "MLB-"
    ]

    if any(
        padrao in url_final
        for padrao in padroes_produto
    ):

        links_produtos = [
            url_final
        ]

    else:

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
            "O Mercado Livre pode ter alterado "
            "a estrutura da página ou o link "
            "informado pode não ser uma vitrine "
            "pública."
        )

        return

    # --------------------------------------------------------
    # HISTÓRICO
    # --------------------------------------------------------

    historico = carregar_historico()

    postados = 0

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
            link
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
        f"<b>{postados}</b>"
    )


# ============================================================
# API /api/configurar
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

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

        return jsonify({
            "ok": False,
            "erro":
                "Dados inválidos."
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
    )

    try:

        intervalo = int(
            dados.get(
                "intervalo",
                300
            )
        )

    except Exception:

        intervalo = 300

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
    # INIT DATA
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
    # LINK
    # --------------------------------------------------------

    if not link:

        return jsonify({
            "ok": False,
            "erro":
                "Informe o link da vitrine."
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

    enviar_mensagem(
        "🚀 <b>Nova automação iniciada!</b>\n\n"
        f"📦 Quantidade: <b>{quantidade}</b>\n"
        f"⏱️ Intervalo: <b>{intervalo}s</b>"
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

    return jsonify({
        "ok": True,
        "mensagem":
            "Postagens iniciadas."
    })


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
        f"📁 Pasta do programa: {BASE_DIR}"
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

    print(
        "=" * 60
    )

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
