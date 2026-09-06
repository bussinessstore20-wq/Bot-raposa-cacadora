import os
import json
import time
import html
import threading
import hashlib
import hmac
import re

import requests

from bs4 import BeautifulSoup

from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory
)

from urllib.parse import (
    parse_qsl,
    urljoin
)


# ============================================================
# RAPOSA CAÇADORA
# MAIN.PY - VERSÃO DEFINITIVA
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

REQUEST_TIMEOUT = 30


# ============================================================
# FLASK
# ============================================================

app = Flask(
    __name__,
    static_folder=BASE_DIR
)


# ============================================================
# LOG
# ============================================================

def log(mensagem):

    print(
        mensagem,
        flush=True
    )


# ============================================================
# ROTA /
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify({

        "ok": True,

        "servico":
            "Raposa Caçadora",

        "status":
            "online",

        "mensagem":
            "Servidor funcionando.",

        "rotas": [

            "/",

            "/app",

            "/health",

            "/api/configurar",

            "/configurar"

        ]

    })


# ============================================================
# MINI APP
# ============================================================

@app.route(
    "/app",
    methods=["GET"]
)
def mini_app():

    log(
        f"📂 Procurando index.html: {INDEX_FILE}"
    )

    if not os.path.isfile(
        INDEX_FILE
    ):

        log(
            "❌ index.html não encontrado."
        )

        return jsonify({

            "ok": False,

            "erro":
                "index.html não encontrado.",

            "diretorio":
                BASE_DIR

        }), 404

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
# CONFIGURAÇÃO
# ============================================================

def verificar_configuracao():

    if not TELEGRAM_TOKEN:

        log(
            "❌ TELEGRAM_TOKEN não configurado."
        )

        return False

    if not CHAT_ID:

        log(
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

    except Exception as erro:

        log(
            f"⚠️ Erro initData: {erro}"
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

        log(
            f"⚠️ Erro histórico: {erro}"
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

        log(
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

        log(
            "❌ TELEGRAM_TOKEN ausente."
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

            timeout=REQUEST_TIMEOUT

        )

        resultado = resposta.json()

        if not resultado.get(
            "ok",
            False
        ):

            log(
                f"❌ Telegram: {resultado}"
            )

        return resultado

    except Exception as erro:

        log(
            f"❌ Erro Telegram: {erro}"
        )

        return None


# ============================================================
# MENSAGEM TELEGRAM
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

    return bool(
        resultado
        and resultado.get("ok")
    )


# ============================================================
# OFERTA
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
                "Chrome/128.0.0.0 "
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

        resposta = requests.get(

            url,

            headers=headers,

            allow_redirects=True,

            timeout=REQUEST_TIMEOUT

        )

        resposta.raise_for_status()

        return resposta.url

    except Exception as erro:

        log(
            f"❌ Erro expandindo link: {erro}"
        )

        return None


# ============================================================
# NORMALIZAR LINK
# ============================================================

def normalizar_link(
    link
):

    if not link:

        return ""

    link = link.strip()

    link = link.split("#")[0]

    return link


# ============================================================
# É PRODUTO?
# ============================================================

def eh_link_produto(
    url
):

    url_lower = url.lower()

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
# ENCONTRAR LINKS NA VITRINE
# ============================================================

def encontrar_links_produtos(
    url_vitrine,
    headers
):

    log(
        f"🔎 Acessando vitrine: {url_vitrine}"
    )

    try:

        resposta = requests.get(

            url_vitrine,

            headers=headers,

            timeout=REQUEST_TIMEOUT

        )

        resposta.raise_for_status()

    except Exception as erro:

        log(
            f"❌ Erro acessando vitrine: {erro}"
        )

        return []

    soup = BeautifulSoup(
        resposta.text,
        "html.parser"
    )

    links = []

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

        href = normalizar_link(
            href
        )

        if eh_link_produto(
            href
        ):

            links.append(
                href
            )

    links = list(
        dict.fromkeys(
            links
        )
    )

    log(
        f"📦 {len(links)} links encontrados."
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

            timeout=REQUEST_TIMEOUT

        )

        resposta.raise_for_status()

    except Exception as erro:

        log(
            f"⚠️ Erro produto: {erro}"
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
        class_=re.compile(
            r"ui-pdp-title"
        )
    )

    if elemento:

        titulo = elemento.get_text(
            " ",
            strip=True
        )

    if not titulo:

        meta = soup.find(
            "meta",
            property="og:title"
        )

        if meta:

            titulo = meta.get(
                "content",
                ""
            ).strip()

    if not titulo:

        titulo = (
            "Oferta Imperdível!"
        )

    # --------------------------------------------------------
    # IMAGEM
    # --------------------------------------------------------

    foto_url = ""

    meta = soup.find(
        "meta",
        property="og:image"
    )

    if meta:

        foto_url = meta.get(
            "content",
            ""
        ).strip()

    # --------------------------------------------------------
    # OUTRA IMAGEM
    # --------------------------------------------------------

    if not foto_url:

        for img in soup.find_all(
            "img"
        ):

            candidato = (

                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy")
                or ""

            ).strip()

            if candidato.startswith(
                "http"
            ):

                foto_url = candidato

                break

    if not foto_url:

        log(
            "⚠️ Produto sem imagem."
        )

        return None

    return {

        "titulo":
            html.escape(
                titulo
            ),

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

    log(
        "\n" + "=" * 60
    )

    log(
        "🦊 NOVA AUTOMAÇÃO"
    )

    log(
        f"🔗 {url_vitrine}"
    )

    log(
        f"📦 Quantidade: {quantidade_maxima}"
    )

    log(
        f"⏱️ Intervalo: {intervalo_seg}s"
    )

    log(
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
            "o link informado.</b>"

        )

        return

    log(
        f"🔗 URL final: {url_final}"
    )

    # --------------------------------------------------------
    # PRODUTO OU VITRINE
    # --------------------------------------------------------

    if eh_link_produto(
        url_final
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

            "O link foi acessado, porém não "
            "foi possível identificar produtos "
            "publicamente nessa página."

        )

        return

    # --------------------------------------------------------
    # HISTÓRICO
    # --------------------------------------------------------

    historico = (
        carregar_historico()
    )

    postados = 0

    # --------------------------------------------------------
    # PRODUTOS
    # --------------------------------------------------------

    for link in links_produtos:

        if postados >= quantidade_maxima:

            break

        link = normalizar_link(
            link
        )

        if not link:

            continue

        if link in historico:

            log(
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

            log(
                f"✅ POSTADO "
                f"{postados}/{quantidade_maxima}"
            )

            if postados < quantidade_maxima:

                log(
                    f"⏳ Aguardando "
                    f"{intervalo_seg}s..."
                )

                time.sleep(
                    intervalo_seg
                )

        else:

            log(
                "❌ Falha ao publicar oferta."
            )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    log(
        "\n" + "=" * 60
    )

    log(
        f"🎯 FINALIZADO: {postados} ofertas"
    )

    log(
        "=" * 60
    )

    enviar_mensagem(

        "✅ <b>Postagens finalizadas!</b>\n\n"

        f"🦊 Ofertas publicadas: "
        f"<b>{postados}</b>"

    )


# ============================================================
# PROCESSAR REQUISIÇÃO
# ============================================================

def processar_configuracao():

    # --------------------------------------------------------
    # GARANTE JSON
    # --------------------------------------------------------

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
                "JSON inválido ou ausente."

        }), 400

    log(
        f"📩 Dados recebidos: "
        f"{json.dumps(dados, ensure_ascii=False)}"
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
    ).strip()

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
    # LINK
    # --------------------------------------------------------

    if not link:

        return jsonify({

            "ok": False,

            "erro":
                "Informe o link da vitrine."

        }), 400

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    if not verificar_configuracao():

        return jsonify({

            "ok": False,

            "erro":
                "Bot Telegram não configurado."

        }), 500

    # --------------------------------------------------------
    # AUTENTICAÇÃO
    #
    # IMPORTANTE:
    # Se initData estiver presente, valida.
    #
    # Isso permite testar a API sem quebrar
    # quando o navegador acessar diretamente.
    # --------------------------------------------------------

    if init_data:

        if not validar_init_data(
            init_data
        ):

            log(
                "🚫 initData inválido."
            )

            return jsonify({

                "ok": False,

                "erro":
                    "Autenticação do Telegram inválida."

            }), 403

    else:

        log(
            "⚠️ initData não enviado."
        )

    # --------------------------------------------------------
    # LIMITES
    # --------------------------------------------------------

    intervalo = max(

        intervalo,

        MIN_INTERVALO

    )

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

    log(
        "\n" + "=" * 60
    )

    log(
        "🚀 ORDEM RECEBIDA"
    )

    log(
        f"🔗 Link: {link}"
    )

    log(
        f"⏱️ Intervalo: {intervalo}s"
    )

    log(
        f"📦 Quantidade: {quantidade}"
    )

    log(
        "=" * 60
    )

    # --------------------------------------------------------
    # AVISO
    # --------------------------------------------------------

    try:

        enviar_mensagem(

            "🚀 <b>Nova automação iniciada!</b>\n\n"

            f"📦 Quantidade: <b>{quantidade}</b>\n"

            f"⏱️ Intervalo: <b>{intervalo}s</b>\n\n"

            "🔎 Pesquisando produtos..."

        )

    except Exception as erro:

        log(
            f"⚠️ Falha enviando aviso: {erro}"
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

        log(
            f"❌ Erro criando thread: {erro}"
        )

        return jsonify({

            "ok": False,

            "erro":
                "Não foi possível iniciar a automação.",

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
            intervalo

    }), 200


# ============================================================
# POST /api/configurar
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def api_configurar():

    try:

        return processar_configuracao()

    except Exception as erro:

        log(
            f"❌ ERRO /api/configurar: {erro}"
        )

        return jsonify({

            "ok": False,

            "erro":
                "Erro interno no servidor.",

            "detalhe":
                str(erro)

        }), 500


# ============================================================
# GET /api/configurar
# ============================================================

@app.route(
    "/api/configurar",
    methods=["GET"]
)
def api_configurar_get():

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
# POST /configurar
#
# ALIAS PARA COMPATIBILIDADE
# ============================================================

@app.route(
    "/configurar",
    methods=["POST"]
)
def configurar_alias():

    try:

        return processar_configuracao()

    except Exception as erro:

        log(
            f"❌ ERRO /configurar: {erro}"
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

        "ok": False,

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
# ERRO 404
# ============================================================

@app.errorhandler(404)
def erro_404(erro):

    return jsonify({

        "ok": False,

        "erro":
            "Rota não encontrada.",

        "detalhe":
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
# ERRO 405
# ============================================================

@app.errorhandler(405)
def erro_405(erro):

    return jsonify({

        "ok": False,

        "erro":
            "Método não permitido.",

        "detalhe":
            f"{request.method} {request.path}",

        "metodo_correto":
            "POST",

        "rotas_disponiveis": [

            "/api/configurar",

            "/configurar"

        ]

    }), 405


# ============================================================
# ERRO 500
# ============================================================

@app.errorhandler(500)
def erro_500(erro):

    log(
        f"❌ Erro 500: {erro}"
    )

    return jsonify({

        "ok": False,

        "erro":
            "Erro interno no servidor.",

        "detalhe":
            str(erro)

    }), 500


# ============================================================
# INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":

    log(
        "=" * 60
    )

    log(
        "🦊 RAPOSA CAÇADORA"
    )

    log(
        "🚀 SERVIDOR INICIANDO"
    )

    log(
        "=" * 60
    )

    log(
        f"📁 BASE_DIR: {BASE_DIR}"
    )

    log(
        f"📄 index.html: "
        f"{'OK' if os.path.isfile(INDEX_FILE) else 'NÃO ENCONTRADO'}"
    )

    log(
        f"🤖 TELEGRAM: "
        f"{'CONFIGURADO' if TELEGRAM_TOKEN else 'NÃO CONFIGURADO'}"
    )

    log(
        f"💬 CHAT_ID: {CHAT_ID}"
    )

    log(
        f"🌐 PORTA: {PORT}"
    )

    if WEBAPP_URL:

        log(
            f"📱 MINI APP: {WEBAPP_URL}/app"
        )

    else:

        log(
            "⚠️ WEBAPP_URL não configurada."
        )

    log(
        "🌐 Rotas disponíveis:"
    )

    log(
        "   GET  /"
    )

    log(
        "   GET  /app"
    )

    log(
        "   GET  /health"
    )

    log(
        "   POST /api/configurar"
    )

    log(
        "   POST /configurar"
    )

    log(
        "=" * 60
    )

    app.run(

        host="0.0.0.0",

        port=PORT,

        debug=False

    )
