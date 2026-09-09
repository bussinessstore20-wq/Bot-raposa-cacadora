import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re
import html as html_lib

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
        "application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,"
        "*/*;q=0.8"
    ),

    "Accept-Language":
        "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",

    "Cache-Control":
        "no-cache",

    "Pragma":
        "no-cache",

    "Connection":
        "keep-alive"
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
# TEXTO
# ============================================================

def limpar_texto(texto):

    if texto is None:
        return ""

    texto = html_lib.unescape(
        str(texto)
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


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

    valor = re.sub(
        r"[^\d,.]",
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

        numero = float(
            valor
        )

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
            .strip()
        )

        # Se tiver ponto e vírgula:
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

        return float(
            valor
        )

    except Exception:

        return 0.0


# ============================================================
# URL
# ============================================================

def normalizar_url(url):

    if not url:
        return ""

    url = str(
        url
    ).strip()

    url = html_lib.unescape(
        url
    )

    return url


def url_e_shopee(url):

    if not url:
        return False

    try:

        dominio = urlparse(
            url
        ).netloc.lower()

        return (
            "shopee" in dominio
        )

    except Exception:

        return (
            "shopee" in url.lower()
        )


# ============================================================
# REQUISIÇÃO DA PÁGINA
# ============================================================

def abrir_pagina_shopee(link):

    print(
        "[PRODUTO] Abrindo link:"
    )

    print(
        link
    )

    headers = {

        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 15) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0.7922.199 "
            "Mobile Safari/537.36"
        ),

        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,"
            "image/avif,image/webp,"
            "*/*;q=0.8"
        ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en-US;q=0.8",

        "Referer":
            "https://shopee.com.br/",

        "Upgrade-Insecure-Requests":
            "1"
    }

    try:

        resposta = session.get(

            link,

            headers=headers,

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

        print(
            "[PRODUTO] HTML recebido:",
            len(resposta.text),
            "bytes"
        )

        if resposta.status_code != 200:

            return {

                "sucesso":
                    False,

                "erro":
                    (
                        f"Página retornou HTTP "
                        f"{resposta.status_code}"
                    )
            }

        return {

            "sucesso":
                True,

            "html":
                resposta.text,

            "url_final":
                resposta.url,

            "resposta":
                resposta
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
                str(erro)
        }


# ============================================================
# BUSCA RECURSIVA EM JSON
# ============================================================

def buscar_valores_json(obj, chaves, encontrados=None):

    if encontrados is None:
        encontrados = []

    if len(encontrados) >= 100:
        return encontrados

    if isinstance(obj, dict):

        for chave, valor in obj.items():

            chave_lower = str(
                chave
            ).lower()

            if chave_lower in chaves:

                if isinstance(
                    valor,
                    (str, int, float)
                ):

                    encontrados.append(
                        valor
                    )

            buscar_valores_json(
                valor,
                chaves,
                encontrados
            )

    elif isinstance(obj, list):

        for item in obj:

            buscar_valores_json(
                item,
                chaves,
                encontrados
            )

    return encontrados


# ============================================================
# EXTRAÇÃO DE JSON DOS SCRIPTS
# ============================================================

def extrair_json_scripts(soup):

    objetos = []

    scripts = soup.find_all(
        "script"
    )

    for script in scripts:

        conteudo = script.string

        if not conteudo:

            conteudo = script.get_text()

        if not conteudo:

            continue

        conteudo = conteudo.strip()

        if not conteudo:

            continue

        # JSON-LD normal
        if (
            script.get("type", "")
            .lower()
            ==
            "application/ld+json"
        ):

            try:

                dados = json.loads(
                    conteudo
                )

                objetos.append(
                    dados
                )

                continue

            except Exception:

                pass

        # Tenta JSON puro
        if (
            conteudo.startswith("{")
            or
            conteudo.startswith("[")
        ):

            try:

                dados = json.loads(
                    conteudo
                )

                objetos.append(
                    dados
                )

                continue

            except Exception:

                pass

        # ====================================================
        # Procura objetos JSON dentro de scripts JS
        # ====================================================

        padroes = [

            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;',

            r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;',

            r'__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;',

            r'__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;'
        ]

        for padrao in padroes:

            encontrados = re.findall(
                padrao,
                conteudo,
                flags=re.DOTALL
            )

            for encontrado in encontrados:

                try:

                    dados = json.loads(
                        encontrado
                    )

                    objetos.append(
                        dados
                    )

                except Exception:

                    continue

    return objetos


# ============================================================
# EXTRAÇÃO JSON-LD
# ============================================================

def extrair_produto_jsonld(soup):

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        try:

            conteudo = script.string

            if not conteudo:
                conteudo = script.get_text()

            if not conteudo:
                continue

            dados = json.loads(
                conteudo
            )

            blocos = []

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

            for bloco in blocos:

                if not isinstance(
                    bloco,
                    dict
                ):

                    continue

                tipo = str(
                    bloco.get(
                        "@type",
                        ""
                    )
                ).lower()

                if (
                    "product"
                    not in tipo
                ):

                    continue

                titulo = (
                    bloco.get(
                        "name"
                    )
                    or
                    ""
                )

                imagem = (
                    bloco.get(
                        "image"
                    )
                    or
                    ""
                )

                offers = bloco.get(
                    "offers"
                )

                preco = ""

                if isinstance(
                    offers,
                    list
                ):

                    offers = (
                        offers[0]
                        if offers
                        else {}
                    )

                if isinstance(
                    offers,
                    dict
                ):

                    preco = (
                        offers.get(
                            "price"
                        )
                        or
                        offers.get(
                            "lowPrice"
                        )
                        or
                        offers.get(
                            "highPrice"
                        )
                    )

                if isinstance(
                    imagem,
                    list
                ):

                    imagem = (
                        imagem[0]
                        if imagem
                        else ""
                    )

                return {

                    "titulo":
                        limpar_texto(
                            titulo
                        ),

                    "preco":
                        formatar_preco(
                            preco
                        ),

                    "imagem":
                        str(
                            imagem
                        ).strip()
                }

        except Exception:

            continue

    return {}


# ============================================================
# EXTRAÇÃO DE META TAGS
# ============================================================

def extrair_meta_produto(soup):

    resultado = {

        "titulo":
            "",

        "preco":
            "",

        "preco_antigo":
            "",

        "imagem":
            ""
    }

    # ========================================================
    # TÍTULO
    # ========================================================

    seletores_titulo = [

        ("meta", {
            "property":
                "og:title"
        }),

        ("meta", {
            "name":
                "twitter:title"
        })
    ]

    for tag, attrs in seletores_titulo:

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

                resultado[
                    "titulo"
                ] = valor

                break

    # ========================================================
    # IMAGEM
    # ========================================================

    seletores_imagem = [

        {
            "property":
                "og:image"
        },

        {
            "name":
                "twitter:image"
        },

        {
            "property":
                "og:image:url"
        }
    ]

    for attrs in seletores_imagem:

        elemento = soup.find(
            "meta",
            attrs=attrs
        )

        if elemento:

            valor = elemento.get(
                "content",
                ""
            ).strip()

            if (
                valor
                and
                "shopeemobilemall-live" not in valor
            ):

                resultado[
                    "imagem"
                ] = valor

                break

    # ========================================================
    # PREÇO
    # ========================================================

    seletores_preco = [

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
        },

        {
            "name":
                "product:price"
        },

        {
            "property":
                "product:price"
        }
    ]

    for attrs in seletores_preco:

        elemento = soup.find(
            "meta",
            attrs=attrs
        )

        if elemento:

            valor = elemento.get(
                "content",
                ""
            )

            valor = formatar_preco(
                valor
            )

            if valor:

                resultado[
                    "preco"
                ] = valor

                break

    return resultado


# ============================================================
# EXTRAÇÃO POR PADRÕES NO HTML
# ============================================================

def extrair_por_regex(html):

    resultado = {

        "titulo":
            "",

        "preco":
            "",

        "preco_antigo":
            "",

        "imagem":
            ""
    }

    # ========================================================
    # TÍTULO
    # ========================================================

    padroes_titulo = [

        r'"name"\s*:\s*"([^"]{5,300})"',

        r'"productName"\s*:\s*"([^"]{5,300})"',

        r'"itemName"\s*:\s*"([^"]{5,300})"',

        r'"title"\s*:\s*"([^"]{5,300})"'
    ]

    for padrao in padroes_titulo:

        encontrado = re.search(
            padrao,
            html,
            flags=re.IGNORECASE
        )

        if encontrado:

            valor = limpar_texto(
                encontrado.group(1)
            )

            if (
                valor
                and
                "Shopee Brasil" not in valor
                and
                "Ofertas incríveis" not in valor
            ):

                resultado[
                    "titulo"
                ] = valor

                break

    # ========================================================
    # IMAGEM
    # ========================================================

    padroes_imagem = [

        r'"image"\s*:\s*"([^"]+)"',

        r'"imageUrl"\s*:\s*"([^"]+)"',

        r'"image_url"\s*:\s*"([^"]+)"',

        r'"thumbnail"\s*:\s*"([^"]+)"',

        r'"cover"\s*:\s*"([^"]+)"'
    ]

    for padrao in padroes_imagem:

        encontrados = re.findall(
            padrao,
            html,
            flags=re.IGNORECASE
        )

        for imagem in encontrados:

            imagem = (
                imagem
                .replace("\\/", "/")
                .replace("\\u002F", "/")
            )

            imagem = html_lib.unescape(
                imagem
            )

            if (
                imagem.startswith("http")
                and
                "shopeemobilemall-live" not in imagem
            ):

                resultado[
                    "imagem"
                ] = imagem

                break

        if resultado[
            "imagem"
        ]:

            break

    # ========================================================
    # PREÇO
    # ========================================================

    padroes_preco = [

        r'"price"\s*:\s*"?(\d+(?:\.\d+)?)"?',

        r'"priceMin"\s*:\s*"?(\d+(?:\.\d+)?)"?',

        r'"priceMax"\s*:\s*"?(\d+(?:\.\d+)?)"?',

        r'"currentPrice"\s*:\s*"?(\d+(?:\.\d+)?)"?',

        r'"current_price"\s*:\s*"?(\d+(?:\.\d+)?)"?'
    ]

    for padrao in padroes_preco:

        encontrados = re.findall(
            padrao,
            html,
            flags=re.IGNORECASE
        )

        for valor in encontrados:

            try:

                numero = float(
                    valor
                )

                # Ignora valores absurdos
                if (
                    numero > 0
                    and
                    numero < 10000000
                ):

                    resultado[
                        "preco"
                    ] = formatar_preco(
                        numero
                    )

                    break

            except Exception:

                continue

        if resultado[
            "preco"
        ]:

            break

    return resultado


# ============================================================
# EXTRAÇÃO PRINCIPAL DO PRODUTO
# ============================================================

def extrair_dados_produto(link):

    pagina = abrir_pagina_shopee(
        link
    )

    if not pagina.get(
        "sucesso"
    ):

        return pagina

    html = pagina[
        "html"
    ]

    url_final = pagina[
        "url_final"
    ]

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    print(
        "[PRODUTO] Analisando página..."
    )

    resultado = {

        "titulo":
            "",

        "preco_atual":
            "",

        "preco_antigo":
            "",

        "imagem":
            "",

        "link":
            link,

        "url_final":
            url_final
    }

    # ========================================================
    # 1. JSON-LD
    # ========================================================

    jsonld = extrair_produto_jsonld(
        soup
    )

    if jsonld:

        if jsonld.get(
            "titulo"
        ):

            resultado[
                "titulo"
            ] = jsonld[
                "titulo"
            ]

        if jsonld.get(
            "preco"
        ):

            resultado[
                "preco_atual"
            ] = jsonld[
                "preco"
            ]

        if jsonld.get(
            "imagem"
        ):

            resultado[
                "imagem"
            ] = jsonld[
                "imagem"
            ]

    # ========================================================
    # 2. META TAGS
    # ========================================================

    meta = extrair_meta_produto(
        soup
    )

    if not resultado[
        "titulo"
    ]:

        resultado[
            "titulo"
        ] = meta.get(
            "titulo",
            ""
        )

    if not resultado[
        "preco_atual"
    ]:

        resultado[
            "preco_atual"
        ] = meta.get(
            "preco",
            ""
        )

    if not resultado[
        "imagem"
    ]:

        resultado[
            "imagem"
        ] = meta.get(
            "imagem",
            ""
        )

    # ========================================================
    # 3. SCRIPTS JSON
    # ========================================================

    objetos = extrair_json_scripts(
        soup
    )

    # ========================================================
    # TÍTULO
    # ========================================================

    if not resultado[
        "titulo"
    ]:

        chaves_titulo = {

            "name",
            "productname",
            "product_name",
            "itemname",
            "item_name"
        }

        valores = buscar_valores_json(
            objetos,
            chaves_titulo
        )

        for valor in valores:

            valor = limpar_texto(
                valor
            )

            if (
                len(valor) >= 5
                and
                "Shopee Brasil" not in valor
                and
                "Ofertas incríveis" not in valor
                and
                "Melhores preços do mercado" not in valor
            ):

                resultado[
                    "titulo"
                ] = valor

                break

    # ========================================================
    # PREÇO
    # ========================================================

    if not resultado[
        "preco_atual"
    ]:

        chaves_preco = {

            "price",
            "currentprice",
            "current_price",
            "price_min",
            "pricemin",
            "price_max",
            "pricemax",
            "discountprice",
            "discount_price",
            "finalprice",
            "final_price"
        }

        valores = buscar_valores_json(
            objetos,
            chaves_preco
        )

        candidatos = []

        for valor in valores:

            try:

                numero = float(
                    str(
                        valor
                    ).replace(
                        ",",
                        "."
                    )
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

        if candidatos:

            # Normalmente o menor preço
            # é o preço promocional.
            numero = min(
                candidatos
            )

            resultado[
                "preco_atual"
            ] = formatar_preco(
                numero
            )

    # ========================================================
    # IMAGEM
    # ========================================================

    if not resultado[
        "imagem"
    ]:

        chaves_imagem = {

            "image",
            "imageurl",
            "image_url",
            "cover",
            "coverimage",
            "cover_image",
            "thumbnail",
            "thumbnailurl",
            "thumbnail_url"
        }

        valores = buscar_valores_json(
            objetos,
            chaves_imagem
        )

        for valor in valores:

            if not isinstance(
                valor,
                str
            ):

                continue

            imagem = (
                valor
                .replace(
                    "\\/",
                    "/"
                )
                .replace(
                    "\\u002F",
                    "/"
                )
            )

            imagem = html_lib.unescape(
                imagem
            )

            if (
                imagem.startswith(
                    "http"
                )
                and
                "shopeemobilemall-live" not in imagem
            ):

                resultado[
                    "imagem"
                ] = imagem

                break

    # ========================================================
    # 4. REGEX DIRETO NO HTML
    # ========================================================

    regex = extrair_por_regex(
        html
    )

    if not resultado[
        "titulo"
    ]:

        resultado[
            "titulo"
        ] = regex.get(
            "titulo",
            ""
        )

    if not resultado[
        "preco_atual"
    ]:

        resultado[
            "preco_atual"
        ] = regex.get(
            "preco",
            ""
        )

    if not resultado[
        "imagem"
    ]:

        resultado[
            "imagem"
        ] = regex.get(
            "imagem",
            ""
        )

    # ========================================================
    # 5. H1
    # ========================================================

    if not resultado[
        "titulo"
    ]:

        for h1 in soup.find_all(
            "h1"
        ):

            texto = limpar_texto(
                h1.get_text(
                    " ",
                    strip=True
                )
            )

            if (
                len(texto) >= 5
                and
                "Shopee Brasil" not in texto
                and
                "Ofertas incríveis" not in texto
            ):

                resultado[
                    "titulo"
                ] = texto

                break

    # ========================================================
    # 6. TITLE
    # ========================================================

    if not resultado[
        "titulo"
    ]:

        title = soup.find(
            "title"
        )

        if title:

            texto = limpar_texto(
                title.get_text(
                    strip=True
                )
            )

            if (
                texto
                and
                "Shopee Brasil" not in texto
                and
                "Ofertas incríveis" not in texto
            ):

                resultado[
                    "titulo"
                ] = texto

    # ========================================================
    # 7. IMAGENS HTML
    # ========================================================

    if not resultado[
        "imagem"
    ]:

        imagens = soup.find_all(
            "img"
        )

        for img in imagens:

            candidatos = [

                img.get(
                    "src"
                ),

                img.get(
                    "data-src"
                ),

                img.get(
                    "data-original"
                ),

                img.get(
                    "data-lazy"
                ),

                img.get(
                    "srcset"
                )
            ]

            for imagem in candidatos:

                if not imagem:
                    continue

                if "," in imagem:

                    imagem = (
                        imagem
                        .split(",")[0]
                        .strip()
                        .split(" ")[0]
                    )

                imagem = (
                    imagem
                    .replace(
                        "\\/",
                        "/"
                    )
                )

                if (
                    imagem.startswith(
                        "http"
                    )
                    and
                    "shopeemobilemall-live" not in imagem
                ):

                    resultado[
                        "imagem"
                    ] = imagem

                    break

            if resultado[
                "imagem"
            ]:

                break

    # ========================================================
    # REMOVE TÍTULOS GENÉRICOS
    # ========================================================

    titulo_atual = limpar_texto(
        resultado[
            "titulo"
        ]
    )

    titulos_invalidos = [

        "Shopee Brasil",

        "Shopee Brasil | Ofertas incríveis. Melhores preços do mercado",

        "Shopee",

        "Ofertas incríveis",

        "Melhores preços do mercado",

        "Comprar Online"
    ]

    if any(
        titulo_atual.lower()
        ==
        item.lower()
        for item in titulos_invalidos
    ):

        resultado[
            "titulo"
        ] = ""

    # ========================================================
    # REMOVE IMAGEM GENÉRICA
    # ========================================================

    imagem_atual = resultado[
        "imagem"
    ]

    if (
        imagem_atual
        and
        (
            "shopee-mobilemall-live" in
            imagem_atual
            or
            "homepagefe" in
            imagem_atual
        )
    ):

        resultado[
            "imagem"
        ] = ""

    # ========================================================
    # DEBUG
    # ========================================================

    print(
        "[PRODUTO] ========================================"
    )

    print(
        "[PRODUTO] URL original:",
        link
    )

    print(
        "[PRODUTO] URL final:",
        url_final
    )

    print(
        "[PRODUTO] Título:",
        resultado[
            "titulo"
        ]
    )

    print(
        "[PRODUTO] Preço atual:",
        resultado[
            "preco_atual"
        ]
    )

    print(
        "[PRODUTO] Preço antigo:",
        resultado[
            "preco_antigo"
        ]
    )

    print(
        "[PRODUTO] Imagem:",
        resultado[
            "imagem"
        ]
    )

    print(
        "[PRODUTO] ========================================"
    )

    # ========================================================
    # VALIDAÇÃO
    # ========================================================

    if not resultado[
        "titulo"
    ]:

        return {

            "sucesso":
                False,

            "erro":
                (
                    "A Shopee não forneceu o título "
                    "do produto no HTML recebido. "
                    "O link provavelmente está retornando "
                    "uma página intermediária."
                )
        }

    # Não publica página genérica
    if (
        "Shopee Brasil" in
        resultado[
            "titulo"
        ]
    ):

        return {

            "sucesso":
                False,

            "erro":
                (
                    "A Shopee retornou uma página "
                    "genérica em vez dos dados do produto."
                )
        }

    return {

        "sucesso":
            True,

        "titulo":
            resultado[
                "titulo"
            ],

        "preco_atual":
            resultado[
                "preco_atual"
            ],

        "preco_antigo":
            resultado[
                "preco_antigo"
            ],

        "imagem":
            resultado[
                "imagem"
            ],

        "link":
            link,

        "url_final":
            url_final
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

            resultado = resposta.json()

        except Exception:

            return {

                "ok":
                    False,

                "erro":
                    (
                        f"Telegram retornou "
                        f"HTTP {resposta.status_code}"
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

        print(
            "[TELEGRAM] Baixando imagem:"
        )

        print(
            foto
        )

        resposta_imagem = requests.get(

            foto,

            headers={

                "User-Agent":
                    (
                        "Mozilla/5.0 "
                        "(Linux; Android 15) "
                        "AppleWebKit/537.36 "
                        "Chrome/151.0 Safari/537.36"
                    ),

                "Referer":
                    "https://shopee.com.br/"
            },

            timeout=30
        )

        print(
            "[TELEGRAM] HTTP imagem:",
            resposta_imagem.status_code
        )

        if resposta_imagem.status_code != 200:

            return {

                "ok":
                    False,

                "erro":
                    (
                        "Não foi possível baixar "
                        f"a imagem. HTTP "
                        f"{resposta_imagem.status_code}"
                    )
            }

        imagem_bytes = (
            resposta_imagem.content
        )

        if not imagem_bytes:

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

                "photo":
                    (
                        "produto.jpg",
                        imagem_bytes,
                        "image/jpeg"
                    )
            },

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
                        f"Telegram retornou "
                        f"HTTP {resposta.status_code}"
                    )
            }

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
            int(
                time.time()
            )
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

    return (
        "shopee." in link_lower
        or
        "shopee" in link_lower
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

    # ========================================================
    # EXTRAI PRODUTO
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
                    "Não foi possível extrair o produto."
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

    # ========================================================
    # ESCAPA HTML
    # ========================================================

    titulo_html = html_lib.escape(
        titulo
    )

    preco_atual_html = html_lib.escape(
        preco_atual
    )

    preco_antigo_html = html_lib.escape(
        preco_antigo
    )

    # ========================================================
    # PREÇO
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

            f"💰 <s>De: "
            f"{preco_antigo_html}</s>\n"

            f"🔥 <b>Por apenas: "
            f"{preco_atual_html}</b>"
        )

    elif preco_atual:

        bloco_preco = (

            f"💰 <b>Por apenas: "
            f"{preco_atual_html}</b>"
        )

    else:

        bloco_preco = (

            "💰 <b>Confira o preço "
            "da oferta</b>"
        )

    # ========================================================
    # LEGENDA FINAL
    # ========================================================

    legenda = (

        "🔥 <b>OFERTA IMPERDÍVEL!</b> 🔥\n\n"

        f"📦 <b>{titulo_html}</b>\n\n"

        f"{bloco_preco}\n\n"

        "🚨 <b>Corre porque essa oferta "
        "pode acabar a qualquer momento!</b>\n\n"

        "👇 <b>APROVEITE AGORA!</b>\n\n"

        "🦊 <b>Raposa Caçadora</b>"
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

        # ====================================================
        # SE A FOTO FALHAR, ENVIA TEXTO
        # ====================================================

        if not resultado.get(
            "ok"
        ):

            print(
                "[TELEGRAM] Foto falhou."
            )

            print(
                "[TELEGRAM] Enviando texto..."
            )

            resultado = telegram_enviar_mensagem(

                texto=legenda,

                canal=canal,

                reply_markup=reply_markup
            )

    else:

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
        # FINALIZA
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
        # LINK
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
        # SALVA
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

            if sucesso:

                tarefa[
                    "status"
                ] = "aguardando"

            else:

                tarefa[
                    "status"
                ] = "erro"

        # ====================================================
        # ÚLTIMO
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
        # LIMITA
        # ====================================================

        links = links[
            :quantidade
        ]

        # ====================================================
        # TAREFA
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
                tarefa[
                    "id"
                ],

            "status":
                tarefa[
                    "status"
                ],

            "progresso":
                tarefa[
                    "progresso"
                ],

            "produto":
                tarefa[
                    "produto_atual"
                ],

            "total":
                tarefa[
                    "quantidade"
                ],

            "produto_link":
                tarefa[
                    "produto_link"
                ],

            "resultados":
                tarefa[
                    "resultados"
                ]
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
