import os
import re
import json
import time
import html
import threading
import hashlib
import hmac

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

from flask_cors import CORS


# ============================================================
# RAPOSA CAÇADORA
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

PORT = int(
    os.getenv(
        "PORT",
        "10000"
    )
)

# Máximo de produtos por execução
MAX_QUANTIDADE = 50

# Intervalo mínimo em minutos
MIN_INTERVALO_MINUTOS = 1

# Timeout individual das requisições
HTTP_TIMEOUT = 15


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
# THREADS / LOCKS
# ============================================================

automacoes_lock = threading.Lock()

automacoes_ativas = 0

historico_lock = threading.Lock()


# ============================================================
# SESSÃO HTTP
# ============================================================

session = requests.Session()


# ============================================================
# HEADERS
# ============================================================

def obter_headers():

    return {

        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Linux; Android 15) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 "
                "Mobile Safari/537.36"
            ),

        "Accept":
            (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "image/avif,image/webp,"
                "*/*;q=0.8"
            ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache",

        "Upgrade-Insecure-Requests":
            "1",

        "Connection":
            "keep-alive"

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

        <meta
            name="viewport"
            content="width=device-width,
            initial-scale=1.0"
        >

        <title>
            Raposa Caçadora
        </title>

        <style>

            body {
                background:#05070a;
                color:#fff;
                font-family:Arial,sans-serif;
                text-align:center;
                padding-top:50px;
            }

            h1 {
                color:#f97316;
            }

            .online {
                color:#22c55e;
                font-weight:bold;
            }

            a {
                color:#fb923c;
                text-decoration:none;
                font-weight:bold;
            }

        </style>

    </head>

    <body>

        <h1>
            🦊 Raposa Caçadora
        </h1>

        <p class="online">
            ● SERVIDOR ONLINE
        </p>

        <p>
            <a href="/app">
                Abrir Mini App
            </a>
        </p>

        <p>
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

    if not os.path.isfile(
        INDEX_FILE
    ):

        return (
            "❌ index.html não encontrado.",
            404
        )

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

    with automacoes_lock:

        ativas = automacoes_ativas

    return jsonify({

        "ok":
            True,

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
# VALIDAR TELEGRAM WEB APP
# ============================================================

def validar_init_data(
    init_data
):

    if not init_data:

        print(
            "⚠️ initData vazio."
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
                "❌ Hash não encontrado."
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

        if valido:

            print(
                "✅ initData Telegram válido."
            )

        else:

            print(
                "❌ initData Telegram inválido."
            )

        return valido

    except Exception as e:

        print(
            f"❌ Erro validando Telegram: {e}"
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
            ) as arquivo:

                return {
                    linha.strip()
                    for linha in arquivo
                    if linha.strip()
                }

    except Exception as e:

        print(
            f"⚠️ Erro lendo histórico: {e}"
        )

        return set()


def salvar_historico(
    link
):

    if not link:

        return False

    try:

        with historico_lock:

            with open(
                ARQUIVO_HISTORICO,
                "a",
                encoding="utf-8"
            ) as arquivo:

                arquivo.write(
                    link.strip()
                    + "\n"
                )

        return True

    except Exception as e:

        print(
            f"⚠️ Erro salvando histórico: {e}"
        )

        return False


# ============================================================
# TELEGRAM
# ============================================================

def enviar_oferta(
    foto_url,
    legenda,
    link_produto
):

    if not TELEGRAM_TOKEN:

        print(
            "❌ TELEGRAM_TOKEN ausente."
        )

        return False

    if not foto_url:

        print(
            "❌ Imagem ausente."
        )

        return False

    if not link_produto:

        print(
            "❌ Link do produto ausente."
        )

        return False

    telegram_url = (
        "https://api.telegram.org/"
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

        resposta = session.post(
            telegram_url,
            data=payload,
            timeout=HTTP_TIMEOUT
        )

        resultado = resposta.json()

        if resultado.get("ok"):

            print(
                "✅ Oferta enviada ao Telegram."
            )

            return True

        print(
            "❌ Telegram recusou:"
        )

        print(
            resultado
        )

        return False

    except Exception as e:

        print(
            f"❌ Erro Telegram: {e}"
        )

        return False


# ============================================================
# NORMALIZAR URL
# ============================================================

def normalizar_url(
    url,
    base_url=""
):

    if not url:

        return ""

    try:

        url = html.unescape(
            str(url).strip()
        )

        url = url.replace(
            "\\/",
            "/"
        )

        url = unquote(
            url
        )

        if url.startswith(
            "//"
        ):

            url = (
                "https:"
                + url
            )

        elif url.startswith(
            "/"
        ):

            url = urljoin(
                base_url,
                url
            )

        elif not url.startswith(
            (
                "http://",
                "https://"
            )
        ):

            return ""

        return url.split(
            "#"
        )[0]

    except Exception:

        return ""


# ============================================================
# DETECTAR PRODUTO ML
# ============================================================

def parece_produto_mercado_livre(
    url
):

    if not url:

        return False

    url_lower = (
        unquote(
            url
        )
        .lower()
    )

    padroes = [

        "/p/mlb",

        "mlb-",

        "produto.mercadolivre.com.br",

        "mercadolivre.com.br/up/",

        "mercadolivre.com.br/p/",

        "mercadolibre.com/p/",

        "mercadolibre.com.ar/p/",

        "/up/"

    ]

    for padrao in padroes:

        if padrao in url_lower:

            return True

    return False


# ============================================================
# EXTRAIR ID MLB
# ============================================================

def extrair_id_mlb(
    url
):

    if not url:

        return None

    texto = unquote(
        url
    ).upper()

    padroes = [

        r"MLB[-_]?(\d{6,15})",

        r"/P/(MLB\d{6,15})",

        r"/UP/(MLB\d{6,15})"

    ]

    for padrao in padroes:

        resultado = re.search(
            padrao,
            texto
        )

        if resultado:

            numero = resultado.group(
                1
            )

            return (
                "MLB"
                + numero
            )

    return None


# ============================================================
# EXTRAIR LINKS DO HTML
# ============================================================

def extrair_links_produtos(
    texto,
    base_url
):

    encontrados = []

    # --------------------------------------------------------
    # HTML
    # --------------------------------------------------------

    try:

        soup = BeautifulSoup(
            texto,
            "html.parser"
        )

        # A
        for tag in soup.find_all(
            "a",
            href=True
        ):

            href = normalizar_url(
                tag.get("href"),
                base_url
            )

            if parece_produto_mercado_livre(
                href
            ):

                encontrados.append(
                    href
                )

        # IMG
        for tag in soup.find_all(
            "img",
            src=True
        ):

            src = normalizar_url(
                tag.get("src"),
                base_url
            )

            if parece_produto_mercado_livre(
                src
            ):

                encontrados.append(
                    src
                )

    except Exception as e:

        print(
            f"⚠️ Erro BeautifulSoup: {e}"
        )

    # --------------------------------------------------------
    # TEXTO / JSON / JAVASCRIPT
    # --------------------------------------------------------

    padroes = [

        r'https?://[^"\']+',

        r'//[^"\']+',

        r'(?:"|\\")(/p/MLB\d+)',

        r'(?:"|\\")(\/MLB-\d+)',

        r'(?:"|\\")(\/up/[^"\']+)',

        r'(?:"|\\")(\/sec/[^"\']+)'

    ]

    for padrao in padroes:

        try:

            encontrados_regex = re.findall(
                padrao,
                texto,
                re.IGNORECASE
            )

        except Exception:

            encontrados_regex = []

        for item in encontrados_regex:

            if isinstance(
                item,
                tuple
            ):

                item = item[0]

            item = normalizar_url(
                item,
                base_url
            )

            if parece_produto_mercado_livre(
                item
            ):

                encontrados.append(
                    item
                )

    # --------------------------------------------------------
    # CONVERTER IDS MLB ENCONTRADOS
    # --------------------------------------------------------

    ids = re.findall(
        r"\bMLB[-_]?\d{6,15}\b",
        texto,
        re.IGNORECASE
    )

    for item in ids:

        item = item.upper().replace(
            "-",
            ""
        )

        encontrados.append(
            "https://www.mercadolivre.com.br/p/"
            + item
        )

    # --------------------------------------------------------
    # DEDUPLICAR
    # --------------------------------------------------------

    resultado = []

    vistos_ids = set()

    for link in encontrados:

        link = normalizar_url(
            link,
            base_url
        )

        if not link:

            continue

        mlb = extrair_id_mlb(
            link
        )

        if mlb:

            chave = mlb

        else:

            chave = link

        if chave in vistos_ids:

            continue

        vistos_ids.add(
            chave
        )

        resultado.append(
            link
        )

    return resultado


# ============================================================
# RESOLVER MELI.LA
# ============================================================

def resolver_meli(
    url_vitrine
):

    print("")
    print(
        "🔗 Tentando resolver meli.la..."
    )

    print(
        url_vitrine
    )

    headers = obter_headers()

    try:

        # ----------------------------------------------------
        # HEAD
        # ----------------------------------------------------

        try:

            resposta_head = session.head(
                url_vitrine,
                headers=headers,
                allow_redirects=True,
                timeout=8
            )

            print(
                "📡 HEAD:"
                f" HTTP {resposta_head.status_code}"
            )

            print(
                "➡️ HEAD destino:"
                f" {resposta_head.url}"
            )

            if (
                resposta_head.url
                and
                resposta_head.url != url_vitrine
            ):

                return (
                    resposta_head.url,
                    resposta_head.text
                )

        except Exception as e:

            print(
                f"⚠️ HEAD falhou: {e}"
            )

        # ----------------------------------------------------
        # GET
        # ----------------------------------------------------

        resposta = session.get(
            url_vitrine,
            headers=headers,
            allow_redirects=True,
            timeout=12
        )

        print(
            "📡 GET:"
            f" HTTP {resposta.status_code}"
        )

        print(
            "➡️ GET destino:"
            f" {resposta.url}"
        )

        print(
            "📄 Tamanho:"
            f" {len(resposta.text)} bytes"
        )

        return (
            resposta.url,
            resposta.text
        )

    except requests.exceptions.Timeout:

        print(
            "❌ Timeout ao acessar meli.la."
        )

        return (
            url_vitrine,
            ""
        )

    except Exception as e:

        print(
            f"❌ Erro resolvendo meli.la: {e}"
        )

        return (
            url_vitrine,
            ""
        )


# ============================================================
# DESCOBRIR PRODUTOS
# ============================================================

def descobrir_produtos(
    url_vitrine
):

    print("")
    print(
        "========================================"
    )

    print(
        "🔎 DESCOBRINDO PRODUTOS"
    )

    print(
        "========================================"
    )

    destino, html_recebido = resolver_meli(
        url_vitrine
    )

    # --------------------------------------------------------
    # SE ENCONTROU PRODUTO NO PRÓPRIO REDIRECIONAMENTO
    # --------------------------------------------------------

    produtos = []

    if parece_produto_mercado_livre(
        destino
    ):

        print(
            "🎯 O link aponta diretamente "
            "para um produto."
        )

        produtos.append(
            destino
        )

    # --------------------------------------------------------
    # HTML
    # --------------------------------------------------------

    if html_recebido:

        encontrados = (
            extrair_links_produtos(
                html_recebido,
                destino
            )
        )

        print(
            "🔍 Links encontrados no HTML:"
            f" {len(encontrados)}"
        )

        produtos.extend(
            encontrados
        )

    # --------------------------------------------------------
    # DESTINO COMO URL
    # --------------------------------------------------------

    encontrados_destino = (
        extrair_links_produtos(
            destino,
            destino
        )
    )

    produtos.extend(
        encontrados_destino
    )

    # --------------------------------------------------------
    # DEDUPLICAR POR MLB
    # --------------------------------------------------------

    finais = []

    vistos = set()

    for link in produtos:

        mlb = extrair_id_mlb(
            link
        )

        if mlb:

            chave = mlb

        else:

            chave = link

        if chave in vistos:

            continue

        vistos.add(
            chave
        )

        finais.append(
            link
        )

    print("")
    print(
        f"🎯 TOTAL ENCONTRADO: {len(finais)}"
    )

    for numero, link in enumerate(
        finais[:20],
        start=1
    ):

        print(
            f"   {numero}. {link}"
        )

    print(
        "========================================"
    )

    return finais


# ============================================================
# EXTRAIR DADOS DO PRODUTO
# ============================================================

def extrair_dados_produto(
    url_produto
):

    headers = obter_headers()

    try:

        resposta = session.get(
            url_produto,
            headers=headers,
            allow_redirects=True,
            timeout=HTTP_TIMEOUT
        )

        print(
            "📦 Produto:"
            f" HTTP {resposta.status_code}"
        )

        if resposta.status_code >= 400:

            return None

        soup = BeautifulSoup(
            resposta.text,
            "html.parser"
        )

        # ----------------------------------------------------
        # TÍTULO
        # ----------------------------------------------------

        titulo = ""

        og_title = soup.find(
            "meta",
            property="og:title"
        )

        if og_title:

            titulo = (
                og_title.get(
                    "content",
                    ""
                )
                .strip()
            )

        if not titulo:

            h1 = soup.find(
                "h1"
            )

            if h1:

                titulo = h1.get_text(
                    " ",
                    strip=True
                )

        if not titulo:

            titulo = (
                "🔥 Oferta "
                "Imperdível!"
            )

        # ----------------------------------------------------
        # IMAGEM
        # ----------------------------------------------------

        imagem = ""

        og_image = soup.find(
            "meta",
            property="og:image"
        )

        if og_image:

            imagem = (
                og_image.get(
                    "content",
                    ""
                )
                .strip()
            )

        if not imagem:

            imagem_tag = soup.find(
                "img"
            )

            if imagem_tag:

                imagem = (
                    imagem_tag.get(
                        "src",
                        ""
                    )
                    or
                    imagem_tag.get(
                        "data-src",
                        ""
                    )
                )

        # ----------------------------------------------------
        # PREÇO
        # ----------------------------------------------------

        preco = ""

        meta_preco = soup.find(
            "meta",
            property="product:price:amount"
        )

        if meta_preco:

            preco = (
                meta_preco.get(
                    "content",
                    ""
                )
                .strip()
            )

        if not preco:

            elemento_preco = soup.find(
                class_=re.compile(
                    "andes-money-amount"
                )
            )

            if elemento_preco:

                preco = elemento_preco.get_text(
                    " ",
                    strip=True
                )

        # ----------------------------------------------------
        # RETORNO
        # ----------------------------------------------------

        return {

            "titulo":
                titulo,

            "imagem":
                imagem,

            "preco":
                preco,

            "url":
                resposta.url

        }

    except Exception as e:

        print(
            f"⚠️ Erro lendo produto: {e}"
        )

        return None


# ============================================================
# PROCESSAMENTO
# ============================================================

def processar_e_postar_vitrine(
    url_vitrine,
    quantidade_maxima,
    intervalo_minutos
):

    global automacoes_ativas

    with automacoes_lock:

        automacoes_ativas += 1

    try:

        print("")
        print(
            "🦊 ========================================"
        )

        print(
            "🦊 RAPOSA CAÇADORA"
        )

        print(
            "🦊 ========================================"
        )

        print(
            f"🔗 Vitrine:"
            f" {url_vitrine}"
        )

        print(
            f"📦 Quantidade:"
            f" {quantidade_maxima}"
        )

        print(
            f"⏱️ Intervalo:"
            f" {intervalo_minutos} minuto(s)"
        )

        # ----------------------------------------------------
        # DESCOBRIR PRODUTOS
        # ----------------------------------------------------

        produtos = descobrir_produtos(
            url_vitrine
        )

        if not produtos:

            print("")
            print(
                "❌ NENHUM PRODUTO ENCONTRADO."
            )

            print(
                "⚠️ O Render conseguiu iniciar "
                "a automação, porém a vitrine "
                "não entregou os produtos "
                "diretamente para o servidor."
            )

            print(
                "⚠️ Precisaremos então usar "
                "a API oficial ou uma forma "
                "de obter os produtos da vitrine."
            )

            return

        # ----------------------------------------------------
        # HISTÓRICO
        # ----------------------------------------------------

        historico = (
            carregar_historico()
        )

        publicados = 0

        # ----------------------------------------------------
        # PROCESSAR
        # ----------------------------------------------------

        for link in produtos:

            if publicados >= quantidade_maxima:

                break

            mlb = extrair_id_mlb(
                link
            )

            chave_historico = (
                mlb
                if mlb
                else link
            )

            if chave_historico in historico:

                print(
                    f"⏭️ Já publicado:"
                    f" {chave_historico}"
                )

                continue

            print("")
            print(
                "----------------------------------------"
            )

            print(
                f"🛒 Produto "
                f"{publicados + 1}/"
                f"{quantidade_maxima}"
            )

            print(
                f"🔗 {link}"
            )

            dados = (
                extrair_dados_produto(
                    link
                )
            )

            if not dados:

                print(
                    "⚠️ Não foi possível "
                    "obter os dados."
                )

                continue

            titulo = dados.get(
                "titulo",
                "🔥 Oferta Imperdível!"
            )

            imagem = dados.get(
                "imagem",
                ""
            )

            if not imagem:

                print(
                    "⚠️ Produto sem imagem."
                )

                continue

            titulo_seguro = html.escape(
                titulo
            )

            legenda = (
                f"🔥 <b>{titulo_seguro}</b>\n\n"
                f"⚡ <i>Oferta encontrada "
                f"pela Raposa Caçadora!</i>\n\n"
                f"🛒 <b>Confira no Mercado Livre:</b>"
            )

            # ------------------------------------------------
            # IMPORTANTE:
            # O BOTÃO USA O LINK ENCONTRADO.
            # ------------------------------------------------

            sucesso = enviar_oferta(
                imagem,
                legenda,
                link
            )

            if sucesso:

                salvar_historico(
                    chave_historico
                )

                publicados += 1

                print(
                    f"✅ PUBLICADO "
                    f"{publicados}/"
                    f"{quantidade_maxima}"
                )

                # --------------------------------------------
                # INTERVALO EM MINUTOS
                # --------------------------------------------

                if publicados < quantidade_maxima:

                    segundos = (
                        intervalo_minutos
                        * 60
                    )

                    print(
                        f"⏳ Próximo em "
                        f"{intervalo_minutos} "
                        f"minuto(s)."
                    )

                    time.sleep(
                        segundos
                    )

        print("")
        print(
            "========================================"
        )

        print(
            "🏁 AUTOMAÇÃO FINALIZADA"
        )

        print(
            f"📦 Publicados:"
            f" {publicados}"
        )

        print(
            "========================================"
        )

    except Exception as e:

        print(
            f"❌ Erro na automação: {e}"
        )

    finally:

        with automacoes_lock:

            automacoes_ativas -= 1

        print(
            "🦊 Thread encerrada."
        )


# ============================================================
# API CONFIGURAR
# ============================================================

@app.route(
    "/api/configurar",
    methods=[
        "POST",
        "OPTIONS"
    ]
)
@app.route(
    "/configurar",
    methods=[
        "POST",
        "OPTIONS"
    ]
)
def api_configurar():

    if request.method == "OPTIONS":

        return "", 200

    try:

        dados = (
            request.get_json(
                silent=True
            )
            or {}
        )

        print("")
        print(
            "============================================================"
        )

        print(
            "📥 NOVA CONFIGURAÇÃO"
        )

        print(
            "============================================================"
        )

        # ----------------------------------------------------
        # LINK
        # ----------------------------------------------------

        link = str(
            dados.get(
                "link",
                dados.get(
                    "linkCanal",
                    ""
                )
            )
        ).strip()

        # ----------------------------------------------------
        # INTERVALO
        # ----------------------------------------------------

        try:

            intervalo_minutos = int(
                dados.get(
                    "intervalo",
                    30
                )
            )

        except Exception:

            intervalo_minutos = 30

        # ----------------------------------------------------
        # QUANTIDADE
        # ----------------------------------------------------

        try:

            quantidade = int(
                dados.get(
                    "quantidade",
                    5
                )
            )

        except Exception:

            quantidade = 5

        # ----------------------------------------------------
        # TELEGRAM
        # ----------------------------------------------------

        init_data = str(
            dados.get(
                "initData",
                ""
            )
        ).strip()

        print(
            f"🔗 Link: {link}"
        )

        print(
            f"📦 Quantidade: {quantidade}"
        )

        print(
            f"⏱️ Intervalo: "
            f"{intervalo_minutos} minuto(s)"
        )

        # ----------------------------------------------------
        # VALIDA LINK
        # ----------------------------------------------------

        if not link:

            return jsonify({

                "erro":
                    "O link da vitrine "
                    "é obrigatório."

            }), 400

        # ----------------------------------------------------
        # LIMITES
        # ----------------------------------------------------

        if quantidade < 1:

            quantidade = 1

        if quantidade > MAX_QUANTIDADE:

            quantidade = (
                MAX_QUANTIDADE
            )

        if intervalo_minutos < MIN_INTERVALO_MINUTOS:

            intervalo_minutos = (
                MIN_INTERVALO_MINUTOS
            )

        # ----------------------------------------------------
        # VALIDAR TELEGRAM
        # ----------------------------------------------------

        if not validar_init_data(
            init_data
        ):

            return jsonify({

                "erro":
                    "Autenticação do Telegram "
                    "inválida ou expirada."

            }), 403

        # ----------------------------------------------------
        # INICIAR THREAD
        # ----------------------------------------------------

        thread = threading.Thread(

            target=
                processar_e_postar_vitrine,

            args=(
                link,
                quantidade,
                intervalo_minutos
            ),

            daemon=True

        )

        thread.start()

        print(
            "🚀 Automação iniciada "
            "em segundo plano."
        )

        print(
            "============================================================"
        )

        return jsonify({

            "sucesso":
                True,

            "mensagem":
                "🦊 Automação iniciada "
                "com sucesso!",

            "link":
                link,

            "quantidade":
                quantidade,

            "intervalo_minutos":
                intervalo_minutos

        }), 200

    except Exception as e:

        print(
            f"❌ Erro API: {e}"
        )

        return jsonify({

            "erro":
                f"Erro interno: {e}"

        }), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("")
    print(
        "============================================================"
    )

    print(
        "🦊 RAPOSA CAÇADORA"
    )

    print(
        "============================================================"
    )

    print(
        f"🌐 Porta: {PORT}"
    )

    print(
        f"🤖 Telegram: "
        f"{bool(TELEGRAM_TOKEN)}"
    )

    print(
        f"📢 Chat: "
        f"{bool(CHAT_ID)}"
    )

    print(
        "🌐 CORS: Vercel autorizado"
    )

    print(
        "============================================================"
    )

    app.run(
        host="0.0.0.0",
        port=PORT
    )
