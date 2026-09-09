import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re

from urllib.parse import parse_qsl, urlparse

import requests
from bs4 import BeautifulSoup

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS


# ============================================================
# APP
# ============================================================

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    }
)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    ""
).strip()

CHANNEL_USERNAME = os.environ.get(
    "CHANNEL_USERNAME",
    ""
).strip()

MAX_LINKS = 20

INTERVALOS_PERMITIDOS = {
    10,
    60,
    300,
    600
}


# ============================================================
# ARMAZENAMENTO
# ============================================================

tarefas = {}

tarefas_lock = threading.Lock()


# ============================================================
# SESSÃO HTTP
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": (
        "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "DNT": "1"
})


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_api_url(metodo):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    return (
        f"https://api.telegram.org/bot{token}/{metodo}"
    )


def telegram_get_me():

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {
            "ok": False,
            "erro": "BOT_TOKEN não configurado."
        }

    try:

        resposta = requests.get(
            telegram_api_url("getMe"),
            timeout=20
        )

        return resposta.json()

    except Exception as erro:

        return {
            "ok": False,
            "erro": str(erro)
        }


# ============================================================
# UTILITÁRIOS
# ============================================================

def limpar_texto(texto):

    if not texto:
        return ""

    texto = str(texto)

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def escapar_html(texto):

    if not texto:
        return ""

    texto = str(texto)

    texto = texto.replace(
        "&",
        "&amp;"
    )

    texto = texto.replace(
        "<",
        "&lt;"
    )

    texto = texto.replace(
        ">",
        "&gt;"
    )

    return texto


def formatar_preco(valor):

    if valor is None:
        return ""

    valor = str(valor).strip()

    if not valor:
        return ""

    valor = valor.replace(
        "R$",
        ""
    ).strip()

    # Remove espaços
    valor = valor.replace(
        " ",
        ""
    )

    # Detecta formato brasileiro
    if "," in valor:

        valor = valor.replace(
            ".",
            ""
        )

        valor = valor.replace(
            ",",
            "."
        )

    try:

        numero = float(valor)

        return (
            "R$ "
            + f"{numero:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except Exception:

        return ""


def converter_preco_float(preco_str):

    if not preco_str:
        return 0.0

    try:

        limpo = str(preco_str)

        limpo = (
            limpo
            .replace("R$", "")
            .replace(" ", "")
        )

        # Exemplo:
        # 1.299,90 -> 1299.90
        if "," in limpo:

            limpo = limpo.replace(
                ".",
                ""
            )

            limpo = limpo.replace(
                ",",
                "."
            )

        return float(limpo)

    except Exception:

        return 0.0


def normalizar_url(url):

    if not url:
        return ""

    url = str(url).strip()

    if not url:
        return ""

    if url.startswith("//"):

        return "https:" + url

    return url


# ============================================================
# JSON SEGURO
# ============================================================

def tentar_json(texto):

    if not texto:
        return None

    try:

        return json.loads(
            texto
        )

    except Exception:

        pass

    # Algumas páginas colocam lixo antes/depois do JSON
    try:

        inicio = texto.find("{")
        fim = texto.rfind("}")

        if inicio >= 0 and fim > inicio:

            return json.loads(
                texto[inicio:fim + 1]
            )

    except Exception:

        pass

    return None


# ============================================================
# EXTRAÇÃO DE JSON-LD
# ============================================================

def extrair_blocos_json_ld(soup):

    blocos = []

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        try:

            conteudo = (
                script.string
                or
                script.get_text()
            )

            if not conteudo:
                continue

            dados = tentar_json(
                conteudo
            )

            if dados is None:
                continue

            if isinstance(
                dados,
                list
            ):

                blocos.extend(
                    dados
                )

            elif isinstance(
                dados,
                dict
            ):

                blocos.append(
                    dados
                )

                graph = dados.get(
                    "@graph"
                )

                if isinstance(
                    graph,
                    list
                ):

                    blocos.extend(
                        graph
                    )

        except Exception:

            continue

    return blocos


# ============================================================
# PREÇO JSON-LD
# ============================================================

def extrair_preco_schema(soup):

    blocos = extrair_blocos_json_ld(
        soup
    )

    for bloco in blocos:

        if not isinstance(
            bloco,
            dict
        ):
            continue

        # Produto diretamente
        preco = bloco.get(
            "price"
        )

        if preco:

            formatado = formatar_preco(
                preco
            )

            if formatado:
                return formatado

        # Offers
        offers = bloco.get(
            "offers"
        )

        if isinstance(
            offers,
            list
        ):

            for oferta in offers:

                if not isinstance(
                    oferta,
                    dict
                ):
                    continue

                preco = (
                    oferta.get("price")
                    or
                    oferta.get("lowPrice")
                )

                if preco:

                    formatado = (
                        formatar_preco(
                            preco
                        )
                    )

                    if formatado:
                        return formatado

        elif isinstance(
            offers,
            dict
        ):

            preco = (
                offers.get("price")
                or
                offers.get("lowPrice")
            )

            if preco:

                formatado = formatar_preco(
                    preco
                )

                if formatado:
                    return formatado

    return ""


# ============================================================
# EXTRAÇÃO GENÉRICA DE PREÇO
# ============================================================

def extrair_preco_meta(soup):

    possiveis = [

        ("product:price:amount", "property"),
        ("og:price:amount", "property"),
        ("product:price", "property"),
        ("price", "name"),
        ("price", "itemprop"),
        ("lowPrice", "name"),
        ("priceAmount", "name")
    ]

    for nome, atributo in possiveis:

        try:

            meta = soup.find(
                "meta",
                attrs={
                    atributo: nome
                }
            )

            if not meta:
                continue

            valor = meta.get(
                "content",
                ""
            )

            preco = formatar_preco(
                valor
            )

            if preco:
                return preco

        except Exception:

            continue

    return ""


def extrair_preco_texto(soup):

    try:

        # Primeiro tenta elementos que normalmente
        # carregam preços.
        seletores = [

            "[class*='price']",

            "[class*='Price']",

            "[class*='amount']",

            "[class*='Amount']",

            "[itemprop='price']"
        ]

        candidatos = []

        for seletor in seletores:

            try:

                encontrados = soup.select(
                    seletor
                )

                candidatos.extend(
                    encontrados[:30]
                )

            except Exception:

                continue

        # Tenta os candidatos primeiro
        for elemento in candidatos:

            try:

                texto = elemento.get_text(
                    " ",
                    strip=True
                )

                if not texto:
                    continue

                encontrados = re.findall(
                    r"R\$\s*[\d\.,]+",
                    texto
                )

                for preco in encontrados:

                    valor = re.sub(
                        r"[^\d\.,]",
                        "",
                        preco
                    )

                    formatado = (
                        formatar_preco(
                            valor
                        )
                    )

                    if formatado:

                        numero = (
                            converter_preco_float(
                                formatado
                            )
                        )

                        if numero > 0:

                            return formatado

            except Exception:

                continue

        # Último recurso: página inteira
        texto = soup.get_text(
            " ",
            strip=True
        )

        encontrados = re.findall(
            r"R\$\s*[\d\.,]+",
            texto
        )

        for preco in encontrados:

            valor = re.sub(
                r"[^\d\.,]",
                "",
                preco
            )

            formatado = (
                formatar_preco(
                    valor
                )
            )

            if formatado:

                numero = (
                    converter_preco_float(
                        formatado
                    )
                )

                if numero > 0:

                    return formatado

    except Exception:

        pass

    return ""


# ============================================================
# EXTRAÇÃO DE TÍTULO
# ============================================================

def extrair_titulo(soup):

    # ========================================================
    # OG TITLE
    # ========================================================

    meta = soup.find(
        "meta",
        property="og:title"
    )

    if meta:

        titulo = limpar_texto(
            meta.get(
                "content",
                ""
            )
        )

        if titulo:

            return titulo

    # ========================================================
    # TWITTER
    # ========================================================

    meta = soup.find(
        "meta",
        attrs={
            "name": "twitter:title"
        }
    )

    if meta:

        titulo = limpar_texto(
            meta.get(
                "content",
                ""
            )
        )

        if titulo:

            return titulo

    # ========================================================
    # JSON-LD
    # ========================================================

    blocos = extrair_blocos_json_ld(
        soup
    )

    for bloco in blocos:

        if not isinstance(
            bloco,
            dict
        ):
            continue

        titulo = (
            bloco.get("name")
            or
            bloco.get("headline")
        )

        if titulo:

            titulo = limpar_texto(
                titulo
            )

            if titulo:

                return titulo

    # ========================================================
    # H1
    # ========================================================

    h1 = soup.find(
        "h1"
    )

    if h1:

        titulo = limpar_texto(
            h1.get_text(
                " ",
                strip=True
            )
        )

        if titulo:

            return titulo

    # ========================================================
    # TITLE
    # ========================================================

    title = soup.find(
        "title"
    )

    if title:

        titulo = limpar_texto(
            title.get_text(
                " ",
                strip=True
            )
        )

        if titulo:

            return titulo

    return "Oferta Imperdível"


# ============================================================
# EXTRAÇÃO DE IMAGEM
# ============================================================

def extrair_imagem(soup):

    # ========================================================
    # OG IMAGE
    # ========================================================

    meta = soup.find(
        "meta",
        property="og:image"
    )

    if meta:

        imagem = normalizar_url(
            meta.get(
                "content",
                ""
            )
        )

        if imagem.startswith(
            "http"
        ):

            return imagem

    # ========================================================
    # OG IMAGE SECUNDÁRIA
    # ========================================================

    metas = soup.find_all(
        "meta",
        property=re.compile(
            r"og:image",
            re.I
        )
    )

    for meta in metas:

        imagem = normalizar_url(
            meta.get(
                "content",
                ""
            )
        )

        if imagem.startswith(
            "http"
        ):

            return imagem

    # ========================================================
    # TWITTER
    # ========================================================

    meta = soup.find(
        "meta",
        attrs={
            "name": "twitter:image"
        }
    )

    if meta:

        imagem = normalizar_url(
            meta.get(
                "content",
                ""
            )
        )

        if imagem.startswith(
            "http"
        ):

            return imagem

    # ========================================================
    # JSON-LD
    # ========================================================

    blocos = extrair_blocos_json_ld(
        soup
    )

    for bloco in blocos:

        if not isinstance(
            bloco,
            dict
        ):
            continue

        imagem = bloco.get(
            "image"
        )

        if isinstance(
            imagem,
            list
        ):

            for item in imagem:

                item = normalizar_url(
                    item
                )

                if item.startswith(
                    "http"
                ):

                    return item

        elif isinstance(
            imagem,
            str
        ):

            imagem = normalizar_url(
                imagem
            )

            if imagem.startswith(
                "http"
            ):

                return imagem

        elif isinstance(
            imagem,
            dict
        ):

            imagem = (
                imagem.get("url")
                or
                imagem.get("contentUrl")
                or
                ""
            )

            imagem = normalizar_url(
                imagem
            )

            if imagem.startswith(
                "http"
            ):

                return imagem

    # ========================================================
    # IMAGENS DA PÁGINA
    # ========================================================

    imagens = soup.find_all(
        "img"
    )

    candidatos = []

    for img in imagens:

        for atributo in [
            "src",
            "data-src",
            "data-original",
            "data-lazy",
            "data-lazy-src"
        ]:

            imagem = img.get(
                atributo,
                ""
            )

            imagem = normalizar_url(
                imagem
            )

            if not imagem.startswith(
                "http"
            ):
                continue

            candidatos.append(
                imagem
            )

    # Prioriza imagens relacionadas à Shopee
    for imagem in candidatos:

        imagem_lower = imagem.lower()

        if (
            "shopee" in imagem_lower
            or
            "susercontent" in imagem_lower
        ):

            return imagem

    # Qualquer imagem HTTP válida
    for imagem in candidatos:

        if imagem.startswith(
            "http"
        ):

            return imagem

    return ""


# ============================================================
# EXTRAÇÃO DE PREÇO ANTIGO
# ============================================================

def extrair_preco_antigo(soup):

    seletores = [

        "s",

        "del",

        ".price-original",

        ".original-price",

        ".old-price",

        ".previous-price",

        ".andes-money-amount--previous",

        "[class*='original']",

        "[class*='Original']",

        "[class*='old-price']",

        "[class*='oldPrice']",

        "[class*='previous']",

        "[class*='Previous']"
    ]

    for seletor in seletores:

        try:

            elementos = soup.select(
                seletor
            )

            for elemento in elementos:

                texto = elemento.get_text(
                    " ",
                    strip=True
                )

                encontrados = re.findall(
                    r"R\$\s*[\d\.,]+",
                    texto
                )

                if encontrados:

                    preco = encontrados[0]

                    valor = (
                        converter_preco_float(
                            preco
                        )
                    )

                    if valor > 0:

                        return preco

        except Exception:

            continue

    return ""


# ============================================================
# EXTRAÇÃO PRINCIPAL DO PRODUTO
# ============================================================

def extrair_dados_produto(link):

    print(
        "========================================"
    )

    print(
        "[PRODUTO] Iniciando extração"
    )

    print(
        "[PRODUTO] Link:",
        link
    )

    try:

        # ====================================================
        # PRIMEIRA REQUISIÇÃO
        # ====================================================

        resposta = session.get(
            link,
            timeout=30,
            allow_redirects=True
        )

        print(
            "[PRODUTO] HTTP:",
            resposta.status_code
        )

        print(
            "[PRODUTO] URL final:",
            resposta.url
        )

        if resposta.status_code != 200:

            return {

                "sucesso": False,

                "erro":
                    (
                        "Não foi possível acessar a página "
                        f"do produto. HTTP {resposta.status_code}"
                    )
            }

        # ====================================================
        # HTML
        # ====================================================

        soup = BeautifulSoup(
            resposta.text,
            "html.parser"
        )

        # ====================================================
        # TÍTULO
        # ====================================================

        titulo = extrair_titulo(
            soup
        )

        # ====================================================
        # IMAGEM
        # ====================================================

        foto_url = extrair_imagem(
            soup
        )

        # ====================================================
        # PREÇO
        # ====================================================

        preco_atual = ""

        # 1. JSON-LD
        preco_atual = (
            extrair_preco_schema(
                soup
            )
        )

        # 2. Meta tags
        if not preco_atual:

            preco_atual = (
                extrair_preco_meta(
                    soup
                )
            )

        # 3. HTML/texto
        if not preco_atual:

            preco_atual = (
                extrair_preco_texto(
                    soup
                )
            )

        # ====================================================
        # PREÇO ANTIGO
        # ====================================================

        preco_antigo = (
            extrair_preco_antigo(
                soup
            )
        )

        # ====================================================
        # VALIDAÇÃO DOS PREÇOS
        # ====================================================

        valor_atual = (
            converter_preco_float(
                preco_atual
            )
        )

        valor_antigo = (
            converter_preco_float(
                preco_antigo
            )
        )

        if (
            valor_antigo <= 0
            or
            valor_antigo <= valor_atual
        ):

            preco_antigo = ""

        # ====================================================
        # LOG
        # ====================================================

        print(
            "[PRODUTO] Título:",
            titulo
        )

        print(
            "[PRODUTO] Preço atual:",
            preco_atual
        )

        print(
            "[PRODUTO] Preço antigo:",
            preco_antigo
        )

        print(
            "[PRODUTO] Imagem:",
            foto_url
        )

        print(
            "========================================"
        )

        # ====================================================
        # RETORNO
        # ====================================================

        return {

            "sucesso":
                True,

            "titulo":
                titulo,

            "preco_atual":
                preco_atual,

            "preco_antigo":
                preco_antigo,

            "imagem":
                foto_url,

            "link":
                link
        }

    except requests.RequestException as erro:

        print(
            "[PRODUTO] Erro HTTP:",
            erro
        )

        return {

            "sucesso":
                False,

            "erro":
                f"Erro ao acessar o produto: {erro}"
        }

    except Exception as erro:

        print(
            "[PRODUTO] Erro:",
            erro
        )

        return {

            "sucesso":
                False,

            "erro":
                f"Erro ao extrair dados: {erro}"
        }


# ============================================================
# TELEGRAM - ENVIO DE TEXTO
# ============================================================

def telegram_enviar_mensagem(
    texto,
    canal,
    reply_markup=None
):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {

            "ok": False,

            "erro":
                "BOT_TOKEN não está disponível."
        }

    if not canal:

        return {

            "ok": False,

            "erro":
                "CHANNEL_USERNAME não configurado."
        }

    try:

        payload = {

            "chat_id":
                canal,

            "text":
                texto,

            "parse_mode":
                "HTML",

            "disable_web_page_preview":
                True
        }

        if reply_markup:

            payload[
                "reply_markup"
            ] = reply_markup

        resposta = requests.post(
            telegram_api_url(
                "sendMessage"
            ),
            json=payload,
            timeout=30
        )

        try:

            return resposta.json()

        except Exception:

            return {

                "ok":
                    False,

                "erro":
                    (
                        "Telegram retornou HTTP "
                        f"{resposta.status_code}"
                    )
            }

    except requests.RequestException as erro:

        return {

            "ok":
                False,

            "erro":
                f"Erro de conexão com Telegram: {erro}"
        }


# ============================================================
# TELEGRAM - ENVIO DE FOTO POR URL
# ============================================================

def telegram_enviar_foto_url(
    foto,
    legenda,
    canal,
    reply_markup=None
):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {

            "ok":
                False,

            "erro":
                "BOT_TOKEN não está disponível."
        }

    if not canal:

        return {

            "ok":
                False,

            "erro":
                "CHANNEL_USERNAME não configurado."
        }

    if not foto:

        return {

            "ok":
                False,

            "erro":
                "URL da imagem não encontrada."
        }

    try:

        payload = {

            "chat_id":
                canal,

            "photo":
                foto,

            "caption":
                legenda,

            "parse_mode":
                "HTML"
        }

        if reply_markup:

            payload[
                "reply_markup"
            ] = reply_markup

        resposta = requests.post(

            telegram_api_url(
                "sendPhoto"
            ),

            json=payload,

            timeout=40
        )

        try:

            return resposta.json()

        except Exception:

            return {

                "ok":
                    False,

                "erro":
                    (
                        "Telegram retornou HTTP "
                        f"{resposta.status_code}"
                    )
            }

    except requests.RequestException as erro:

        print(
            "[TELEGRAM] Erro imagem:",
            erro
        )

        return {

            "ok":
                False,

            "erro":
                str(erro)
        }


# ============================================================
# TELEGRAM - ENVIO DE FOTO POR DOWNLOAD
# ============================================================

def telegram_enviar_foto_download(
    foto,
    legenda,
    canal,
    reply_markup=None
):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {

            "ok":
                False,

            "erro":
                "BOT_TOKEN não está disponível."
        }

    try:

        resposta_imagem = session.get(
            foto,
            timeout=30,
            headers={
                "User-Agent":
                    (
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    )
            }
        )

        if resposta_imagem.status_code != 200:

            return {

                "ok":
                    False,

                "erro":
                    (
                        "Não foi possível baixar a imagem. "
                        f"HTTP {resposta_imagem.status_code}"
                    )
            }

        content_type = (
            resposta_imagem.headers.get(
                "Content-Type",
                ""
            )
        )

        extensao = ".jpg"

        if "png" in content_type.lower():
            extensao = ".png"

        elif "webp" in content_type.lower():
            extensao = ".webp"

        elif "gif" in content_type.lower():
            extensao = ".gif"

        files = {

            "photo":
                (
                    "produto" + extensao,
                    resposta_imagem.content,
                    content_type or "image/jpeg"
                )
        }

        data = {

            "chat_id":
                canal,

            "caption":
                legenda,

            "parse_mode":
                "HTML"
        }

        if reply_markup:

            data[
                "reply_markup"
            ] = json.dumps(
                reply_markup
            )

        resposta = requests.post(

            telegram_api_url(
                "sendPhoto"
            ),

            data=data,

            files=files,

            timeout=50
        )

        try:

            return resposta.json()

        except Exception:

            return {

                "ok":
                    False,

                "erro":
                    (
                        "Telegram retornou HTTP "
                        f"{resposta.status_code}"
                    )
            }

    except Exception as erro:

        print(
            "[TELEGRAM] Erro download foto:",
            erro
        )

        return {

            "ok":
                False,

            "erro":
                str(erro)
        }


# ============================================================
# DEBUG TELEGRAM
# ============================================================

@app.route(
    "/debug-telegram",
    methods=["GET"]
)
def debug_telegram():

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    canal = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()

    resultado = telegram_get_me()

    bot = None

    if resultado.get("ok"):

        bot = resultado.get(
            "result"
        )

    return jsonify({

        "BOT_TOKEN_existe":
            bool(token),

        "BOT_TOKEN_tamanho":
            len(token),

        "CHANNEL_USERNAME":
            canal,

        "CHANNEL_USERNAME_existe":
            bool(canal),

        "telegram_api_ok":
            resultado.get(
                "ok",
                False
            ),

        "bot":
            bot,

        "erro":
            resultado.get(
                "erro"
            )
            or
            resultado.get(
                "description"
            )
    })


# ============================================================
# DEBUG ENV
# ============================================================

@app.route(
    "/debug-env",
    methods=["GET"]
)
def debug_env():

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    )

    channel = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    )

    return jsonify({

        "BOT_TOKEN_existe":
            bool(token),

        "BOT_TOKEN_tamanho":
            len(token),

        "CHANNEL_USERNAME_existe":
            bool(channel),

        "CHANNEL_USERNAME":
            channel,

        "PORT":
            os.environ.get(
                "PORT",
                ""
            ),

        "telegram_configurado":
            bool(token),

        "canal_configurado":
            bool(channel)
    })


# ============================================================
# HEALTH
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    channel = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()

    return jsonify({

        "status":
            "ok",

        "service":
            "raposa-cacadora",

        "telegram_configurado":
            bool(token),

        "canal_configurado":
            bool(channel),

        "timestamp":
            int(time.time())
    })


# ============================================================
# TELEGRAM INIT DATA
# ============================================================

def validar_init_data(init_data):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:
        return False

    if not init_data:
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

            token.encode(
                "utf-8"
            ),

            hashlib.sha256

        ).digest()

        hash_calculado = hmac.new(

            secret_key,

            data_check_string.encode(
                "utf-8"
            ),

            hashlib.sha256

        ).hexdigest()

        return hmac.compare_digest(

            hash_calculado,

            hash_recebido
        )

    except Exception as erro:

        print(
            "[TELEGRAM] Erro initData:",
            erro
        )

        return False


def obter_usuario(init_data):

    if not init_data:
        return None

    try:

        dados = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        usuario = dados.get(
            "user"
        )

        if not usuario:
            return None

        return json.loads(
            usuario
        )

    except Exception as erro:

        print(
            "[TELEGRAM] Erro usuário:",
            erro
        )

        return None


# ============================================================
# SHOPEE
# ============================================================

def link_shopee_valido(link):

    if not isinstance(
        link,
        str
    ):
        return False

    link = link.strip()

    if not link:
        return False

    link_lower = link.lower()

    if not (
        link_lower.startswith(
            "http://"
        )
        or
        link_lower.startswith(
            "https://"
        )
    ):

        return False

    try:

        dominio = (
            urlparse(
                link
            ).netloc.lower()
        )

    except Exception:

        return False

    # Aceita domínios da Shopee.
    #
    # Também aceita links encurtados que contenham
    # "shopee" no domínio.
    return (
        "shopee." in dominio
        or
        "shopee" in dominio
    )


# ============================================================
# TAREFAS
# ============================================================

def criar_tarefa(
    links,
    intervalo,
    quantidade,
    usuario
):

    task_id = str(
        uuid.uuid4()
    )

    tarefa = {

        "id":
            task_id,

        "usuario":
            usuario,

        "links":
            links,

        "intervalo":
            intervalo,

        "quantidade":
            quantidade,

        "produto_atual":
            0,

        "produto_link":
            "",

        "progresso":
            0,

        "status":
            "iniciando",

        "cancelada":
            False,

        "resultados":
            [],

        "criada_em":
            time.time()
    }

    with tarefas_lock:

        tarefas[
            task_id
        ] = tarefa

    return task_id


# ============================================================
# PUBLICAÇÃO REAL NO TELEGRAM
# ============================================================

def publicar_produto(
    link,
    usuario
):

    canal = os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()

    if not canal:

        return {

            "sucesso":
                False,

            "mensagem":
                "CHANNEL_USERNAME não configurado."
        }

    print(
        "----------------------------------------"
    )

    print(
        "[TELEGRAM] Processando produto"
    )

    print(
        "[TELEGRAM] Usuário:",
        usuario
    )

    print(
        "[TELEGRAM] Canal:",
        canal
    )

    print(
        "[TELEGRAM] Link:",
        link
    )

    print(
        "----------------------------------------"
    )

    # ========================================================
    # EXTRAI DADOS
    # ========================================================

    dados = extrair_dados_produto(
        link
    )

    if not dados.get(
        "sucesso"
    ):

        return {

            "sucesso":
                False,

            "mensagem":
                dados.get(
                    "erro",
                    (
                        "Não foi possível obter "
                        "os dados do produto."
                    )
                )
        }

    titulo = dados.get(
        "titulo",
        "Oferta Imperdível"
    )

    preco_atual = dados.get(
        "preco_atual",
        ""
    )

    preco_antigo = dados.get(
        "preco_antigo",
        ""
    )

    foto_url = dados.get(
        "imagem",
        ""
    )

    # ========================================================
    # ESCAPA TÍTULO
    # ========================================================

    titulo_html = escapar_html(
        titulo
    )

    # ========================================================
    # PREÇOS
    # ========================================================

    valor_atual = (
        converter_preco_float(
            preco_atual
        )
    )

    valor_antigo = (
        converter_preco_float(
            preco_antigo
        )
    )

    if (
        preco_antigo
        and
        valor_antigo > valor_atual
        and
        valor_atual > 0
    ):

        bloco_preco = (

            f"💰 <s>De: {escapar_html(preco_antigo)}</s>\n"

            f"🔥 <b>POR APENAS: "
            f"{escapar_html(preco_atual)}!</b>"
        )

    elif preco_atual:

        bloco_preco = (

            f"💰 <b>POR APENAS: "
            f"{escapar_html(preco_atual)}!</b>"
        )

    else:

        bloco_preco = (

            "💰 <b>Confira o preço "
            "especial da oferta!</b>"
        )

    # ========================================================
    # LEGENDA
    # ========================================================

    legenda = (

        "🔥 <b>OFERTA IMPERDÍVEL!</b> 🔥\n\n"

        f"📦 <b>{titulo_html}</b>\n\n"

        f"{bloco_preco}\n\n"

        "🚨 <b>Corre porque essa oferta pode acabar "
        "a qualquer momento!</b>\n\n"

        "👇 <b>APROVEITE AGORA!</b>\n\n"

        "🦊 <b>Raposa Caçadora</b>"
    )

    # ========================================================
    # BOTÃO DE COMPRA
    # ========================================================

    reply_markup = {

        "inline_keyboard": [

            [

                {

                    "text":
                        "🛒 COMPRAR AGORA",

                    "url":
                        link
                }

            ]

        ]
    }

    # ========================================================
    # ENVIA FOTO
    # ========================================================

    resultado = None

    if (
        foto_url
        and
        foto_url.startswith(
            "http"
        )
    ):

        print(
            "[TELEGRAM] Tentando enviar foto por URL..."
        )

        resultado = telegram_enviar_foto_url(

            foto=foto_url,

            legenda=legenda,

            canal=canal,

            reply_markup=reply_markup
        )

        # ====================================================
        # FALLBACK
        # ====================================================

        if not resultado.get(
            "ok"
        ):

            print(
                "[TELEGRAM] URL da imagem falhou."
            )

            print(
                "[TELEGRAM] Tentando baixar a imagem..."
            )

            resultado = (
                telegram_enviar_foto_download(

                    foto=foto_url,

                    legenda=legenda,

                    canal=canal,

                    reply_markup=reply_markup
                )
            )

    # ========================================================
    # SEM FOTO OU FOTO FALHOU
    # ========================================================

    if (
        not resultado
        or
        not resultado.get(
            "ok"
        )
    ):

        print(
            "[TELEGRAM] Enviando mensagem sem foto."
        )

        resultado = telegram_enviar_mensagem(

            texto=legenda,

            canal=canal,

            reply_markup=reply_markup
        )

    # ========================================================
    # ERRO TELEGRAM
    # ========================================================

    if not resultado.get(
        "ok"
    ):

        erro = (

            resultado.get(
                "description"
            )

            or

            resultado.get(
                "erro"
            )

            or

            "Erro desconhecido do Telegram."
        )

        print(
            "[TELEGRAM] ERRO:",
            erro
        )

        return {

            "sucesso":
                False,

            "mensagem":
                erro
        }

    # ========================================================
    # RESULTADO
    # ========================================================

    mensagem_telegram = resultado.get(
        "result",
        {}
    )

    message_id = (
        mensagem_telegram.get(
            "message_id"
        )
    )

    print(
        "[TELEGRAM] Produto publicado:",
        message_id
    )

    return {

        "sucesso":
            True,

        "mensagem":
            "Produto publicado no canal.",

        "message_id":
            message_id,

        "titulo":
            titulo,

        "preco_atual":
            preco_atual,

        "preco_antigo":
            preco_antigo,

        "imagem":
            foto_url
    }


# ============================================================
# WORKER
# ============================================================

def executar_tarefa(
    task_id
):

    print(
        f"[TASK] Iniciando {task_id}"
    )

    while True:

        with tarefas_lock:

            tarefa = tarefas.get(
                task_id
            )

            if not tarefa:
                return

            if tarefa[
                "cancelada"
            ]:

                tarefa[
                    "status"
                ] = "cancelada"

                return

            indice = tarefa[
                "produto_atual"
            ]

            links = list(
                tarefa[
                    "links"
                ]
            )

            quantidade = tarefa[
                "quantidade"
            ]

            usuario = tarefa[
                "usuario"
            ]

            intervalo = tarefa[
                "intervalo"
            ]

        # ====================================================
        # FINALIZAÇÃO
        # ====================================================

        if indice >= quantidade:

            with tarefas_lock:

                tarefa = tarefas.get(
                    task_id
                )

                if tarefa:

                    tarefa[
                        "status"
                    ] = "concluida"

                    tarefa[
                        "progresso"
                    ] = 100

                    tarefa[
                        "produto_atual"
                    ] = quantidade

                    tarefa[
                        "produto_link"
                    ] = ""

            print(
                f"[TASK] Finalizada {task_id}"
            )

            return

        # ====================================================
        # PRODUTO
        # ====================================================

        link = links[
            indice
        ]

        numero_produto = (
            indice + 1
        )

        with tarefas_lock:

            tarefa = tarefas.get(
                task_id
            )

            if not tarefa:
                return

            tarefa[
                "status"
            ] = "processando"

            tarefa[
                "produto_link"
            ] = link

            tarefa[
                "progresso"
            ] = round(

                (
                    indice
                    /
                    quantidade
                )
                *
                100
            )

        # ====================================================
        # PUBLICAÇÃO
        # ====================================================

        try:

            resultado = publicar_produto(

                link,

                usuario
            )

            sucesso = resultado.get(
                "sucesso",
                False
            )

        except Exception as erro:

            print(
                "[PUBLICAÇÃO] Erro:",
                erro
            )

            sucesso = False

            resultado = {

                "mensagem":
                    str(erro)
            }

        # ====================================================
        # SALVA RESULTADO
        # ====================================================

        with tarefas_lock:

            tarefa = tarefas.get(
                task_id
            )

            if not tarefa:
                return

            if tarefa[
                "cancelada"
            ]:

                tarefa[
                    "status"
                ] = "cancelada"

                return

            if sucesso:

                tarefa[
                    "resultados"
                ].append({

                    "produto":
                        numero_produto,

                    "link":
                        link,

                    "status":
                        "postado",

                    "message_id":
                        resultado.get(
                            "message_id"
                        ),

                    "titulo":
                        resultado.get(
                            "titulo"
                        ),

                    "preco_atual":
                        resultado.get(
                            "preco_atual"
                        ),

                    "preco_antigo":
                        resultado.get(
                            "preco_antigo"
                        )
                })

                tarefa[
                    "produto_atual"
                ] = numero_produto

                tarefa[
                    "progresso"
                ] = round(

                    (
                        numero_produto
                        /
                        quantidade
                    )
                    *
                    100
                )

                tarefa[
                    "status"
                ] = "aguardando"

            else:

                tarefa[
                    "resultados"
                ].append({

                    "produto":
                        numero_produto,

                    "link":
                        link,

                    "status":
                        "erro",

                    "mensagem":
                        resultado.get(
                            "mensagem",
                            "Erro desconhecido."
                        )
                })

                tarefa[
                    "produto_atual"
                ] = numero_produto

                tarefa[
                    "progresso"
                ] = round(

                    (
                        numero_produto
                        /
                        quantidade
                    )
                    *
                    100
                )

                tarefa[
                    "status"
                ] = "erro"

        # ====================================================
        # ERRO
        # ====================================================

        if not sucesso:

            # Continua para o próximo produto
            time.sleep(
                1
            )

            continue

        # ====================================================
        # ÚLTIMO PRODUTO
        # ====================================================

        if numero_produto >= quantidade:

            with tarefas_lock:

                tarefa = tarefas.get(
                    task_id
                )

                if tarefa:

                    tarefa[
                        "status"
                    ] = "concluida"

                    tarefa[
                        "progresso"
                    ] = 100

                    tarefa[
                        "produto_link"
                    ] = ""

            print(
                f"[TASK] Finalizada {task_id}"
            )

            return

        # ====================================================
        # INTERVALO
        # ====================================================

        with tarefas_lock:

            tarefa = tarefas.get(
                task_id
            )

            if tarefa:

                tarefa[
                    "status"
                ] = "aguardando"

        segundos_restantes = intervalo

        while segundos_restantes > 0:

            with tarefas_lock:

                tarefa = tarefas.get(
                    task_id
                )

                if not tarefa:
                    return

                if tarefa[
                    "cancelada"
                ]:

                    tarefa[
                        "status"
                    ] = "cancelada"

                    return

            time.sleep(
                1
            )

            segundos_restantes -= 1


# ============================================================
# PÁGINA
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# CONFIGURAR
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    try:

        dados = request.get_json(
            silent=True
        )

        if not dados:

            return jsonify({

                "erro":
                    "JSON inválido."
            }), 400

        # ====================================================
        # TOKEN
        # ====================================================

        token = os.environ.get(
            "BOT_TOKEN",
            ""
        ).strip()

        if not token:

            return jsonify({

                "erro":
                    (
                        "BOT_TOKEN não está disponível "
                        "para o processo do Render."
                    )
            }), 500

        # ====================================================
        # CANAL
        # ====================================================

        canal = os.environ.get(
            "CHANNEL_USERNAME",
            ""
        ).strip()

        if not canal:

            return jsonify({

                "erro":
                    (
                        "CHANNEL_USERNAME não está disponível "
                        "para o processo do Render."
                    )
            }), 500

        # ====================================================
        # INIT DATA
        # ====================================================

        init_data = dados.get(
            "initData",
            ""
        )

        exigir_init_data = os.environ.get(
            "TELEGRAM_INIT_DATA_REQUIRED",
            "false"
        ).strip().lower()

        if exigir_init_data in (
            "1",
            "true",
            "yes",
            "sim"
        ):

            if not validar_init_data(
                init_data
            ):

                return jsonify({

                    "erro":
                        "Sessão do Telegram inválida."
                }), 401

        usuario = obter_usuario(
            init_data
        )

        if not usuario:

            usuario = dados.get(
                "user"
            )

        # ====================================================
        # LINKS
        # ====================================================

        links = dados.get(
            "links",
            []
        )

        if not isinstance(
            links,
            list
        ):

            return jsonify({

                "erro":
                    "A lista de produtos é inválida."
            }), 400

        links = [

            str(link).strip()

            for link in links

            if str(link).strip()
        ]

        if not links:

            return jsonify({

                "erro":
                    "Adicione pelo menos um produto."
            }), 400

        if len(links) > MAX_LINKS:

            return jsonify({

                "erro":
                    "Máximo de 20 produtos."
            }), 400

        # ====================================================
        # VALIDAÇÃO DOS LINKS
        # ====================================================

        invalidos = [

            link

            for link in links

            if not link_shopee_valido(
                link
            )
        ]

        if invalidos:

            return jsonify({

                "erro":
                    (
                        "Um ou mais links não são "
                        "links válidos da Shopee."
                    ),

                "links_invalidos":
                    invalidos[:5]
            }), 400

        # ====================================================
        # QUANTIDADE
        # ====================================================

        try:

            quantidade = int(
                dados.get(
                    "quantidade",
                    1
                )
            )

        except Exception:

            return jsonify({

                "erro":
                    "Quantidade inválida."
            }), 400

        if quantidade < 1:

            return jsonify({

                "erro":
                    "A quantidade mínima é 1."
            }), 400

        if quantidade > len(links):

            return jsonify({

                "erro":
                    (
                        "A quantidade não pode ser "
                        "maior que os produtos."
                    )
            }), 400

        if quantidade > MAX_LINKS:

            return jsonify({

                "erro":
                    "Máximo de 20 postagens."
            }), 400

        # ====================================================
        # INTERVALO
        # ====================================================

        try:

            intervalo = int(
                dados.get(
                    "intervalo",
                    10
                )
            )

        except Exception:

            return jsonify({

                "erro":
                    "Intervalo inválido."
            }), 400

        if intervalo not in INTERVALOS_PERMITIDOS:

            return jsonify({

                "erro":
                    "Intervalo selecionado é inválido."
            }), 400

        # ====================================================
        # LIMITA LINKS
        # ====================================================

        links = links[
            :quantidade
        ]

        # ====================================================
        # CRIA TAREFA
        # ====================================================

        task_id = criar_tarefa(

            links=links,

            intervalo=intervalo,

            quantidade=quantidade,

            usuario=usuario
        )

        # ====================================================
        # THREAD
        # ====================================================

        thread = threading.Thread(

            target=executar_tarefa,

            args=(task_id,),

            daemon=True
        )

        thread.start()

        # ====================================================
        # RESPOSTA
        # ====================================================

        return jsonify({

            "sucesso":
                True,

            "mensagem":
                "Automação iniciada com sucesso.",

            "task_id":
                task_id,

            "quantidade":
                quantidade,

            "intervalo":
                intervalo,

            "canal":
                canal
        })

    except Exception as erro:

        print(
            "Erro /api/configurar:",
            erro
        )

        return jsonify({

            "erro":
                "Erro interno do servidor.",

            "detalhes":
                str(erro)

        }), 500


# ============================================================
# STATUS
# ============================================================

@app.route(
    "/api/status/<task_id>",
    methods=["GET"]
)
def status(task_id):

    with tarefas_lock:

        tarefa = tarefas.get(
            task_id
        )

        if not tarefa:

            return jsonify({

                "erro":
                    "Tarefa não encontrada."
            }), 404

        return jsonify({

            "id":
                tarefa["id"],

            "status":
                tarefa["status"],

            "progresso":
                tarefa["progresso"],

            "produto":
                tarefa["produto_atual"],

            "total":
                tarefa["quantidade"],

            "produto_link":
                tarefa["produto_link"],

            "resultados":
                tarefa["resultados"]
        })


# ============================================================
# PARAR
# ============================================================

@app.route(
    "/api/parar/<task_id>",
    methods=["POST"]
)
def parar(task_id):

    with tarefas_lock:

        tarefa = tarefas.get(
            task_id
        )

        if not tarefa:

            return jsonify({

                "erro":
                    "Tarefa não encontrada."
            }), 404

        tarefa[
            "cancelada"
        ] = True

        tarefa[
            "status"
        ] = "cancelada"

    return jsonify({

        "sucesso":
            True,

        "mensagem":
            "Automação interrompida."
    })


# ============================================================
# EXECUÇÃO LOCAL / RENDER
# ============================================================

if __name__ == "__main__":

    port = int(

        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(

        host="0.0.0.0",

        port=port
    )
