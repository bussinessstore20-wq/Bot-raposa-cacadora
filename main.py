import os
import json
import time
import html
import threading
import hashlib
import hmac
from urllib.parse import parse_qsl, urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory


# ============================================================
# CONFIGURAÇÃO GERAL
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INDEX_FILE = os.path.join(BASE_DIR, "index.html")

ARQUIVO_HISTORICO = os.path.join(
    BASE_DIR,
    "produtos_postados.txt"
)

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

TIMEOUT_HTTP = 30


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


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
        "Chrome/152.0.0.0 "
        "Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Connection": "keep-alive"
})


# ============================================================
# HOME
# ============================================================

@app.route("/", methods=["GET"])
def home():

    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport"
              content="width=device-width, initial-scale=1.0">
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
                <a href="/app">abrir painel</a>
            </p>

            <p>
                Health:
                <a href="/health">verificar servidor</a>
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

        print("❌ index.html não encontrado.")

        return """
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <title>Erro</title>
        </head>

        <body style="
            background:#05070a;
            color:white;
            font-family:Arial;
            padding:30px;
        ">

            <h2>❌ Mini App não encontrado</h2>

            <p>
                O arquivo index.html não está
                junto do main.py.
            </p>

        </body>
        </html>
        """, 404

    print("✅ index.html encontrado.")

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "ok": True,
        "servico": "Raposa Caçadora",
        "status": "online",
        "mini_app": os.path.isfile(INDEX_FILE),
        "telegram_configurado": bool(TELEGRAM_TOKEN),
        "chat_configurado": bool(CHAT_ID),
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
        print("❌ TELEGRAM_TOKEN não configurado.")
        return False

    if not CHAT_ID:
        print("❌ CHAT_ID não configurado.")
        return False

    return True


# ============================================================
# VALIDAR INIT DATA TELEGRAM
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
            f"⚠️ Erro validando initData: {e}"
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
            f"⚠️ Erro salvando histórico: {e}"
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
            timeout=TIMEOUT_HTTP
        )

        print(
            f"📡 Telegram HTTP: "
            f"{resposta.status_code}"
        )

        try:

            resultado = resposta.json()

        except Exception:

            print(
                "❌ Telegram não retornou JSON."
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
            f"❌ Erro conexão Telegram "
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

    sucesso = bool(
        resultado
        and resultado.get("ok")
    )

    print(
        f"📨 Mensagem Telegram enviada: {sucesso}"
    )

    return sucesso


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

    sucesso = bool(
        resultado
        and resultado.get("ok")
    )

    print(
        f"📸 Oferta enviada: {sucesso}"
    )

    return sucesso


# ============================================================
# NORMALIZAR URL
# ============================================================

def normalizar_url(url):

    if not url:
        return None

    try:

        url = str(url).strip()

        url = url.replace(
            "\n",
            ""
        ).replace(
            "\r",
            ""
        )

        url = url.strip(
            "\"'<> "
        )

        if not url:
            return None

        if not url.startswith(
            ("http://", "https://")
        ):
            url = "https://" + url

        partes = urlparse(url)

        if partes.scheme not in (
            "http",
            "https"
        ):
            return None

        if not partes.netloc:
            return None

        return url

    except Exception as e:

        print(
            f"⚠️ URL inválida: {e}"
        )

        return None


# ============================================================
# EXPANDIR LINK
# ============================================================

def expandir_link(
    url,
    headers=None
):

    url = normalizar_url(url)

    if not url:
        return None

    print(
        f"🔗 Expandindo: {url}"
    )

    try:

        resposta = session.get(
            url,
            headers=headers or {},
            allow_redirects=True,
            timeout=TIMEOUT_HTTP
        )

        print(
            f"📡 HTTP expansão: "
            f"{resposta.status_code}"
        )

        print(
            f"🔗 URL final recebida: "
            f"{resposta.url}"
        )

        url_final = normalizar_url(
            resposta.url
        )

        if not url_final:
            return None

        return url_final

    except requests.RequestException as e:

        print(
            f"❌ Erro HTTP expandindo URL: {e}"
        )

        return None

    except Exception as e:

        print(
            f"❌ Erro expandindo URL: {e}"
        )

        return None


# ============================================================
# IDENTIFICAR PRODUTO
# ============================================================

def parece_produto_mercadolivre(url):

    if not url:
        return False

    texto = unquote(
        url
    ).lower()

    padroes = [
        "produto.mercadolivre.com.br",
        "mercadolivre.com.br/p/",
        "mercadolivre.com.br/mlb-",
        "mercadolivre.com.br/mla-",
        "/p/mlb",
        "/p/mla",
        "mlb-"
    ]

    return any(
        padrao in texto
        for padrao in padroes
    )


# ============================================================
# LIMPAR LINK
# ============================================================

def limpar_link_produto(
    href,
    base_url
):

    if not href:
        return None

    try:

        href = html.unescape(
            href.strip()
        )

        href = href.strip(
            "\"'<> "
        )

        if not href:
            return None

        # Alguns links possuem escapes
        href = href.replace(
            "\\/",
            "/"
        )

        # Link absoluto
        if href.startswith(
            "http://"
        ) or href.startswith(
            "https://"
        ):

            resultado = href

        else:

            # Só fazemos urljoin com uma base
            # comprovadamente válida.
            base_normalizada = normalizar_url(
                base_url
            )

            if not base_normalizada:
                return None

            resultado = urljoin(
                base_normalizada,
                href
            )

        resultado = normalizar_url(
            resultado
        )

        if not resultado:
            return None

        resultado = resultado.split(
            "#"
        )[0]

        return resultado

    except Exception as e:

        print(
            f"⚠️ Erro normalizando link: "
            f"{href[:200]} | {e}"
        )

        return None


# ============================================================
# DESCOBRIR LINKS DOS PRODUTOS
# ============================================================

def encontrar_links_produtos(
    url_vitrine,
    headers=None
):

    url_vitrine = normalizar_url(
        url_vitrine
    )

    if not url_vitrine:
        return []

    print(
        ""
    )

    print(
        "=" * 60
    )

    print(
        "🔎 PROCURANDO PRODUTOS"
    )

    print(
        "=" * 60
    )

    print(
        f"🌐 URL: {url_vitrine}"
    )

    try:

        resposta = session.get(
            url_vitrine,
            headers=headers or {},
            allow_redirects=True,
            timeout=TIMEOUT_HTTP
        )

        print(
            f"📡 HTTP vitrine: "
            f"{resposta.status_code}"
        )

        print(
            f"🔗 URL efetiva: "
            f"{resposta.url}"
        )

        resposta.raise_for_status()

    except Exception as e:

        print(
            f"❌ Erro acessando vitrine: {e}"
        )

        return []

    base_url = normalizar_url(
        resposta.url
    )

    if not base_url:

        print(
            "❌ URL base inválida."
        )

        return []

    soup = BeautifulSoup(
        resposta.text,
        "html.parser"
    )

    links = []

    # --------------------------------------------------------
    # LINKS <a>
    # --------------------------------------------------------

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a.get(
            "href"
        )

        encontrado = limpar_link_produto(
            href,
            base_url
        )

        if not encontrado:
            continue

        if parece_produto_mercadolivre(
            encontrado
        ):

            links.append(
                encontrado
            )

    # --------------------------------------------------------
    # LINKS EM ATRIBUTOS
    # --------------------------------------------------------

    atributos = [
        "data-href",
        "data-url",
        "data-link",
        "href"
    ]

    for elemento in soup.find_all():

        for atributo in atributos:

            valor = elemento.get(
                atributo
            )

            if not valor:
                continue

            encontrado = limpar_link_produto(
                valor,
                base_url
            )

            if not encontrado:
                continue

            if parece_produto_mercadolivre(
                encontrado
            ):

                links.append(
                    encontrado
                )

    # --------------------------------------------------------
    # BUSCAR PADRÕES NO HTML
    # --------------------------------------------------------

    texto_html = resposta.text

    import re

    padroes_regex = [

        r'https?://produto\.mercadolivre\.com\.br/[^\s"\'<>]+',

        r'https?://www\.mercadolivre\.com\.br/[^\s"\'<>]+',

        r'https?://mercadolivre\.com\.br/[^\s"\'<>]+',

        r'https?:\\/\\/produto\.mercadolivre\.com\.br\\/[^\s"\'<>]+',

        r'https?:\\/\\/www\.mercadolivre\.com\.br\\/[^\s"\'<>]+'
    ]

    for padrao in padroes_regex:

        try:

            encontrados_regex = re.findall(
                padrao,
                texto_html,
                flags=re.IGNORECASE
            )

        except Exception:
            encontrados_regex = []

        for encontrado in encontrados_regex:

            encontrado = encontrado.replace(
                "\\/",
                "/"
            )

            encontrado = html.unescape(
                encontrado
            )

            encontrado = encontrado.rstrip(
                "\"'<>),;"
            )

            url_produto = normalizar_url(
                encontrado
            )

            if not url_produto:
                continue

            if parece_produto_mercadolivre(
                url_produto
            ):

                links.append(
                    url_produto
                )

    # --------------------------------------------------------
    # REMOVER DUPLICADOS
    # --------------------------------------------------------

    resultado_final = []

    vistos = set()

    for link in links:

        if not link:
            continue

        chave = link.rstrip(
            "/"
        ).lower()

        if chave in vistos:
            continue

        vistos.add(
            chave
        )

        resultado_final.append(
            link
        )

    print(
        f"📦 Produtos encontrados: "
        f"{len(resultado_final)}"
    )

    for numero, produto_link in enumerate(
        resultado_final[:20],
        start=1
    ):

        print(
            f"   {numero}. {produto_link}"
        )

    print(
        "=" * 60
    )

    return resultado_final


# ============================================================
# EXTRAIR TEXTO META
# ============================================================

def obter_meta(
    soup,
    atributo,
    valor
):

    elemento = soup.find(
        "meta",
        attrs={
            atributo: valor
        }
    )

    if not elemento:
        return ""

    return (
        elemento.get(
            "content",
            ""
        )
        or ""
    ).strip()


# ============================================================
# EXTRAIR PRODUTO
# ============================================================

def extrair_produto(
    link,
    headers=None
):

    link = normalizar_url(
        link
    )

    if not link:
        return None

    print(
        f"🔍 Extraindo produto: {link}"
    )

    try:

        resposta = session.get(
            link,
            headers=headers or {},
            allow_redirects=True,
            timeout=TIMEOUT_HTTP
        )

        print(
            f"📡 HTTP produto: "
            f"{resposta.status_code}"
        )

        resposta.raise_for_status()

    except Exception as e:

        print(
            f"⚠️ Erro acessando produto: {e}"
        )

        return None

    url_final = normalizar_url(
        resposta.url
    ) or link

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

        titulo = obter_meta(
            soup,
            "property",
            "og:title"
        )

    if not titulo:

        titulo = obter_meta(
            soup,
            "name",
            "twitter:title"
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

    foto_url = obter_meta(
        soup,
        "property",
        "og:image"
    )

    if not foto_url:

        foto_url = obter_meta(
            soup,
            "name",
            "twitter:image"
        )

    # --------------------------------------------------------
    # IMAGEM IMG
    # --------------------------------------------------------

    if not foto_url:

        classes_imagem = [
            "ui-pdp-image",
            "ui-pdp-gallery__figure__image"
        ]

        for classe in classes_imagem:

            imagem = soup.find(
                "img",
                class_=classe
            )

            if not imagem:
                continue

            foto_url = (
                imagem.get("src")
                or imagem.get("data-src")
                or imagem.get("data-lazy")
                or ""
            )

            if foto_url:
                break

    # --------------------------------------------------------
    # QUALQUER IMAGEM HTTPS
    # --------------------------------------------------------

    if not foto_url:

        for imagem in soup.find_all(
            "img"
        ):

            candidato = (
                imagem.get("src")
                or imagem.get("data-src")
                or imagem.get("data-lazy")
                or ""
            )

            if not candidato:
                continue

            if candidato.startswith(
                "http://"
            ) or candidato.startswith(
                "https://"
            ):

                foto_url = candidato

                break

    # --------------------------------------------------------
    # NORMALIZAR IMAGEM
    # --------------------------------------------------------

    if foto_url:

        foto_url = html.unescape(
            foto_url
        ).strip()

    if not foto_url:

        print(
            "⚠️ Produto sem imagem."
        )

        return None

    titulo_limpo = html.escape(
        titulo,
        quote=False
    )

    return {
        "titulo": titulo_limpo,
        "foto_url": foto_url,
        "link": url_final
    }


# ============================================================
# PROCESSAR VITRINE
# ============================================================

def processar_e_postar_vitrine(
    url_vitrine,
    quantidade_maxima,
    intervalo_seg
):

    try:

        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/152.0.0.0 "
                "Safari/537.36"
            ),
            "Accept-Language":
                "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            )
        }

        print(
            ""
        )

        print(
            "=" * 60
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

        # ----------------------------------------------------
        # NORMALIZAR
        # ----------------------------------------------------

        url_vitrine = normalizar_url(
            url_vitrine
        )

        if not url_vitrine:

            enviar_mensagem(
                "❌ <b>Link inválido.</b>\n\n"
                "Não foi possível interpretar "
                "o link enviado."
            )

            return

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
                "o link informado.</b>\n\n"
                "Verifique se o link está público "
                "e tente novamente."
            )

            return

        print(
            f"🔗 URL final: {url_final}"
        )

        # ----------------------------------------------------
        # IDENTIFICAR PRODUTO OU VITRINE
        # ----------------------------------------------------

        if parece_produto_mercadolivre(
            url_final
        ):

            print(
                "🛒 O link final parece ser "
                "um produto."
            )

            links_produtos = [
                url_final
            ]

        else:

            print(
                "🏪 O link final parece ser "
                "uma vitrine/lista."
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
                "possível localizar produtos públicos "
                "na página.\n\n"
                "Se for uma vitrine do Mercado Livre, "
                "verifique se ela está pública."
            )

            print(
                "⚠️ Nenhum produto encontrado."
            )

            return

        # ----------------------------------------------------
        # HISTÓRICO
        # ----------------------------------------------------

        historico = carregar_historico()

        postados = 0

        tentativas = 0

        max_tentativas = max(
            len(links_produtos),
            quantidade_maxima
        )

        # ----------------------------------------------------
        # LOOP
        # ----------------------------------------------------

        for link in links_produtos:

            if postados >= quantidade_maxima:
                break

            if tentativas >= max_tentativas:
                break

            tentativas += 1

            if not link:
                continue

            link = normalizar_url(
                link
            )

            if not link:
                continue

            # ------------------------------------------------
            # HISTÓRICO
            # ------------------------------------------------

            if link.rstrip(
                "/"
            ).lower() in {
                x.rstrip("/").lower()
                for x in historico
            }:

                print(
                    f"⏭️ Já postado: {link}"
                )

                continue

            # ------------------------------------------------
            # EXTRAIR
            # ------------------------------------------------

            produto = extrair_produto(
                link,
                headers
            )

            if not produto:

                print(
                    "⚠️ Não foi possível "
                    "extrair produto."
                )

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

            # ------------------------------------------------
            # LEGENDA
            # ------------------------------------------------

            legenda = (
                f"🔥 <b>{titulo}</b>\n\n"
                f"⚡ <i>Aproveite esta oferta "
                f"por tempo limitado!</i>\n\n"
                f"🛒 <b>Confira o preço e "
                f"as condições no Mercado Livre.</b>"
            )

            # ------------------------------------------------
            # PUBLICAR
            # ------------------------------------------------

            print(
                f"📤 Publicando: {titulo}"
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
                    "❌ Falha ao publicar oferta."
                )

        # ----------------------------------------------------
        # FINAL
        # ----------------------------------------------------

        print(
            ""
        )

        print(
            "=" * 60
        )

        print(
            f"🎯 FINALIZADO: "
            f"{postados} ofertas."
        )

        print(
            "=" * 60
        )

        if postados > 0:

            enviar_mensagem(
                "✅ <b>Postagens finalizadas!</b>\n\n"
                f"🦊 Ofertas publicadas: "
                f"<b>{postados}</b>\n"
                f"📦 Solicitadas: "
                f"<b>{quantidade_maxima}</b>"
            )

        else:

            enviar_mensagem(
                "⚠️ <b>Automação finalizada.</b>\n\n"
                "Nenhuma oferta conseguiu ser publicada."
            )

    except Exception as e:

        print(
            ""
        )

        print(
            "❌ ERRO FATAL NA AUTOMAÇÃO"
        )

        print(
            repr(e)
        )

        enviar_mensagem(
            "❌ <b>Erro durante a automação.</b>\n\n"
            "O processamento foi interrompido.\n"
            "Verifique os logs do servidor."
        )


# ============================================================
# PROCESSAR POST
# ============================================================

def processar_configuracao():

    # --------------------------------------------------------
    # CONFIGURAÇÃO
    # --------------------------------------------------------

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

    if not isinstance(
        dados,
        dict
    ):

        return jsonify({
            "ok": False,
            "erro": "Dados JSON inválidos."
        }), 400

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
    # VALIDAR LINK
    # --------------------------------------------------------

    link_normalizado = normalizar_url(
        link
    )

    if not link_normalizado:

        return jsonify({
            "ok": False,
            "erro":
                "Informe um link válido."
        }), 400

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

    print(
        ""
    )

    print(
        "=" * 60
    )

    print(
        "🚀 ORDEM RECEBIDA"
    )

    print(
        "=" * 60
    )

    print(
        f"🔗 Link: {link_normalizado}"
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
    # AVISO TELEGRAM
    # --------------------------------------------------------

    aviso = enviar_mensagem(
        "🚀 <b>Nova automação iniciada!</b>\n\n"
        f"🔗 Link recebido:\n"
        f"<code>{html.escape(link_normalizado)}</code>\n\n"
        f"📦 Quantidade: <b>{quantidade}</b>\n"
        f"⏱️ Intervalo: <b>{intervalo}s</b>"
    )

    print(
        f"📨 Aviso enviado: {aviso}"
    )

    # --------------------------------------------------------
    # THREAD
    # --------------------------------------------------------

    thread = threading.Thread(
        target=processar_e_postar_vitrine,
        args=(
            link_normalizado,
            quantidade,
            intervalo
        ),
        daemon=True
    )

    thread.start()

    print(
        "✅ Thread da automação iniciada."
    )

    # --------------------------------------------------------
    # RESPOSTA IMEDIATA
    # --------------------------------------------------------

    return jsonify({
        "ok": True,
        "mensagem":
            "Postagens iniciadas.",
        "link":
            link_normalizado,
        "quantidade":
            quantidade,
        "intervalo":
            intervalo
    }), 200


# ============================================================
# API PRINCIPAL
#
# IMPORTANTE:
# Existe SOMENTE UMA função para /api/configurar.
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    return processar_configuracao()


# ============================================================
# ROTA ALTERNATIVA
#
# Também aceita POST.
# NÃO existe função configurar_get.
# ============================================================

@app.route(
    "/configurar",
    methods=["POST"]
)
def configurar_alternativa():

    return processar_configuracao()


# ============================================================
# GET /configurar
# ============================================================

@app.route(
    "/configurar",
    methods=["GET"]
)
def configurar_info():

    return jsonify({
        "ok": True,
        "servico": "Raposa Caçadora",
        "rota_recomendada":
            "/api/configurar",
        "metodo":
            "POST",
        "mensagem":
            "A rota /configurar existe. "
            "Para iniciar uma automação use POST."
    })


# ============================================================
# GET /api/configurar
#
# Serve apenas para teste no navegador.
# O Mini App continua usando POST.
# ============================================================

@app.route(
    "/api/configurar",
    methods=["GET"]
)
def configurar_api_info():

    return jsonify({
        "ok": False,
        "erro":
            "A rota /api/configurar "
            "não aceita o método GET.",
        "metodo_correto":
            "POST",
        "rota":
            "/api/configurar"
    }), 405


# ============================================================
# ERRO 404 JSON PARA API
# ============================================================

@app.errorhandler(404)
def erro_404(e):

    if request.path.startswith(
        "/api/"
    ) or request.path == "/configurar":

        return jsonify({
            "ok": False,
            "erro":
                "Rota não encontrada.",
            "rota":
                request.path,
            "metodo":
                request.method
        }), 404

    return e


# ============================================================
# ERRO 405 JSON PARA API
# ============================================================

@app.errorhandler(405)
def erro_405(e):

    return jsonify({
        "ok": False,
        "erro":
            "Método HTTP não permitido.",
        "rota":
            request.path,
        "metodo":
            request.method
    }), 405


# ============================================================
# ERRO 500
# ============================================================

@app.errorhandler(500)
def erro_500(e):

    return jsonify({
        "ok": False,
        "erro":
            "Erro interno no servidor.",
        "detalhe":
            str(e)
    }), 500


# ============================================================
# INFORMAÇÕES DAS ROTAS
# ============================================================

def mostrar_rotas():

    print(
        ""
    )

    print(
        "📚 ROTAS REGISTRADAS:"
    )

    for regra in app.url_map.iter_rules():

        metodos = ",".join(
            sorted(
                regra.methods
            )
        )

        print(
            f"   {regra.rule} "
            f"[{metodos}]"
        )


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    print(
        ""
    )

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
        f"📁 Pasta: {BASE_DIR}"
    )

    print(
        "📄 index.html: "
        + (
            "ENCONTRADO"
            if os.path.isfile(INDEX_FILE)
            else "NÃO ENCONTRADO"
        )
    )

    print(
        "🤖 Telegram Token: "
        + (
            "CONFIGURADO"
            if TELEGRAM_TOKEN
            else "NÃO CONFIGURADO"
        )
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
        debug=False,
        threaded=True
    )
