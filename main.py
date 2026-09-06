import os
import json
import time
import html
import threading
import hashlib
import hmac
from urllib.parse import parse_qsl

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()

# Pode ser @canal ou ID numérico
CHAT_ID = os.getenv("CHAT_ID", "@raposacacadora").strip()

# URL pública do Render
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

ARQUIVO_HISTORICO = "produtos_postados.txt"

PORT = int(os.getenv("PORT", "10000"))

# Limites de segurança
MAX_QUANTIDADE = 50
MIN_INTERVALO = 10


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__, static_folder=".")


@app.route("/")
def home():
    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Raposa Caçadora</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #111827;
                color: white;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                text-align: center;
            }

            .box {
                background: #1f2937;
                padding: 30px;
                border-radius: 16px;
                max-width: 500px;
                width: 90%;
                box-shadow: 0 10px 30px rgba(0,0,0,.3);
            }

            h1 {
                color: #f97316;
            }

            p {
                color: #d1d5db;
            }
        </style>
    </head>
    <body>
        <div class="box">
            <h1>🦊 Raposa Caçadora</h1>
            <p>Servidor online.</p>
            <p>Mini App disponível em <b>/app</b>.</p>
        </div>
    </body>
    </html>
    """


@app.route("/app")
def mini_app():
    try:
        return send_from_directory(".", "index.html")
    except Exception as e:
        print(f"❌ Erro ao carregar index.html: {e}")

        return """
        <h2>❌ Mini App não encontrado</h2>
        <p>Verifique se o arquivo <b>index.html</b> está na mesma pasta do main.py.</p>
        """, 404


# ============================================================
# VALIDAÇÕES
# ============================================================

def verificar_configuracao():
    if not TELEGRAM_TOKEN:
        print("❌ ERRO: variável TELEGRAM_TOKEN não configurada.")
        return False

    if not CHAT_ID:
        print("❌ ERRO: variável CHAT_ID não configurada.")
        return False

    return True


def validar_init_data(init_data):
    """
    Valida o initData recebido pelo Telegram Mini App.

    O Telegram utiliza:
        secret_key = HMAC_SHA256("WebAppData", BOT_TOKEN)

    Depois:
        hash = HMAC_SHA256(secret_key, data_check_string)
    """

    if not init_data:
        return False

    try:
        dados = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        hash_recebido = dados.pop("hash", None)

        if not hash_recebido:
            return False

        data_check_string = "\n".join(
            f"{chave}={valor}"
            for chave, valor in sorted(dados.items())
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
    if not os.path.exists(ARQUIVO_HISTORICO):
        return set()

    try:
        with open(
            ARQUIVO_HISTORICO,
            "r",
            encoding="utf-8"
        ) as arquivo:

            return set(
                linha.strip()
                for linha in arquivo
                if linha.strip()
            )

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
                    f"{link}\n"
                )

    except Exception as e:
        print(
            f"⚠️ Erro ao salvar histórico: {e}"
        )


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api(metodo, dados=None):
    if not TELEGRAM_TOKEN:
        print(
            "❌ TELEGRAM_TOKEN não configurado."
        )

        return None

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/{metodo}"
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
                f"❌ Telegram retornou erro: "
                f"{resultado}"
            )

        return resultado

    except requests.RequestException as e:
        print(
            f"❌ Erro de conexão com Telegram "
            f"({metodo}): {e}"
        )

        return None

    except ValueError as e:
        print(
            f"❌ Resposta inválida da API Telegram: "
            f"{e}"
        )

        return None

    except Exception as e:
        print(
            f"❌ Erro na API Telegram "
            f"({metodo}): {e}"
        )

        return None


def enviar_mensagem(texto):
    dados = {
        "chat_id": CHAT_ID,
        "text": texto,
        "parse_mode": "HTML"
    }

    resultado = telegram_api(
        "sendMessage",
        dados
    )

    return bool(
        resultado
        and resultado.get("ok")
    )


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

    payload = {
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
        payload
    )

    return bool(
        resultado
        and resultado.get("ok")
    )


# ============================================================
# LIMPEZA DE LINKS
# ============================================================

def limpar_link(link):
    if not link:
        return ""

    return str(link).strip()


# ============================================================
# EXPANSÃO DE LINK
# ============================================================

def expandir_link(url, headers):
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
# DESCOBRIR PRODUTOS
# ============================================================

def encontrar_links_produtos(
    url_vitrine,
    headers
):
    print(
        f"\n🔎 Acessando: {url_vitrine}"
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

        href = href.split("#")[0]

        if any(
            padrao in href
            for padrao in padroes
        ):
            links.append(href)

    # Remove duplicados mantendo ordem
    links = list(
        dict.fromkeys(links)
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

    titulo_elem = soup.find(
        "h1",
        class_="ui-pdp-title"
    )

    if titulo_elem:
        titulo = titulo_elem.get_text(
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
        img = soup.find(
            "img",
            class_="ui-pdp-image"
        )

        if img:
            foto_url = (
                img.get("src")
                or img.get("data-src")
                or ""
            )

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    if not foto_url:
        print(
            "⚠️ Produto sem imagem."
        )

        return None

    titulo = html.escape(
        titulo
    )

    return {
        "titulo": titulo,
        "foto_url": foto_url,
        "link": link
    }


# ============================================================
# PROCESSAMENTO DA VITRINE
# ============================================================

def processar_e_postar_vitrine(
    url_vitrine,
    quantidade_maxima,
    intervalo_seg
):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0.0.0 "
            "Safari/537.36"
        ),
        "Accept-Language": (
            "pt-BR,pt;q=0.9"
        )
    }

    print(
        "\n" + "=" * 60
    )
    print(
        "🦊 NOVA TAREFA DE POSTAGEM"
    )
    print(
        "=" * 60
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
            "❌ <b>Não foi possível acessar "
            "a vitrine.</b>"
        )

        return

    print(
        f"🔗 URL final: {url_final}"
    )

    # --------------------------------------------------------
    # VERIFICAR SE É PRODUTO DIRETO
    # --------------------------------------------------------

    links_produtos = []

    padroes_produto = [
        "produto.mercadolivre.com.br",
        "/p/MLB",
        "MLB-"
    ]

    if any(
        padrao in url_final
        for padrao in padroes_produto
    ):
        links_produtos.append(
            url_final
        )

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
        print(
            "⚠️ Nenhum produto encontrado."
        )

        enviar_mensagem(
            "⚠️ <b>Nenhum produto foi encontrado.</b>\n\n"
            "Verifique se o link informado é uma "
            "vitrine/lista válida do Mercado Livre."
        )

        return

    print(
        f"📦 Produtos encontrados: "
        f"{len(links_produtos)}"
    )

    # --------------------------------------------------------
    # HISTÓRICO
    # --------------------------------------------------------

    historico = carregar_historico()

    postados = 0

    # --------------------------------------------------------
    # LOOP DOS PRODUTOS
    # --------------------------------------------------------

    for link in links_produtos:

        if postados >= quantidade_maxima:
            break

        link = link.strip()

        if not link:
            continue

        if link in historico:
            print(
                f"⏭️ Já postado: {link}"
            )

            continue

        print(
            f"\n🔍 Extraindo produto:"
            f"\n{link}"
        )

        produto = extrair_produto(
            link,
            headers
        )

        if not produto:
            continue

        titulo = produto["titulo"]
        foto_url = produto["foto_url"]

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
                    f"{intervalo_seg} segundos..."
                )

                time.sleep(
                    intervalo_seg
                )

        else:

            print(
                "❌ Falha ao publicar produto."
            )

    # --------------------------------------------------------
    # FINALIZAÇÃO
    # --------------------------------------------------------

    print(
        "\n" + "=" * 60
    )

    print(
        f"🎯 FINALIZADO: "
        f"{postados} ofertas publicadas."
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
# API DO MINI APP
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    if not verificar_configuracao():

        return jsonify({
            "ok": False,
            "erro": "Bot não configurado."
        }), 500

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    dados = request.get_json(
        silent=True
    )

    if not dados:

        return jsonify({
            "ok": False,
            "erro": "Dados inválidos."
        }), 400

    # --------------------------------------------------------
    # DADOS
    # --------------------------------------------------------

    link = limpar_link(
        dados.get("link")
    )

    intervalo = dados.get(
        "intervalo",
        300
    )

    quantidade = dados.get(
        "quantidade",
        5
    )

    init_data = dados.get(
        "initData",
        ""
    )

    # --------------------------------------------------------
    # VALIDAR INIT DATA
    # --------------------------------------------------------

    if not validar_init_data(
        init_data
    ):

        print(
            "🚫 Requisição recusada: "
            "initData inválido."
        )

        return jsonify({
            "ok": False,
            "erro": (
                "Autenticação do Telegram "
                "inválida."
            )
        }), 403

    # --------------------------------------------------------
    # VALIDAR LINK
    # --------------------------------------------------------

    if not link:

        return jsonify({
            "ok": False,
            "erro": (
                "Informe o link da vitrine."
            )
        }), 400

    # --------------------------------------------------------
    # VALIDAR INTERVALO
    # --------------------------------------------------------

    try:
        intervalo = int(
            intervalo
        )

    except Exception:
        intervalo = 300

    if intervalo < MIN_INTERVALO:
        intervalo = MIN_INTERVALO

    # --------------------------------------------------------
    # VALIDAR QUANTIDADE
    # --------------------------------------------------------

    try:
        quantidade = int(
            quantidade
        )

    except Exception:
        quantidade = 5

    if quantidade < 1:
        quantidade = 1

    if quantidade > MAX_QUANTIDADE:
        quantidade = MAX_QUANTIDADE

    # --------------------------------------------------------
    # MOSTRAR NO CONSOLE
    # --------------------------------------------------------

    print(
        "\n" + "=" * 60
    )

    print(
        "📩 ORDEM RECEBIDA DO MINI APP"
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
    # AVISO INICIAL
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
        "mensagem": (
            "Postagens iniciadas."
        )
    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "servico": "Raposa Caçadora"
    })


# ============================================================
# INICIALIZAÇÃO
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

    if not TELEGRAM_TOKEN:

        print(
            "⚠️ TELEGRAM_TOKEN não configurado."
        )

    else:

        print(
            "✅ TELEGRAM_TOKEN configurado."
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
        port=PORT
    )
