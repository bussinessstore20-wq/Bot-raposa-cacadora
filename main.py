import os
import json
import time
import html
import threading
import hashlib
import hmac
import re
from urllib.parse import parse_qsl, urljoin, urlparse, unquote

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
        "Chrome/131.0.0.0 "
        "Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Cache-Control": "no-cache",
})


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
                box-shadow:
                    0 10px 40px
                    rgba(0,0,0,.5);
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
                Coloque os dois arquivos
                na mesma pasta.
            </p>

        </body>

        </html>
        """, 404

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
        "mini_app": os.path.isfile(INDEX_FILE),
        "telegram_configurado": bool(
            TELEGRAM_TOKEN
        ),
        "chat_configurado": bool(
            CHAT_ID
        )
    })


# ============================================================
# TRATAMENTO GLOBAL DE ERROS
# ============================================================

@app.errorhandler(Exception)
def erro_global(e):

    print(
        "\n" + "=" * 60
    )

    print(
        "❌ ERRO INTERNO DO SERVIDOR"
    )

    print(
        repr(e)
    )

    print(
        "=" * 60
    )

    return jsonify({
        "ok": False,
        "erro": (
            "Erro interno no servidor."
        ),
        "detalhe": str(e)
    }), 500


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

def validar_init_data(init_data):

    if not init_data:
        print(
            "❌ initData vazio."
        )
        return False

    if not TELEGRAM_TOKEN:
        print(
            "❌ TELEGRAM_TOKEN ausente."
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
                "❌ Hash do Telegram ausente."
            )

            return False

        data_check_string = "\n".join(
            f"{chave}={valor}"
            for chave, valor
            in sorted(
                dados.items()
            )
        )

        secret_key = hmac.new(
            key=b"WebAppData",
            msg=TELEGRAM_TOKEN.encode(
                "utf-8"
            ),
            digestmod=hashlib.sha256
        ).digest()

        calculado = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(
                "utf-8"
            ),
            digestmod=hashlib.sha256
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
            f"❌ Erro ao validar initData: {e}"
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

        resposta = session.post(
            url,
            data=dados or {},
            timeout=20
        )

        print(
            f"📡 Telegram {metodo}: "
            f"HTTP {resposta.status_code}"
        )

        try:

            resultado = resposta.json()

        except Exception:

            print(
                "❌ Telegram não retornou JSON:"
            )

            print(
                resposta.text[:1000]
            )

            return None

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
            f"❌ Erro Telegram "
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
            "parse_mode": "HTML",
            "disable_web_page_preview": False
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
            "Chrome/131.0.0.0 "
            "Safari/537.36"
        ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8",

        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,"
            "image/avif,image/webp,"
            "*/*;q=0.8"
        ),

        "Referer":
            "https://www.mercadolivre.com.br/"
    }


# ============================================================
# NORMALIZAR URL
# ============================================================

def normalizar_url(url):

    if not url:
        return ""

    url = str(url).strip()

    url = url.replace(
        "\n",
        ""
    ).replace(
        "\r",
        ""
    )

    if not url.startswith(
        ("http://", "https://")
    ):

        url = (
            "https://" +
            url
        )

    return url


# ============================================================
# EXPANDIR LINK
# ============================================================

def expandir_link(
    url,
    headers
):

    url = normalizar_url(
        url
    )

    if not url:
        return None

    print(
        f"🔗 Expandindo URL: {url}"
    )

    try:

        resposta = session.get(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"➡️ HTTP: "
            f"{resposta.status_code}"
        )

        print(
            f"➡️ URL final: "
            f"{resposta.url}"
        )

        if resposta.status_code >= 400:

            print(
                "⚠️ URL retornou erro HTTP."
            )

            return None

        return resposta.url

    except Exception as e:

        print(
            f"❌ Erro ao expandir URL: {e}"
        )

        return None


# ============================================================
# VERIFICAR SE É LINK DE PRODUTO
# ============================================================

def parece_produto(url):

    if not url:
        return False

    url_lower = url.lower()

    padroes = [
        "produto.mercadolivre.com.br",
        "/p/mlb",
        "/p/MLB".lower(),
        "mlb-"
    ]

    return any(
        padrao in url_lower
        for padrao in padroes
    )


# ============================================================
# LIMPAR LINK DE PRODUTO
# ============================================================

def limpar_link_produto(
    url,
    base_url=None
):

    if not url:
        return ""

    try:

        if base_url:

            url = urljoin(
                base_url,
                url
            )

        url = url.strip()

        url = url.split(
            "#"
        )[0]

        return url

    except Exception:

        return url


# ============================================================
# EXTRAIR URLS DE TEXTO
# ============================================================

def extrair_urls_texto(
    texto,
    base_url
):

    encontrados = []

    if not texto:
        return encontrados

    padrao = re.compile(
        r'https?://[^\s"\'<>\\]+'
    )

    for item in padrao.findall(
        texto
    ):

        item = html.unescape(
            item
        )

        item = item.replace(
            "\\/",
            "/"
        )

        item = item.rstrip(
            ".,);]}"
        )

        if parece_produto(
            item
        ):

            item = limpar_link_produto(
                item,
                base_url
            )

            encontrados.append(
                item
            )

    return encontrados


# ============================================================
# DESCOBRIR LINKS DE PRODUTOS
# ============================================================

def encontrar_links_produtos(
    url_vitrine,
    headers
):

    print(
        "\n🔎 ACESSANDO VITRINE"
    )

    print(
        f"🔗 {url_vitrine}"
    )

    try:

        resposta = session.get(
            url_vitrine,
            headers=headers,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"🌐 HTTP: "
            f"{resposta.status_code}"
        )

        print(
            f"🌐 URL final: "
            f"{resposta.url}"
        )

        resposta.raise_for_status()

    except Exception as e:

        print(
            f"❌ Erro ao acessar vitrine: {e}"
        )

        return []

    url_base = resposta.url

    texto = resposta.text

    print(
        f"📄 Tamanho HTML: "
        f"{len(texto)} caracteres"
    )

    soup = BeautifulSoup(
        texto,
        "html.parser"
    )

    links = []

    # --------------------------------------------------------
    # LINKS <A>
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

        href = html.unescape(
            href
        )

        href = limpar_link_produto(
            href,
            url_base
        )

        if parece_produto(
            href
        ):

            links.append(
                href
            )

    # --------------------------------------------------------
    # LINKS EM ATRIBUTOS
    # --------------------------------------------------------

    for elemento in soup.find_all():

        for atributo in [
            "href",
            "src",
            "data-href",
            "data-url",
            "data-link",
            "data-permalink"
        ]:

            valor = elemento.get(
                atributo
            )

            if not valor:
                continue

            valor = html.unescape(
                str(valor)
            )

            valor = valor.replace(
                "\\/",
                "/"
            )

            if parece_produto(
                valor
            ):

                valor = limpar_link_produto(
                    valor,
                    url_base
                )

                links.append(
                    valor
                )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        conteudo = script.string

        if not conteudo:
            conteudo = script.get_text()

        if not conteudo:
            continue

        links.extend(
            extrair_urls_texto(
                conteudo,
                url_base
            )
        )

        try:

            objeto = json.loads(
                conteudo
            )

            objetos = (
                objeto
                if isinstance(
                    objeto,
                    list
                )
                else [objeto]
            )

            for obj in objetos:

                if not isinstance(
                    obj,
                    dict
                ):
                    continue

                for chave in [
                    "url",
                    "@id",
                    "mainEntityOfPage"
                ]:

                    valor = obj.get(
                        chave
                    )

                    if isinstance(
                        valor,
                        str
                    ) and parece_produto(
                        valor
                    ):

                        links.append(
                            valor
                        )

                    elif isinstance(
                        valor,
                        dict
                    ):

                        valor_url = valor.get(
                            "@id"
                        ) or valor.get(
                            "url"
                        )

                        if (
                            valor_url
                            and
                            parece_produto(
                                valor_url
                            )
                        ):

                            links.append(
                                valor_url
                            )

        except Exception:
            pass

    # --------------------------------------------------------
    # PROCURAR URLS NO HTML
    # --------------------------------------------------------

    links.extend(
        extrair_urls_texto(
            texto,
            url_base
        )
    )

    # --------------------------------------------------------
    # EXTRAIR IDs MLB
    # --------------------------------------------------------

    ids = re.findall(
        r'\bMLB[-_]?(\d{5,})\b',
        texto,
        flags=re.IGNORECASE
    )

    for produto_id in ids:

        links.append(
            "https://www.mercadolivre.com.br/"
            f"MLB-{produto_id}"
        )

    # --------------------------------------------------------
    # NORMALIZAR E REMOVER DUPLICADOS
    # --------------------------------------------------------

    resultado = []

    vistos = set()

    for link in links:

        if not link:
            continue

        link = html.unescape(
            link
        )

        link = link.replace(
            "\\/",
            "/"
        )

        link = limpar_link_produto(
            link,
            url_base
        )

        if not parece_produto(
            link
        ):
            continue

        chave = link.lower()

        if chave in vistos:
            continue

        vistos.add(
            chave
        )

        resultado.append(
            link
        )

    print(
        f"📦 {len(resultado)} "
        f"produtos encontrados."
    )

    for i, link in enumerate(
        resultado[:20],
        1
    ):

        print(
            f"   {i}. {link}"
        )

    return resultado


# ============================================================
# EXTRAIR CAMPO META
# ============================================================

def meta_content(
    soup,
    propriedade=None,
    nome=None
):

    if propriedade:

        elemento = soup.find(
            "meta",
            attrs={
                "property":
                    propriedade
            }
        )

        if elemento:

            return (
                elemento.get(
                    "content",
                    ""
                ).strip()
            )

    if nome:

        elemento = soup.find(
            "meta",
            attrs={
                "name":
                    nome
            }
        )

        if elemento:

            return (
                elemento.get(
                    "content",
                    ""
                ).strip()
            )

    return ""


# ============================================================
# EXTRAIR PRODUTO
# ============================================================

def extrair_produto(
    link,
    headers
):

    print(
        f"\n🔎 Lendo produto:"
    )

    print(
        link
    )

    try:

        resposta = session.get(
            link,
            headers=headers,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"🌐 HTTP produto: "
            f"{resposta.status_code}"
        )

        print(
            f"🌐 URL final produto: "
            f"{resposta.url}"
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

        titulo = meta_content(
            soup,
            propriedade="og:title"
        )

    if not titulo:

        titulo = meta_content(
            soup,
            nome="twitter:title"
        )

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
            "Oferta Imperdível "
            "no Mercado Livre!"
        )

    # --------------------------------------------------------
    # IMAGEM
    # --------------------------------------------------------

    foto_url = ""

    foto_url = meta_content(
        soup,
        propriedade="og:image"
    )

    if not foto_url:

        foto_url = meta_content(
            soup,
            nome="twitter:image"
        )

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

    if not foto_url:

        for img in soup.find_all(
            "img"
        ):

            candidato = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy")
                or ""
            )

            if candidato.startswith(
                "http"
            ):

                foto_url = candidato

                break

    # --------------------------------------------------------
    # PROCURAR IMAGEM NO HTML
    # --------------------------------------------------------

    if not foto_url:

        padroes_imagem = [
            r'"original"\s*:\s*"([^"]+)"',
            r'"url"\s*:\s*"([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
            r'https?://[^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*'
        ]

        for padrao in padroes_imagem:

            encontrado = re.search(
                padrao,
                resposta.text,
                re.IGNORECASE
            )

            if encontrado:

                if encontrado.groups():

                    foto_url = encontrado.group(
                        1
                    )

                else:

                    foto_url = encontrado.group(
                        0
                    )

                foto_url = foto_url.replace(
                    "\\/",
                    "/"
                )

                break

    # --------------------------------------------------------
    # LIMPAR
    # --------------------------------------------------------

    titulo = html.unescape(
        titulo
    ).strip()

    foto_url = html.unescape(
        foto_url
    ).strip()

    if foto_url:

        foto_url = foto_url.replace(
            "\\/",
            "/"
        )

    # --------------------------------------------------------
    # ESCAPAR TÍTULO
    # --------------------------------------------------------

    titulo = html.escape(
        titulo
    )

    if not foto_url:

        print(
            "⚠️ Produto sem imagem."
        )

        print(
            f"🔗 {link_final}"
        )

        return None

    print(
        f"✅ Produto encontrado:"
    )

    print(
        f"   📝 {titulo}"
    )

    print(
        f"   🖼️ {foto_url[:200]}"
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
            "o link informado.</b>\n\n"
            "Verifique se o link está correto "
            "e tente novamente."
        )

        return

    print(
        f"🔗 URL final: {url_final}"
    )

    # --------------------------------------------------------
    # IDENTIFICAR PRODUTO OU VITRINE
    # --------------------------------------------------------

    if parece_produto(
        url_final
    ):

        print(
            "🛒 Link identificado como "
            "produto individual."
        )

        links_produtos = [
            url_final
        ]

    else:

        print(
            "🏪 Link identificado como "
            "vitrine/lista."
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

        print(
            "⚠️ Nenhum produto encontrado."
        )

        enviar_mensagem(
            "⚠️ <b>Nenhum produto foi encontrado.</b>\n\n"
            "O link foi acessado, porém os produtos "
            "não foram encontrados no conteúdo recebido "
            "do Mercado Livre.\n\n"
            "Se for uma vitrine que carrega os produtos "
            "dinamicamente, será necessário utilizar "
            "uma fonte/API que forneça os produtos."
        )

        return

    # --------------------------------------------------------
    # HISTÓRICO
    # --------------------------------------------------------

    historico = carregar_historico()

    postados = 0

    encontrados = 0

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
                f"⏭️ Já postado:"
            )

            print(
                link
            )

            continue

        produto = extrair_produto(
            link,
            headers
        )

        if not produto:

            continue

        encontrados += 1

        titulo = produto[
            "titulo"
        ]

        foto_url = produto[
            "foto_url"
        ]

        link_produto = produto[
            "link"
        ]

        # ----------------------------------------------------
        # LEGENDA
        # ----------------------------------------------------

        legenda = (
            f"🔥 <b>{titulo}</b>\n\n"
            f"⚡ <i>Aproveite esta promoção "
            f"por tempo limitado!</i>\n\n"
            f"👉 <b>Clique abaixo para "
            f"ver a oferta:</b>"
        )

        # ----------------------------------------------------
        # PUBLICAR
        # ----------------------------------------------------

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
                "❌ Falha ao publicar produto."
            )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    print(
        "\n" + "=" * 60
    )

    print(
        "🎯 TAREFA FINALIZADA"
    )

    print(
        f"📦 Produtos encontrados: "
        f"{encontrados}"
    )

    print(
        f"📤 Ofertas publicadas: "
        f"{postados}"
    )

    print(
        "=" * 60
    )

    enviar_mensagem(
        "✅ <b>Postagens finalizadas!</b>\n\n"
        f"🔎 Produtos encontrados: "
        f"<b>{encontrados}</b>\n"
        f"📤 Ofertas publicadas: "
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

    print(
        "\n" + "=" * 60
    )

    print(
        "📩 REQUISIÇÃO RECEBIDA"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # CONFIGURAÇÃO
    # --------------------------------------------------------

    if not verificar_configuracao():

        return jsonify({
            "ok": False,
            "erro":
                "Bot não configurado no servidor."
        }), 500

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    try:

        dados = request.get_json(
            silent=True
        )

    except Exception as e:

        print(
            f"❌ Erro lendo JSON: {e}"
        )

        return jsonify({
            "ok": False,
            "erro":
                "Não foi possível ler os dados enviados."
        }), 400

    if not isinstance(
        dados,
        dict
    ):

        print(
            "❌ Payload não é objeto JSON."
        )

        return jsonify({
            "ok": False,
            "erro":
                "Dados inválidos."
        }), 400

    print(
        f"📦 Campos recebidos: "
        f"{list(dados.keys())}"
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
    )

    print(
        f"🔗 Link recebido: {link}"
    )

    print(
        f"🔐 initData recebido: "
        f"{'SIM' if init_data else 'NÃO'}"
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
    # TELEGRAM
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
                "Informe o link da vitrine ou produto."
        }), 400

    link = normalizar_url(
        link
    )

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
        "✅ ORDEM VALIDADA"
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
    # AVISO NO TELEGRAM
    # --------------------------------------------------------

    aviso = enviar_mensagem(
        "🚀 <b>Nova automação iniciada!</b>\n\n"
        f"🔗 Fonte: <code>{html.escape(link)}</code>\n"
        f"📦 Quantidade: <b>{quantidade}</b>\n"
        f"⏱️ Intervalo: <b>{intervalo}s</b>"
    )

    if not aviso:

        print(
            "⚠️ Não foi possível enviar "
            "o aviso inicial ao Telegram."
        )

    # --------------------------------------------------------
    # THREAD
    # --------------------------------------------------------

    try:

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
            "🧵 Thread de processamento iniciada."
        )

    except Exception as e:

        print(
            f"❌ Erro iniciando thread: {e}"
        )

        return jsonify({
            "ok": False,
            "erro":
                "Não foi possível iniciar o processamento.",
            "detalhe":
                str(e)
        }), 500

    # --------------------------------------------------------
    # RESPOSTA JSON
    # --------------------------------------------------------

    resposta = {
        "ok": True,
        "mensagem":
            "Postagens iniciadas.",
        "quantidade":
            quantidade,
        "intervalo":
            intervalo
    }

    print(
        "📤 Respondendo ao Mini App:"
    )

    print(
        resposta
    )

    return jsonify(
        resposta
    ), 200


# ============================================================
# TESTE DE POSTAGEM
# ============================================================

@app.route(
    "/api/teste",
    methods=["GET"]
)
def teste():

    if not verificar_configuracao():

        return jsonify({
            "ok": False,
            "erro":
                "Telegram não configurado."
        }), 500

    sucesso = enviar_mensagem(
        "🦊 <b>Raposa Caçadora</b>\n\n"
        "✅ Teste de conexão realizado "
        "com sucesso."
    )

    return jsonify({
        "ok": sucesso,
        "telegram":
            "conectado"
            if sucesso
            else "erro"
    }), (
        200
        if sucesso
        else 500
    )


# ============================================================
# INFORMAÇÕES DO SERVIDOR
# ============================================================

@app.route(
    "/api/info",
    methods=["GET"]
)
def info():

    return jsonify({
        "ok": True,
        "servico":
            "Raposa Caçadora",
        "max_quantidade":
            MAX_QUANTIDADE,
        "min_intervalo":
            MIN_INTERVALO,
        "telegram_configurado":
            bool(TELEGRAM_TOKEN),
        "chat_id":
            CHAT_ID,
        "mini_app":
            os.path.isfile(INDEX_FILE)
    })


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
        debug=False,
        threaded=True
    )
