import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re

from urllib.parse import parse_qsl, urlparse, unquote

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

def criar_sessao():

    sessao = requests.Session()

    sessao.headers.update({

        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),

        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,image/apng,*/*;q=0.8"
        ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache",

        "Upgrade-Insecure-Requests":
            "1",

        "Sec-Fetch-Dest":
            "document",

        "Sec-Fetch-Mode":
            "navigate",

        "Sec-Fetch-Site":
            "none",

        "Sec-Fetch-User":
            "?1"
    })

    return sessao


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

    if texto is None:
        return ""

    texto = str(texto)

    texto = (
        texto
        .replace("\xa0", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def normalizar_url(url):

    if not url:
        return ""

    url = str(url).strip()

    url = (
        url
        .replace("\\/", "/")
        .replace("&amp;", "&")
    )

    return url.strip()


def formatar_preco(valor):

    if valor is None:
        return ""

    valor = str(valor).strip()

    if not valor:
        return ""

    valor = (
        valor
        .replace("R$", "")
        .replace("BRL", "")
        .replace("brl", "")
        .replace(" ", "")
    )

    # Remove símbolos estranhos, mantendo números,
    # ponto e vírgula.
    valor = re.sub(
        r"[^\d\.,]",
        "",
        valor
    )

    if not valor:
        return ""

    try:

        # Formato brasileiro:
        # 1.299,90
        if "," in valor:

            valor = valor.replace(
                ".",
                ""
            )

            valor = valor.replace(
                ",",
                "."
            )

        # Formato internacional:
        # 1299.90
        numero = float(valor)

        if numero <= 0:
            return ""

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

    if preco_str is None:
        return 0.0

    preco_str = str(preco_str).strip()

    if not preco_str:
        return 0.0

    try:

        limpo = (
            preco_str
            .replace("R$", "")
            .replace("BRL", "")
            .replace("brl", "")
            .replace(" ", "")
        )

        # Se tiver vírgula, assumimos formato BR.
        if "," in limpo:

            limpo = limpo.replace(
                ".",
                ""
            )

            limpo = limpo.replace(
                ",",
                "."
            )

        else:

            # Mantém decimal com ponto.
            limpo = re.sub(
                r"[^\d.]",
                "",
                limpo
            )

        return float(limpo)

    except Exception:

        return 0.0


def extrair_numero_preco(texto):

    if not texto:
        return ""

    texto = limpar_texto(texto)

    # Primeiro procura R$.
    encontrado = re.search(
        r"R\$\s*([0-9][0-9\.,]*)",
        texto,
        re.IGNORECASE
    )

    if encontrado:

        return formatar_preco(
            encontrado.group(1)
        )

    # Depois procura valores com vírgula decimal.
    encontrado = re.search(
        r"\b([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})\b",
        texto
    )

    if encontrado:

        return formatar_preco(
            encontrado.group(1)
        )

    # Depois números decimais simples.
    encontrado = re.search(
        r"\b([0-9]+\.[0-9]{2})\b",
        texto
    )

    if encontrado:

        return formatar_preco(
            encontrado.group(1)
        )

    return ""


# ============================================================
# JSON RECURSIVO
# ============================================================

def percorrer_json(valor):

    if isinstance(valor, dict):

        yield valor

        for item in valor.values():

            yield from percorrer_json(item)

    elif isinstance(valor, list):

        for item in valor:

            yield from percorrer_json(item)


# ============================================================
# EXTRAÇÃO DE JSON-LD
# ============================================================

def extrair_json_ld(soup):

    blocos = []

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        try:

            conteudo = script.string

            if not conteudo:

                conteudo = script.get_text(
                    strip=True
                )

            if not conteudo:

                continue

            conteudo = conteudo.strip()

            dados = json.loads(
                conteudo
            )

            blocos.extend(
                list(
                    percorrer_json(
                        dados
                    )
                )
            )

        except Exception:

            continue

    return blocos


# ============================================================
# EXTRAÇÃO DE PREÇO DO JSON-LD
# ============================================================

def extrair_preco_schema(soup):

    blocos = extrair_json_ld(
        soup
    )

    for bloco in blocos:

        if not isinstance(
            bloco,
            dict
        ):
            continue

        # Product > offers
        offers = bloco.get(
            "offers"
        )

        if isinstance(
            offers,
            list
        ):

            ofertas = offers

        elif isinstance(
            offers,
            dict
        ):

            ofertas = [
                offers
            ]

        else:

            ofertas = []

        for oferta in ofertas:

            if not isinstance(
                oferta,
                dict
            ):
                continue

            preco = (
                oferta.get("price")
                or
                oferta.get("lowPrice")
                or
                oferta.get("highPrice")
            )

            if preco:

                resultado = formatar_preco(
                    preco
                )

                if resultado:

                    return resultado

        # Às vezes o próprio bloco contém price.
        preco = (
            bloco.get("price")
            or
            bloco.get("lowPrice")
        )

        if preco:

            resultado = formatar_preco(
                preco
            )

            if resultado:

                return resultado

    return ""


# ============================================================
# EXTRAÇÃO DE TÍTULO
# ============================================================

def extrair_titulo(soup):

    candidatos = []

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for bloco in extrair_json_ld(soup):

        if not isinstance(
            bloco,
            dict
        ):
            continue

        tipo = bloco.get(
            "@type",
            ""
        )

        nome = bloco.get(
            "name",
            ""
        )

        if nome:

            nome = limpar_texto(
                nome
            )

            if nome:

                # Prioriza Product.
                if (
                    tipo == "Product"
                    or
                    (
                        isinstance(
                            tipo,
                            list
                        )
                        and
                        "Product" in tipo
                    )
                ):

                    candidatos.insert(
                        0,
                        nome
                    )

                else:

                    candidatos.append(
                        nome
                    )

    # --------------------------------------------------------
    # META OG
    # --------------------------------------------------------

    metas = [

        ("property", "og:title"),

        ("name", "twitter:title"),

        ("name", "title")
    ]

    for atributo, valor in metas:

        meta = soup.find(
            "meta",
            attrs={
                atributo:
                    valor
            }
        )

        if meta:

            conteudo = limpar_texto(
                meta.get(
                    "content",
                    ""
                )
            )

            if conteudo:

                candidatos.append(
                    conteudo
                )

    # --------------------------------------------------------
    # H1
    # --------------------------------------------------------

    for h1 in soup.find_all(
        "h1"
    ):

        texto = limpar_texto(
            h1.get_text(
                " ",
                strip=True
            )
        )

        if texto:

            candidatos.append(
                texto
            )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = soup.find(
        "title"
    )

    if title:

        texto = limpar_texto(
            title.get_text(
                strip=True
            )
        )

        if texto:

            candidatos.append(
                texto
            )

    # --------------------------------------------------------
    # FILTROS
    # --------------------------------------------------------

    termos_genericos = [

        "shopee brasil",
        "ofertas incríveis",
        "ofertas incriveis",
        "melhores preços do mercado",
        "melhores precos do mercado",
        "compre na shopee",
        "shopee"
    ]

    vistos = set()

    for candidato in candidatos:

        candidato = limpar_texto(
            candidato
        )

        if not candidato:
            continue

        chave = candidato.lower()

        if chave in vistos:
            continue

        vistos.add(
            chave
        )

        # Ignora títulos claramente genéricos.
        if any(
            termo in chave
            for termo in termos_genericos
        ):

            continue

        # Evita título excessivamente pequeno.
        if len(candidato) < 4:
            continue

        return candidato

    return ""


# ============================================================
# EXTRAÇÃO DE IMAGEM
# ============================================================

def extrair_imagem(soup):

    candidatos = []

    # --------------------------------------------------------
    # OG IMAGE
    # --------------------------------------------------------

    for atributo, valor in [

        ("property", "og:image"),

        ("property", "og:image:url"),

        ("name", "twitter:image"),

        ("name", "twitter:image:src")

    ]:

        meta = soup.find(
            "meta",
            attrs={
                atributo:
                    valor
            }
        )

        if meta:

            url = normalizar_url(
                meta.get(
                    "content",
                    ""
                )
            )

            if url.startswith(
                "http"
            ):

                candidatos.append(
                    url
                )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for bloco in extrair_json_ld(soup):

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
            str
        ):

            candidatos.append(
                normalizar_url(
                    imagem
                )
            )

        elif isinstance(
            imagem,
            list
        ):

            for item in imagem:

                if isinstance(
                    item,
                    str
                ):

                    candidatos.append(
                        normalizar_url(
                            item
                        )
                    )

                elif isinstance(
                    item,
                    dict
                ):

                    url = item.get(
                        "url"
                    )

                    if url:

                        candidatos.append(
                            normalizar_url(
                                url
                            )
                        )

        elif isinstance(
            imagem,
            dict
        ):

            url = imagem.get(
                "url"
            )

            if url:

                candidatos.append(
                    normalizar_url(
                        url
                    )
                )

    # --------------------------------------------------------
    # IMAGENS HTML
    # --------------------------------------------------------

    for img in soup.find_all(
        "img"
    )[:50]:

        for atributo in [

            "data-src",
            "data-original",
            "data-lazy",
            "src"

        ]:

            url = normalizar_url(
                img.get(
                    atributo,
                    ""
                )
            )

            if url.startswith(
                "http"
            ):

                candidatos.append(
                    url
                )

    # --------------------------------------------------------
    # VALIDAÇÃO
    # --------------------------------------------------------

    vistos = set()

    for url in candidatos:

        if not url:
            continue

        if url in vistos:
            continue

        vistos.add(
            url
        )

        # Ignora SVGs e imagens minúsculas/generic.
        url_lower = url.lower()

        if url_lower.endswith(
            ".svg"
        ):
            continue

        return url

    return ""


# ============================================================
# EXTRAÇÃO DE PREÇO POR META
# ============================================================

def extrair_preco_meta(soup):

    atributos = [

        ("property", "product:price:amount"),

        ("property", "og:price:amount"),

        ("name", "product:price:amount"),

        ("name", "price"),

        ("itemprop", "price")

    ]

    for atributo, valor in atributos:

        elementos = soup.find_all(
            "meta",
            attrs={
                atributo:
                    valor
            }
        )

        for elemento in elementos:

            valor_preco = elemento.get(
                "content",
                ""
            )

            resultado = formatar_preco(
                valor_preco
            )

            if resultado:

                return resultado

    # Itemprop sem meta.
    elementos = soup.find_all(
        attrs={
            "itemprop":
                "price"
        }
    )

    for elemento in elementos:

        valor_preco = (
            elemento.get(
                "content"
            )
            or
            elemento.get_text(
                " ",
                strip=True
            )
        )

        resultado = formatar_preco(
            valor_preco
        )

        if resultado:

            return resultado

    return ""


# ============================================================
# EXTRAÇÃO DE PREÇO DO HTML
# ============================================================

def extrair_preco_html(soup):

    seletores = [

        ".andes-money-amount__fraction",

        ".ui-pdp-price__part",

        "[class*='price']",

        "[class*='Price']",

        "[class*='preco']",

        "[class*='Preco']"

    ]

    for seletor in seletores:

        try:

            elementos = soup.select(
                seletor
            )

        except Exception:

            continue

        for elemento in elementos[:30]:

            texto = limpar_texto(
                elemento.get_text(
                    " ",
                    strip=True
                )
            )

            if not texto:
                continue

            # Primeiro tenta R$.
            resultado = extrair_numero_preco(
                texto
            )

            if resultado:

                return resultado

    # Procura diretamente no texto da página.
    texto_total = limpar_texto(
        soup.get_text(
            " ",
            strip=True
        )
    )

    # Preços com R$.
    encontrados = re.findall(
        r"R\$\s*[0-9][0-9\.,]*",
        texto_total,
        re.IGNORECASE
    )

    for valor in encontrados:

        resultado = formatar_preco(
            valor
        )

        if resultado:

            numero = converter_preco_float(
                resultado
            )

            # Evita valores absurdos.
            if 0 < numero < 10000000:

                return resultado

    return ""


# ============================================================
# EXTRAÇÃO DE PREÇO
# ============================================================

def extrair_preco(soup):

    # 1. JSON-LD
    resultado = extrair_preco_schema(
        soup
    )

    if resultado:

        return resultado

    # 2. Meta
    resultado = extrair_preco_meta(
        soup
    )

    if resultado:

        return resultado

    # 3. Classes HTML
    resultado = extrair_preco_html(
        soup
    )

    if resultado:

        return resultado

    return ""


# ============================================================
# PREÇO ANTIGO
# ============================================================

def extrair_preco_antigo(soup, preco_atual):

    valor_atual = converter_preco_float(
        preco_atual
    )

    candidatos = []

    # --------------------------------------------------------
    # ELEMENTOS COM INDÍCIO DE PREÇO ANTERIOR
    # --------------------------------------------------------

    seletores = [

        "s",

        "del",

        ".andes-money-amount--previous",

        ".ui-pdp-price__part--old",

        ".ui-pdp-price__original-value",

        "[class*='previous']",

        "[class*='Previous']",

        "[class*='old-price']",

        "[class*='oldPrice']",

        "[class*='original']",

        "[class*='Original']",

        "[class*='list-price']",

        "[class*='ListPrice']"

    ]

    for seletor in seletores:

        try:

            elementos = soup.select(
                seletor
            )

        except Exception:

            continue

        for elemento in elementos:

            texto = limpar_texto(
                elemento.get_text(
                    " ",
                    strip=True
                )
            )

            if not texto:
                continue

            resultado = extrair_numero_preco(
                texto
            )

            if resultado:

                candidatos.append(
                    resultado
                )

    # --------------------------------------------------------
    # ESCOLHE UM PREÇO MAIOR QUE O ATUAL
    # --------------------------------------------------------

    maior = 0.0
    melhor = ""

    for candidato in candidatos:

        numero = converter_preco_float(
            candidato
        )

        if (
            numero > valor_atual
            and
            numero > maior
        ):

            maior = numero
            melhor = candidato

    return melhor


# ============================================================
# EXTRAI DADOS DO PRODUTO
# ============================================================

def extrair_dados_produto(link):

    """
    Extrator robusto para páginas da Shopee.

    Tenta:
    - link original;
    - redirecionamentos;
    - HTML final;
    - JSON-LD;
    - OG metadata;
    - meta price;
    - elementos HTML;
    - imagens.
    """

    link = normalizar_url(
        link
    )

    if not link:

        return {

            "sucesso":
                False,

            "erro":
                "Link vazio."
        }

    sessao = criar_sessao()

    resposta = None

    try:

        print(
            "========================================"
        )

        print(
            "[PRODUTO] Abrindo link:"
        )

        print(
            link
        )

        # ----------------------------------------------------
        # PRIMEIRA TENTATIVA
        # ----------------------------------------------------

        resposta = sessao.get(

            link,

            timeout=35,

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

        # ----------------------------------------------------
        # ALGUNS SERVIDORES PODEM RECUSAR A PRIMEIRA
        # REQUISIÇÃO. TENTA NOVAMENTE COM REFERER.
        # ----------------------------------------------------

        if (
            resposta.status_code != 200
            or
            len(resposta.text or "") < 500
        ):

            print(
                "[PRODUTO] Primeira resposta insuficiente."
            )

            headers_2 = {

                "Referer":
                    "https://shopee.com.br/",

                "User-Agent":
                    (
                        "Mozilla/5.0 (Linux; Android 13) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/131.0.0.0 "
                        "Mobile Safari/537.36"
                    ),

                "Accept-Language":
                    "pt-BR,pt;q=0.9"
            }

            resposta = sessao.get(

                link,

                headers=headers_2,

                timeout=35,

                allow_redirects=True
            )

            print(
                "[PRODUTO] Segunda tentativa HTTP:",
                resposta.status_code
            )

            print(
                "[PRODUTO] Segunda URL final:",
                resposta.url
            )

        if resposta.status_code != 200:

            return {

                "sucesso":
                    False,

                "erro":
                    (
                        "A Shopee não permitiu acessar "
                        f"a página. HTTP {resposta.status_code}"
                    ),

                "url_final":
                    resposta.url
            }

        html = resposta.text or ""

        if len(html) < 100:

            return {

                "sucesso":
                    False,

                "erro":
                    "A Shopee retornou uma página vazia."
            }

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # ----------------------------------------------------
        # DADOS
        # ----------------------------------------------------

        titulo = extrair_titulo(
            soup
        )

        preco_atual = extrair_preco(
            soup
        )

        preco_antigo = extrair_preco_antigo(
            soup,
            preco_atual
        )

        imagem = extrair_imagem(
            soup
        )

        # ----------------------------------------------------
        # LIMPA TÍTULO
        # ----------------------------------------------------

        titulo = limpar_texto(
            titulo
        )

        # Alguns títulos podem vir com o nome do site.
        titulo = re.sub(
            r"\s*[\|\-]\s*Shopee.*$",
            "",
            titulo,
            flags=re.IGNORECASE
        )

        titulo = limpar_texto(
            titulo
        )

        # ----------------------------------------------------
        # VALIDAÇÃO
        # ----------------------------------------------------

        valor_atual = converter_preco_float(
            preco_atual
        )

        valor_antigo = converter_preco_float(
            preco_antigo
        )

        if (
            valor_antigo <= valor_atual
            or
            valor_antigo <= 0
        ):

            preco_antigo = ""

        # ----------------------------------------------------
        # LOG
        # ----------------------------------------------------

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
            imagem
        )

        print(
            "========================================"
        )

        # ----------------------------------------------------
        # NÃO ACEITA DADOS GENÉRICOS
        # ----------------------------------------------------

        titulo_generico = (

            not titulo
            or
            titulo.lower() in {

                "oferta imperdível",

                "oferta imperdivel",

                "shopee brasil",

                "shopee"
            }
        )

        if titulo_generico:

            titulo = ""

        # ----------------------------------------------------
        # RETORNA
        # ----------------------------------------------------

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
                imagem,

            "link":
                link,

            "url_final":
                resposta.url
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
# DOWNLOAD DA IMAGEM
# ============================================================

def baixar_imagem(
    foto_url,
    referer=""
):

    if not foto_url:

        return None

    try:

        headers = {

            "User-Agent":
                (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),

            "Accept":
                "image/avif,image/webp,image/apng,"
                "image/svg+xml,image/*,*/*;q=0.8"
        }

        if referer:

            headers[
                "Referer"
            ] = referer

        resposta = requests.get(

            foto_url,

            headers=headers,

            timeout=30
        )

        if resposta.status_code != 200:

            print(
                "[IMAGEM] HTTP:",
                resposta.status_code
            )

            return None

        conteudo = resposta.content

        if not conteudo:

            return None

        return conteudo

    except Exception as erro:

        print(
            "[IMAGEM] Erro:",
            erro
        )

        return None


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
            ] = json.dumps(
                reply_markup
            )

        resposta = requests.post(

            telegram_api_url(
                "sendMessage"
            ),

            json=payload,

            timeout=30
        )

        try:

            resultado = resposta.json()

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

        return resultado

    except requests.RequestException as erro:

        return {

            "ok":
                False,

            "erro":
                f"Erro de conexão com Telegram: {erro}"
        }


# ============================================================
# TELEGRAM - ENVIO DE FOTO
# ============================================================

def telegram_enviar_foto(
    foto,
    legenda,
    canal,
    reply_markup=None,
    referer=""
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

    try:

        conteudo_imagem = baixar_imagem(
            foto,
            referer=referer
        )

        if not conteudo_imagem:

            return {

                "ok":
                    False,

                "erro":
                    "Não foi possível baixar a imagem do produto."
            }

        payload = {

            "chat_id":
                canal,

            "caption":
                legenda,

            "parse_mode":
                "HTML"
        }

        if reply_markup:

            payload[
                "reply_markup"
            ] = json.dumps(
                reply_markup
            )

        resposta = requests.post(

            telegram_api_url(
                "sendPhoto"
            ),

            data=payload,

            files={

                "photo":
                    (
                        "produto.jpg",
                        conteudo_imagem,
                        "image/jpeg"
                    )
            },

            timeout=40
        )

        try:

            resultado = resposta.json()

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

        return resultado

    except Exception as erro:

        print(
            "[TELEGRAM] Erro ao enviar foto:",
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
            ) or resultado.get(
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

    dominio = urlparse(
        link
    ).netloc.lower()

    return (
        "shopee." in dominio
        or
        dominio.endswith(
            "shopee.com"
        )
        or
        dominio.endswith(
            "shopee.com.br"
        )
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
        "Usuário:",
        usuario
    )

    print(
        "Canal:",
        canal
    )

    print(
        "Link:",
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
                    "Não foi possível acessar o produto."
                )
        }

    titulo = dados.get(
        "titulo",
        ""
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

    url_final = dados.get(
        "url_final",
        link
    )

    # ========================================================
    # NÃO PUBLICA DADOS GENÉRICOS
    # ========================================================

    if not titulo:

        return {

            "sucesso":
                False,

            "mensagem":
                (
                    "Não foi possível identificar o título "
                    "real do produto na Shopee."
                )
        }

    # ========================================================
    # PREÇOS
    # ========================================================

    valor_atual = converter_preco_float(
        preco_atual
    )

    valor_antigo = converter_preco_float(
        preco_antigo
    )

    if (
        preco_antigo
        and
        valor_antigo > valor_atual
        and
        valor_atual > 0
    ):

        bloco_preco = (

            f"💰 <s>De: {preco_antigo}</s>\n"

            f"🔥 <b>POR APENAS: "
            f"{preco_atual}!</b>\n"
        )

    elif preco_atual:

        bloco_preco = (

            f"💰 <b>POR APENAS: "
            f"{preco_atual}!</b>\n"
        )

    else:

        bloco_preco = (

            "💰 <b>Confira o preço "
            "da oferta!</b>\n"
        )

    # ========================================================
    # ESCAPA HTML
    # ========================================================

    def escapar_html(texto):

        if texto is None:
            return ""

        return (
            str(texto)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    titulo_html = escapar_html(
        titulo
    )

    # ========================================================
    # LEGENDA
    # ========================================================

    legenda = (

        "🔥 <b>OFERTA IMPERDÍVEL!</b> 🔥\n\n"

        f"📦 <b>{titulo_html}</b>\n\n"

        f"{bloco_preco}\n"

        "🚨 <b>Corre porque essa oferta pode "
        "acabar a qualquer momento!</b>\n\n"

        "👇 <b>APROVEITE AGORA!</b>\n\n"

        "🦊 <b>Raposa Caçadora</b>\n"
        "📌 Ofertas selecionadas todos os dias"
    )

    # ========================================================
    # BOTÃO REAL DO TELEGRAM
    # ========================================================

    reply_markup = {

        "inline_keyboard": [

            [

                {

                    "text":
                        "🛒 COMPRAR AGORA",

                    "url":
                        url_final or link
                }

            ]

        ]

    }

    # ========================================================
    # PRIMEIRA OPÇÃO:
    # FOTO + LEGENDA
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
            "[TELEGRAM] Tentando enviar foto:"
        )

        print(
            foto_url
        )

        resultado = telegram_enviar_foto(

            foto=foto_url,

            legenda=legenda,

            canal=canal,

            reply_markup=reply_markup,

            referer=url_final
        )

        # ----------------------------------------------------
        # SE FALHAR, ENVIA TEXTO
        # ----------------------------------------------------

        if not resultado.get(
            "ok"
        ):

            print(
                "[TELEGRAM] Falha ao enviar imagem."
            )

            print(
                "[TELEGRAM] Motivo:",
                resultado.get(
                    "description"
                )
                or
                resultado.get(
                    "erro"
                )
            )

            print(
                "[TELEGRAM] Enviando mensagem como fallback."
            )

            resultado = telegram_enviar_mensagem(

                texto=legenda,

                canal=canal,

                reply_markup=reply_markup
            )

    else:

        print(
            "[TELEGRAM] Produto não possui imagem."
        )

        resultado = telegram_enviar_mensagem(

            texto=legenda,

            canal=canal,

            reply_markup=reply_markup
        )

    # ========================================================
    # RESULTADO
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
            foto_url,

        "url_final":
            url_final
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
                        ),

                    "imagem":
                        resultado.get(
                            "imagem"
                        ),

                    "url_final":
                        resultado.get(
                            "url_final"
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
                    "BOT_TOKEN não está disponível para o processo do Render."
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
                    "CHANNEL_USERNAME não está disponível para o processo do Render."
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
        # VALIDAÇÃO
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
                    "Um ou mais links não são links válidos da Shopee."
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
                    "A quantidade não pode ser maior que os produtos."
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
# TESTE DIRETO DE UM LINK
# ============================================================

@app.route(
    "/api/testar-produto",
    methods=["POST"]
)
def testar_produto():

    try:

        dados = request.get_json(
            silent=True
        ) or {}

        link = str(
            dados.get(
                "link",
                ""
            )
        ).strip()

        if not link:

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "Informe um link."
            }), 400

        if not link_shopee_valido(
            link
        ):

            return jsonify({

                "sucesso":
                    False,

                "erro":
                    "O link não parece ser da Shopee."
            }), 400

        resultado = extrair_dados_produto(
            link
        )

        return jsonify(
            resultado
        )

    except Exception as erro:

        return jsonify({

            "sucesso":
                False,

            "erro":
                str(erro)
        }), 500


# ============================================================
# EXECUÇÃO LOCAL
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
