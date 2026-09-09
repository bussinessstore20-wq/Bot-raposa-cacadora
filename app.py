import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re

from urllib.parse import parse_qsl, urljoin, urlparse

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
        "Mozilla/5.0 (Linux; Android 15) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.7922.199 "
        "Mobile Safari/537.36"
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
    "Pragma": "no-cache"
})


# ============================================================
# TELEGRAM
# ============================================================

def obter_bot_token():

    return os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()


def obter_canal():

    return os.environ.get(
        "CHANNEL_USERNAME",
        ""
    ).strip()


def telegram_api_url(metodo):

    token = obter_bot_token()

    return (
        f"https://api.telegram.org/bot{token}/{metodo}"
    )


def telegram_get_me():

    token = obter_bot_token()

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

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def limpar_html_texto(texto):

    if not texto:
        return ""

    soup = BeautifulSoup(
        str(texto),
        "html.parser"
    )

    return limpar_texto(
        soup.get_text(
            " ",
            strip=True
        )
    )


def normalizar_url(url):

    if not url:
        return ""

    url = str(url).strip()

    if url.startswith("//"):
        return "https:" + url

    if url.startswith("/"):
        return url

    return url


# ============================================================
# PREÇOS
# ============================================================

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
        .strip()
    )

    # Remove espaços
    valor = valor.replace(" ", "")

    # Caso venha com formato brasileiro:
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

    if preco_str is None:
        return 0.0

    preco_str = str(
        preco_str
    ).strip()

    if not preco_str:
        return 0.0

    try:

        valor = (
            preco_str
            .replace("R$", "")
            .replace("BRL", "")
            .replace("brl", "")
            .replace(" ", "")
        )

        # Formato brasileiro
        if "," in valor:

            valor = valor.replace(
                ".",
                ""
            )

            valor = valor.replace(
                ",",
                "."
            )

        return float(valor)

    except Exception:

        # Última tentativa: extrair números
        encontrado = re.search(
            r"\d+(?:[.,]\d+)*",
            preco_str
        )

        if not encontrado:
            return 0.0

        valor = encontrado.group(0)

        try:

            if "," in valor:

                valor = valor.replace(
                    ".",
                    ""
                )

                valor = valor.replace(
                    ",",
                    "."
                )

            return float(valor)

        except Exception:

            return 0.0


# ============================================================
# EXTRAÇÃO DE PREÇO EM JSON-LD
# ============================================================

def procurar_precos_em_objeto(objeto):

    encontrados = []

    if isinstance(
        objeto,
        dict
    ):

        # Campos comuns
        campos = [
            "price",
            "lowPrice",
            "highPrice",
            "priceValue",
            "salePrice",
            "currentPrice",
            "amount"
        ]

        for campo in campos:

            valor = objeto.get(
                campo
            )

            if valor is not None:

                numero = converter_preco_float(
                    valor
                )

                if numero > 0:

                    encontrados.append(
                        numero
                    )

        # Offers
        offers = objeto.get(
            "offers"
        )

        if offers:

            encontrados.extend(
                procurar_precos_em_objeto(
                    offers
                )
            )

        # Graph
        graph = objeto.get(
            "@graph"
        )

        if graph:

            encontrados.extend(
                procurar_precos_em_objeto(
                    graph
                )
            )

        # Objetos aninhados
        for chave, valor in objeto.items():

            if chave in (
                "offers",
                "@graph"
            ):
                continue

            if isinstance(
                valor,
                (dict, list)
            ):

                encontrados.extend(
                    procurar_precos_em_objeto(
                        valor
                    )
                )

    elif isinstance(
        objeto,
        list
    ):

        for item in objeto:

            encontrados.extend(
                procurar_precos_em_objeto(
                    item
                )
            )

    return encontrados


def extrair_preco_json_ld(soup):

    maiores = []

    scripts = soup.find_all(
        "script",
        type=re.compile(
            r"application/ld\+json",
            re.I
        )
    )

    for script in scripts:

        conteudo = script.string

        if not conteudo:

            conteudo = script.get_text(
                strip=True
            )

        if not conteudo:
            continue

        try:

            dados = json.loads(
                conteudo
            )

            valores = (
                procurar_precos_em_objeto(
                    dados
                )
            )

            maiores.extend(
                valores
            )

        except Exception:

            # Alguns sites colocam JSON inválido
            # dentro do script. Ignoramos.
            continue

    if not maiores:
        return ""

    # Preferimos valores positivos.
    # Em páginas de produto, o menor valor
    # geralmente é o preço promocional.
    maiores = [
        x
        for x in maiores
        if x > 0
    ]

    if not maiores:
        return ""

    valor = min(
        maiores
    )

    return formatar_preco(
        valor
    )


# ============================================================
# EXTRAÇÃO DE TÍTULO
# ============================================================

def extrair_titulo(soup):

    seletores = [

        ("meta", {
            "property": "og:title"
        }),

        ("meta", {
            "name": "twitter:title"
        }),

        ("meta", {
            "name": "title"
        })
    ]

    for tag, attrs in seletores:

        elemento = soup.find(
            tag,
            attrs=attrs
        )

        if elemento:

            valor = elemento.get(
                "content",
                ""
            )

            valor = limpar_texto(
                valor
            )

            if valor:
                return valor

    # H1
    for seletor in [
        "h1",
        ".product-title",
        "[class*='product-title']",
        "[class*='ProductTitle']"
    ]:

        try:

            elemento = soup.select_one(
                seletor
            )

            if elemento:

                valor = limpar_texto(
                    elemento.get_text(
                        " ",
                        strip=True
                    )
                )

                if valor:
                    return valor

        except Exception:

            pass

    # JSON-LD
    scripts = soup.find_all(
        "script",
        type=re.compile(
            r"application/ld\+json",
            re.I
        )
    )

    for script in scripts:

        conteudo = script.string

        if not conteudo:

            conteudo = script.get_text(
                strip=True
            )

        if not conteudo:
            continue

        try:

            dados = json.loads(
                conteudo
            )

            blocos = (
                dados
                if isinstance(
                    dados,
                    list
                )
                else [dados]
            )

            for bloco in blocos:

                if not isinstance(
                    bloco,
                    dict
                ):
                    continue

                nome = bloco.get(
                    "name"
                )

                if nome:

                    nome = limpar_texto(
                        nome
                    )

                    if nome:
                        return nome

        except Exception:

            continue

    # Title HTML
    title_tag = soup.find(
        "title"
    )

    if title_tag:

        titulo = limpar_texto(
            title_tag.get_text(
                strip=True
            )
        )

        if titulo:

            # Remove possíveis sufixos comuns
            titulo = re.sub(
                r"\s*[\-|]\s*Shopee.*$",
                "",
                titulo,
                flags=re.I
            )

            return titulo.strip()

    return ""


# ============================================================
# EXTRAÇÃO DE IMAGEM
# ============================================================

def extrair_imagem(soup):

    # OpenGraph
    for attrs in [

        {
            "property":
                "og:image"
        },

        {
            "property":
                "og:image:url"
        },

        {
            "name":
                "twitter:image"
        }
    ]:

        elemento = soup.find(
            "meta",
            attrs=attrs
        )

        if elemento:

            imagem = (
                elemento.get(
                    "content",
                    ""
                )
                or ""
            ).strip()

            if imagem:

                return normalizar_url(
                    imagem
                )

    # Itemprop image
    elemento = soup.find(
        attrs={
            "itemprop":
                "image"
        }
    )

    if elemento:

        imagem = (
            elemento.get(
                "content"
            )
            or elemento.get(
                "src"
            )
            or elemento.get(
                "data-src"
            )
            or ""
        )

        if imagem:

            return normalizar_url(
                imagem
            )

    # JSON-LD
    scripts = soup.find_all(
        "script",
        type=re.compile(
            r"application/ld\+json",
            re.I
        )
    )

    for script in scripts:

        conteudo = script.string

        if not conteudo:

            conteudo = script.get_text(
                strip=True
            )

        if not conteudo:
            continue

        try:

            dados = json.loads(
                conteudo
            )

            blocos = (
                dados
                if isinstance(
                    dados,
                    list
                )
                else [dados]
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
                    str
                ):

                    if imagem.startswith(
                        "http"
                    ):

                        return imagem

                if isinstance(
                    imagem,
                    list
                ):

                    for item in imagem:

                        if isinstance(
                            item,
                            str
                        ) and item.startswith(
                            "http"
                        ):

                            return item

        except Exception:

            continue

    # Imagens HTML
    for img in soup.find_all(
        "img"
    ):

        candidatos = [

            img.get("src"),

            img.get("data-src"),

            img.get("data-original"),

            img.get("data-lazy"),

            img.get("data-lazy-src")
        ]

        for imagem in candidatos:

            if not imagem:
                continue

            imagem = normalizar_url(
                imagem
            )

            if (
                imagem.startswith(
                    "http"
                )
                and
                not imagem.lower().endswith(
                    ".svg"
                )
            ):

                return imagem

    return ""


# ============================================================
# EXTRAÇÃO DE PREÇO NO HTML
# ============================================================

def extrair_preco_html(soup):

    candidatos = []

    # Classes comuns
    seletores = [

        ".andes-money-amount__fraction",

        "[class*='price']",

        "[class*='Price']",

        "[class*='amount']",

        "[itemprop='price']",

        "[data-testid*='price']"
    ]

    for seletor in seletores:

        try:

            elementos = soup.select(
                seletor
            )

            for elemento in elementos:

                texto = limpar_texto(
                    elemento.get_text(
                        " ",
                        strip=True
                    )
                )

                if not texto:
                    continue

                # Procura R$
                encontrados = re.findall(
                    r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*(?:,\d{2})|\d+(?:,\d{2}))",
                    texto
                )

                for valor in encontrados:

                    numero = converter_preco_float(
                        valor
                    )

                    if (
                        numero > 0
                        and
                        numero < 10000000
                    ):

                        candidatos.append(
                            numero
                        )

        except Exception:

            continue

    # Meta price
    for attrs in [

        {
            "property":
                "product:price:amount"
        },

        {
            "property":
                "og:price:amount"
        },

        {
            "name":
                "price"
        }
    ]:

        elemento = soup.find(
            "meta",
            attrs=attrs
        )

        if elemento:

            valor = elemento.get(
                "content",
                ""
            )

            numero = converter_preco_float(
                valor
            )

            if numero > 0:

                candidatos.append(
                    numero
                )

    if not candidatos:
        return ""

    # Remove valores absurdos
    candidatos = [
        x
        for x in candidatos
        if x > 0
    ]

    if not candidatos:
        return ""

    # Normalmente o menor valor encontrado
    # é o valor promocional.
    valor = min(
        candidatos
    )

    return formatar_preco(
        valor
    )


# ============================================================
# PREÇO ANTIGO
# ============================================================

def extrair_preco_antigo(soup, preco_atual):

    valor_atual = converter_preco_float(
        preco_atual
    )

    candidatos = []

    seletores = [

        ".andes-money-amount--previous",

        ".ui-pdp-price__part--old",

        ".ui-pdp-price__original-value",

        "[class*='previous']",

        "[class*='Previous']",

        "[class*='old-price']",

        "[class*='oldPrice']",

        "[class*='original-price']",

        "[class*='originalPrice']",

        "s"
    ]

    for seletor in seletores:

        try:

            elementos = soup.select(
                seletor
            )

            for elemento in elementos:

                texto = limpar_texto(
                    elemento.get_text(
                        " ",
                        strip=True
                    )
                )

                if not texto:
                    continue

                encontrados = re.findall(
                    r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*(?:,\d{2})|\d+(?:,\d{2}))",
                    texto
                )

                for valor in encontrados:

                    numero = converter_preco_float(
                        valor
                    )

                    if (
                        numero > valor_atual
                        and
                        numero < 10000000
                    ):

                        candidatos.append(
                            numero
                        )

        except Exception:

            continue

    if not candidatos:
        return ""

    # O menor preço acima do atual
    # costuma ser o preço anterior correto.
    valor = min(
        candidatos
    )

    return formatar_preco(
        valor
    )


# ============================================================
# EXTRAÇÃO PRINCIPAL
# ============================================================

def extrair_dados_produto(link):

    print(
        "[PRODUTO] Abrindo link:"
    )

    print(
        link
    )

    try:

        resposta = session.get(
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

        if resposta.status_code != 200:

            return {

                "sucesso":
                    False,

                "erro":
                    (
                        "Não foi possível acessar "
                        f"a página. HTTP {resposta.status_code}"
                    )
            }

        html = resposta.text

        if not html:

            return {

                "sucesso":
                    False,

                "erro":
                    "A Shopee retornou uma página vazia."
            }

        print(
            "[PRODUTO] HTML recebido:",
            len(html),
            "bytes"
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # ====================================================
        # TÍTULO
        # ====================================================

        titulo = extrair_titulo(
            soup
        )

        # ====================================================
        # PREÇO
        # ====================================================

        preco_atual = extrair_preco_json_ld(
            soup
        )

        if not preco_atual:

            preco_atual = extrair_preco_html(
                soup
            )

        # ====================================================
        # IMAGEM
        # ====================================================

        foto_url = extrair_imagem(
            soup
        )

        # ====================================================
        # PREÇO ANTIGO
        # ====================================================

        preco_antigo = extrair_preco_antigo(
            soup,
            preco_atual
        )

        # ====================================================
        # LIMPEZA DO TÍTULO
        # ====================================================

        if titulo:

            titulo = re.sub(
                r"\s*\|\s*Shopee.*$",
                "",
                titulo,
                flags=re.I
            )

            titulo = re.sub(
                r"\s*-\s*Shopee.*$",
                "",
                titulo,
                flags=re.I
            )

            titulo = limpar_texto(
                titulo
            )

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

        # ====================================================
        # VALIDAÇÃO
        # ====================================================

        if not titulo:

            titulo = "Oferta da Shopee"

        # Se absolutamente nenhum dado útil
        # foi encontrado, não fingimos que deu certo.
        if (
            not preco_atual
            and
            not foto_url
            and
            titulo == "Oferta da Shopee"
        ):

            return {

                "sucesso":
                    False,

                "erro":
                    (
                        "A Shopee carregou a página, "
                        "mas não disponibilizou os dados "
                        "do produto no HTML recebido pelo servidor."
                    ),

                "url_final":
                    resposta.url
            }

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
                f"Erro de conexão: {erro}"
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
                f"Erro ao extrair produto: {erro}"
        }


# ============================================================
# TELEGRAM - MENSAGEM
# ============================================================

def telegram_enviar_mensagem(
    texto,
    canal,
    reply_markup=None
):

    token = obter_bot_token()

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
                reply_markup,
                ensure_ascii=False
            )

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
                        "Telegram retornou "
                        f"HTTP {resposta.status_code}"
                    )
            }

    except Exception as erro:

        return {

            "ok":
                False,

            "erro":
                str(erro)
        }


# ============================================================
# TELEGRAM - FOTO
# ============================================================

def telegram_enviar_foto(
    foto,
    legenda,
    canal,
    reply_markup=None
):

    token = obter_bot_token()

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
                "URL da imagem vazia."
        }

    try:

        print(
            "[TELEGRAM] Baixando imagem:"
        )

        print(
            foto
        )

        imagem_resposta = session.get(
            foto,
            timeout=30,
            allow_redirects=True
        )

        print(
            "[TELEGRAM] HTTP imagem:",
            imagem_resposta.status_code
        )

        if imagem_resposta.status_code != 200:

            return {

                "ok":
                    False,

                "erro":
                    (
                        "Não foi possível baixar "
                        "a imagem do produto."
                    )
            }

        conteudo_imagem = (
            imagem_resposta.content
        )

        if not conteudo_imagem:

            return {

                "ok":
                    False,

                "erro":
                    "A imagem retornou vazia."
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
                reply_markup,
                ensure_ascii=False
            )

        resposta = requests.post(

            telegram_api_url(
                "sendPhoto"
            ),

            data=payload,

            files={
                "photo": (
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
                        "Telegram retornou "
                        f"HTTP {resposta.status_code}"
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
# INIT DATA TELEGRAM
# ============================================================

def validar_init_data(init_data):

    token = obter_bot_token()

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
# PUBLICAÇÃO
# ============================================================

def publicar_produto(
    link,
    usuario
):

    canal = obter_canal()

    if not canal:

        return {

            "sucesso":
                False,

            "mensagem":
                "CHANNEL_USERNAME não configurado."
        }

    print(
        "========================================"
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
        "========================================"
    )

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
                    "Não foi possível obter os dados do produto."
                )
        }

    titulo = (
        dados.get(
            "titulo"
        )
        or
        "Oferta da Shopee"
    )

    preco_atual = (
        dados.get(
            "preco_atual"
        )
        or
        ""
    )

    preco_antigo = (
        dados.get(
            "preco_antigo"
        )
        or
        ""
    )

    foto_url = (
        dados.get(
            "imagem"
        )
        or
        ""
    )

    valor_atual = converter_preco_float(
        preco_atual
    )

    valor_antigo = converter_preco_float(
        preco_antigo
    )

    # ========================================================
    # BLOCO DO PREÇO
    # ========================================================

    if (
        preco_antigo
        and
        valor_antigo > valor_atual
        and
        valor_atual > 0
    ):

        bloco_preco = (

            f"💰 <s>De: {preco_antigo}</s>\n"

            f"🔥 <b>Por apenas: "
            f"{preco_atual}</b>"
        )

    elif preco_atual:

        bloco_preco = (

            f"💰 <b>Por apenas: "
            f"{preco_atual}</b>"
        )

    else:

        bloco_preco = (

            "💰 <b>Confira o preço "
            "da oferta</b>"
        )

    # ========================================================
    # TÍTULO SEGURO PARA HTML
    # ========================================================

    # Evita que caracteres especiais do produto
    # quebrem o parse_mode HTML.
    titulo_html = (
        titulo
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    # ========================================================
    # LEGENDA
    # ========================================================

    legenda = (

        "🔥 <b>OFERTA IMPERDÍVEL!</b> 🔥\n\n"

        f"📦 <b>{titulo_html}</b>\n\n"

        f"{bloco_preco}\n\n"

        "🚨 <b>Corre porque essa oferta "
        "pode acabar a qualquer momento!</b>\n\n"

        "🛒 <b>APROVEITE AGORA!</b>"
    )

    # ========================================================
    # BOTÃO
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
    # FOTO
    # ========================================================

    resultado = None

    if (
        foto_url
        and
        foto_url.startswith(
            "http"
        )
    ):

        resultado = telegram_enviar_foto(

            foto=foto_url,

            legenda=legenda,

            canal=canal,

            reply_markup=reply_markup
        )

        # Se o Telegram não aceitar a imagem,
        # manda pelo menos a mensagem.
        if not resultado.get(
            "ok"
        ):

            print(
                "[TELEGRAM] Falha na foto:"
            )

            print(
                resultado
            )

            print(
                "[TELEGRAM] Tentando enviar somente texto."
            )

            resultado = telegram_enviar_mensagem(

                texto=legenda,

                canal=canal,

                reply_markup=reply_markup
            )

    else:

        print(
            "[TELEGRAM] Nenhuma imagem encontrada."
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
# DEBUG TELEGRAM
# ============================================================

@app.route(
    "/debug-telegram",
    methods=["GET"]
)
def debug_telegram():

    token = obter_bot_token()

    canal = obter_canal()

    resultado = telegram_get_me()

    bot = None

    if resultado.get(
        "ok"
    ):

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

    token = obter_bot_token()

    channel = obter_canal()

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

    token = obter_bot_token()

    channel = obter_canal()

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
            int(
                time.time()
            )
    })


# ============================================================
# TESTAR PRODUTO MANUALMENTE
# ============================================================

@app.route(
    "/api/testar-produto",
    methods=["POST"]
)
def testar_produto():

    try:

        dados = request.get_json(
            silent=True
        )

        if not dados:

            return jsonify({

                "erro":
                    "JSON inválido."
            }), 400

        link = str(
            dados.get(
                "link",
                ""
            )
        ).strip()

        if not link:

            return jsonify({

                "erro":
                    "Informe o link."
            }), 400

        if not link_shopee_valido(
            link
        ):

            return jsonify({

                "erro":
                    "Link da Shopee inválido."
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

        token = obter_bot_token()

        if not token:

            return jsonify({

                "erro":
                    "BOT_TOKEN não está disponível para o processo do Render."
            }), 500

        # ====================================================
        # CANAL
        # ====================================================

        canal = obter_canal()

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
                    "Um ou mais links não são válidos."
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
