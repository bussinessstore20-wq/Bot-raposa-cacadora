import os
import json
import time
import html
import threading
import hashlib
import hmac
from urllib.parse import parse_qsl, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory


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

ARQUIVO_HISTORICO = "produtos_postados.txt"

MAX_QUANTIDADE = 50
MIN_INTERVALO = 10


# ============================================================
# FLASK
# ============================================================

app = Flask(
    __name__,
    static_folder="."
)


# ============================================================
# HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 "
        "Safari/537.36"
    ),
    "Accept-Language": (
        "pt-BR,pt;q=0.9,en;q=0.8"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    )
}


# ============================================================
# ROTAS BÁSICAS
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
            content="width=device-width,
            initial-scale=1.0"
        >

        <title>Raposa Caçadora</title>

        <style>

            * {
                box-sizing: border-box;
            }

            body {
                margin: 0;
                min-height: 100vh;

                display: flex;
                align-items: center;
                justify-content: center;

                background:
                    linear-gradient(
                        135deg,
                        #05070a,
                        #111827
                    );

                color: white;

                font-family:
                    Arial,
                    sans-serif;

                text-align: center;
            }

            .box {
                width: 90%;
                max-width: 500px;

                padding: 35px;

                background:
                    rgba(
                        31,
                        41,
                        55,
                        0.9
                    );

                border:
                    1px solid
                    rgba(
                        255,
                        255,
                        255,
                        0.1
                    );

                border-radius: 20px;

                box-shadow:
                    0 20px 50px
                    rgba(0, 0, 0, .4);
            }

            h1 {
                color: #f97316;
                margin-bottom: 10px;
            }

            p {
                color: #cbd5e1;
            }

            .online {
                color: #4ade80;
                font-weight: bold;
            }

        </style>
    </head>

    <body>

        <div class="box">

            <h1>🦊 Raposa Caçadora</h1>

            <p class="online">
                ● Servidor online
            </p>

            <p>
                Mini App disponível em
                <b>/app</b>
            </p>

            <p>
                API disponível em
                <b>/api/configurar</b>
            </p>

        </div>

    </body>
    </html>
    """


@app.route("/app")
def mini_app():

    try:

        return send_from_directory(
            ".",
            "index.html"
        )

    except Exception as e:

        print(
            f"❌ Erro ao carregar index.html: {e}"
        )

        return """
        <!DOCTYPE html>
        <html lang="pt-BR">
        <body style="
            background:#05070a;
            color:white;
            font-family:Arial;
            text-align:center;
            padding:40px;
        ">

            <h2>❌ Mini App não encontrado</h2>

            <p>
                Verifique se o arquivo
                <b>index.html</b>
                está na mesma pasta do
                <b>main.py</b>.
            </p>

        </body>
        </html>
        """, 404


@app.route("/health")
def health():

    return jsonify({
        "ok": True,
        "servico": "Raposa Caçadora",
        "status": "online"
    })


# ============================================================
# TRATAMENTO GLOBAL DE ERROS
# ============================================================

@app.errorhandler(Exception)
def tratar_erro_global(e):

    print("\n" + "=" * 60)
    print("❌ ERRO INTERNO DO SERVIDOR")
    print("=" * 60)

    print(
        f"Tipo: {type(e).__name__}"
    )

    print(
        f"Erro: {e}"
    )

    import traceback

    traceback.print_exc()

    print("=" * 60)

    return jsonify({
        "ok": False,
        "erro": (
            "Erro interno do servidor: "
            f"{str(e)}"
        )
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
# VALIDAÇÃO DO INIT DATA DO TELEGRAM
# ============================================================

def validar_init_data(init_data):

    if not init_data:

        print(
            "❌ initData vazio."
        )

        return False

    try:

        dados_lista = parse_qsl(
            init_data,
            keep_blank_values=True
        )

        dados = dict(
            dados_lista
        )

        hash_recebido = dados.pop(
            "hash",
            None
        )

        if not hash_recebido:

            print(
                "❌ Hash não encontrado no initData."
            )

            return False


        data_check_string = "\n".join(
            f"{chave}={valor}"
            for chave, valor
            in sorted(
                dados.items()
            )
        )


        # Telegram Mini Apps:
        #
        # secret_key =
        # HMAC_SHA256(
        #     "WebAppData",
        #     BOT_TOKEN
        # )

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
                "✅ initData válido."
            )

        else:

            print(
                "❌ initData inválido."
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
            timeout=30
        )


        print(
            f"📡 Telegram {metodo}: "
            f"HTTP {resposta.status_code}"
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
            f"❌ Erro de conexão com Telegram "
            f"({metodo}): {e}"
        )

        return None


    except ValueError as e:

        print(
            f"❌ Telegram retornou JSON inválido: "
            f"{e}"
        )

        return None


    except Exception as e:

        print(
            f"❌ Erro na API Telegram "
            f"({metodo}): {e}"
        )

        return None


# ============================================================
# ENVIAR MENSAGEM
# ============================================================

def enviar_mensagem(texto):

    dados = {

        "chat_id":
            CHAT_ID,

        "text":
            texto,

        "parse_mode":
            "HTML"

    }


    resultado = telegram_api(
        "sendMessage",
        dados
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
# LIMPAR LINK
# ============================================================

def limpar_link(link):

    if not link:

        return ""

    return str(
        link
    ).strip()


# ============================================================
# VALIDAR URL
# ============================================================

def url_valida(url):

    try:

        resultado = urlparse(
            url
        )

        return (
            resultado.scheme
            in (
                "http",
                "https"
            )
            and bool(
                resultado.netloc
            )
        )

    except Exception:

        return False


# ============================================================
# EXPANDIR LINK
# ============================================================

def expandir_link(
    url,
    headers
):

    try:

        if not url_valida(url):

            print(
                "❌ URL inválida."
            )

            return None


        resposta = requests.get(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=30
        )


        resposta.raise_for_status()


        print(
            f"🔗 URL final: "
            f"{resposta.url}"
        )


        return resposta.url


    except Exception as e:

        print(
            f"❌ Erro ao expandir URL: {e}"
        )

        return None


# ============================================================
# IDENTIFICAR LINK DE PRODUTO
# ============================================================

def parece_produto_mercadolivre(url):

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
# DESCOBRIR PRODUTOS
# ============================================================

def encontrar_links_produtos(
    url_vitrine,
    headers
):

    print(
        f"\n🔎 Acessando vitrine:"
        f"\n{url_vitrine}"
    )


    try:

        resposta = requests.get(
            url_vitrine,
            headers=headers,
            timeout=30
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


        href = href.split(
            "#"
        )[0]


        if any(
            padrao.lower()
            in href.lower()
            for padrao in padroes
        ):

            links.append(
                href
            )


    # --------------------------------------------------------
    # NORMALIZAR LINKS
    # --------------------------------------------------------

    links_finais = []


    for link in links:

        if link.startswith("//"):

            link = (
                "https:"
                + link
            )


        elif link.startswith("/"):

            link = (
                "https://www.mercadolivre.com.br"
                + link
            )


        if url_valida(link):

            links_finais.append(
                link
            )


    # --------------------------------------------------------
    # REMOVER DUPLICADOS
    # --------------------------------------------------------

    links_finais = list(
        dict.fromkeys(
            links_finais
        )
    )


    print(
        f"📦 Produtos encontrados: "
        f"{len(links_finais)}"
    )


    return links_finais


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
            timeout=30
        )


        resposta.raise_for_status()


    except Exception as e:

        print(
            f"⚠️ Erro acessando produto:"
            f" {e}"
        )

        return None


    soup = BeautifulSoup(
        resposta.text,
        "html.parser"
    )


    # ========================================================
    # TÍTULO
    # ========================================================

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
            "Oferta Imperdível "
            "Mercado Livre!"
        )


    # ========================================================
    # IMAGEM
    # ========================================================

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

                or

                img.get("data-src")

                or

                img.get("data-lazy")

                or

                ""

            )


    if not foto_url:

        print(
            "⚠️ Produto sem imagem."
        )

        return None


    # ========================================================
    # LIMPEZA
    # ========================================================

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
# PROCESSAR E POSTAR VITRINE
# ============================================================

def processar_e_postar_vitrine(
    url_vitrine,
    quantidade_maxima,
    intervalo_seg
):

    print("\n" + "=" * 60)

    print(
        "🦊 NOVA TAREFA DE POSTAGEM"
    )

    print("=" * 60)

    print(
        f"🔗 Vitrine: {url_vitrine}"
    )

    print(
        f"📦 Quantidade: "
        f"{quantidade_maxima}"
    )

    print(
        f"⏱️ Intervalo: "
        f"{intervalo_seg}s"
    )

    print("=" * 60)


    # ========================================================
    # EXPANDIR
    # ========================================================

    url_final = expandir_link(
        url_vitrine,
        HEADERS
    )


    if not url_final:

        enviar_mensagem(
            "❌ <b>Não foi possível acessar "
            "a vitrine.</b>"
        )

        return


    # ========================================================
    # DESCOBRIR PRODUTOS
    # ========================================================

    if parece_produto_mercadolivre(
        url_final
    ):

        links_produtos = [
            url_final
        ]

    else:

        links_produtos = (
            encontrar_links_produtos(
                url_final,
                HEADERS
            )
        )


    # ========================================================
    # NENHUM PRODUTO
    # ========================================================

    if not links_produtos:

        print(
            "⚠️ Nenhum produto encontrado."
        )


        enviar_mensagem(
            "⚠️ <b>Nenhum produto foi encontrado.</b>\n\n"
            "Verifique se o link informado "
            "é uma vitrine ou lista válida "
            "do Mercado Livre."
        )

        return


    # ========================================================
    # HISTÓRICO
    # ========================================================

    historico = carregar_historico()

    postados = 0


    # ========================================================
    # PROCESSAMENTO
    # ========================================================

    for link in links_produtos:

        if (
            postados
            >= quantidade_maxima
        ):

            break


        link = link.strip()


        if not link:

            continue


        if link in historico:

            print(
                f"⏭️ Já postado:"
                f" {link}"
            )

            continue


        print(
            "\n🔍 Extraindo produto:"
        )

        print(
            link
        )


        produto = extrair_produto(
            link,
            HEADERS
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

            f"⚡ <i>Aproveite esta "
            f"promoção por tempo limitado!</i>\n\n"

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
                f"{postados}/"
                f"{quantidade_maxima}"
            )


            if (
                postados
                < quantidade_maxima
            ):

                print(
                    f"⏳ Aguardando "
                    f"{intervalo_seg} segundos..."
                )


                time.sleep(
                    intervalo_seg
                )


        else:

            print(
                "❌ Falha ao publicar "
                "produto."
            )


    # ========================================================
    # FINALIZAÇÃO
    # ========================================================

    print("\n" + "=" * 60)

    print(
        f"🎯 FINALIZADO: "
        f"{postados} ofertas publicadas."
    )

    print("=" * 60)


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

    print("\n" + "=" * 60)

    print(
        "📩 NOVA REQUISIÇÃO DO MINI APP"
    )

    print("=" * 60)


    try:

        # ====================================================
        # CONFIGURAÇÃO
        # ====================================================

        if not verificar_configuracao():

            return jsonify({

                "ok":
                    False,

                "erro":
                    "Bot não configurado."

            }), 500


        # ====================================================
        # JSON
        # ====================================================

        dados = request.get_json(
            silent=True
        )


        if not dados:

            print(
                "❌ JSON inválido ou vazio."
            )


            return jsonify({

                "ok":
                    False,

                "erro":
                    "Dados JSON inválidos."

            }), 400


        # ====================================================
        # RECEBER DADOS
        # ====================================================

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


        print(
            f"🔗 Link: {link}"
        )

        print(
            f"⏱️ Intervalo: {intervalo}"
        )

        print(
            f"📦 Quantidade: {quantidade}"
        )

        print(
            f"🔐 initData recebido: "
            f"{bool(init_data)}"
        )


        # ====================================================
        # LINK
        # ====================================================

        if not link:

            return jsonify({

                "ok":
                    False,

                "erro":
                    "Informe o link da vitrine."

            }), 400


        if not url_valida(link):

            return jsonify({

                "ok":
                    False,

                "erro":
                    "O link informado é inválido."

            }), 400


        # ====================================================
        # INIT DATA
        # ====================================================

        if not init_data:

            return jsonify({

                "ok":
                    False,

                "erro":
                    "Autenticação do Telegram "
                    "não foi enviada."

            }), 403


        if not validar_init_data(
            init_data
        ):

            return jsonify({

                "ok":
                    False,

                "erro":
                    "Autenticação do Telegram "
                    "inválida."

            }), 403


        # ====================================================
        # INTERVALO
        # ====================================================

        try:

            intervalo = int(
                intervalo
            )

        except Exception:

            intervalo = 300


        if intervalo < MIN_INTERVALO:

            intervalo = MIN_INTERVALO


        # ====================================================
        # QUANTIDADE
        # ====================================================

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


        # ====================================================
        # CONFIGURAÇÃO VALIDADA
        # ====================================================

        print("\n" + "=" * 60)

        print(
            "✅ CONFIGURAÇÃO VALIDADA"
        )

        print("=" * 60)

        print(
            f"🔗 Link: {link}"
        )

        print(
            f"⏱️ Intervalo: "
            f"{intervalo}s"
        )

        print(
            f"📦 Quantidade: "
            f"{quantidade}"
        )

        print("=" * 60)


        # ====================================================
        # AVISO TELEGRAM
        # ====================================================

        aviso = enviar_mensagem(

            "🚀 <b>Nova automação iniciada!</b>\n\n"

            f"📦 Quantidade: "
            f"<b>{quantidade}</b>\n"

            f"⏱️ Intervalo: "
            f"<b>{intervalo}s</b>"

        )


        if aviso:

            print(
                "✅ Aviso enviado ao Telegram."
            )

        else:

            print(
                "⚠️ Aviso inicial não "
                "foi enviado."
            )


        # ====================================================
        # THREAD
        # ====================================================

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


        print(
            "✅ Thread iniciada."
        )


        # ====================================================
        # RESPOSTA AO MINI APP
        # ====================================================

        resposta = {

            "ok":
                True,

            "mensagem":
                "Postagens iniciadas."

        }


        print(
            f"📤 Resposta: {resposta}"
        )

        print("=" * 60)


        return jsonify(
            resposta
        ), 200


    except Exception as e:

        print("\n" + "=" * 60)

        print(
            "🔥 ERRO NA API /api/configurar"
        )

        print("=" * 60)

        print(
            f"Tipo: {type(e).__name__}"
        )

        print(
            f"Erro: {e}"
        )


        import traceback

        traceback.print_exc()


        print("=" * 60)


        return jsonify({

            "ok":
                False,

            "erro":
                "Erro interno do servidor: "
                f"{str(e)}"

        }), 500


# ============================================================
# INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":

    print("\n" + "=" * 60)

    print(
        "🦊 RAPOSA CAÇADORA"
    )

    print("=" * 60)


    if TELEGRAM_TOKEN:

        print(
            "✅ TELEGRAM_TOKEN configurado."
        )

    else:

        print(
            "⚠️ TELEGRAM_TOKEN NÃO configurado."
        )


    if CHAT_ID:

        print(
            f"✅ CHAT_ID: {CHAT_ID}"
        )

    else:

        print(
            "⚠️ CHAT_ID não configurado."
        )


    print(
        f"🌐 Porta: {PORT}"
    )


    if WEBAPP_URL:

        print(
            f"📱 Mini App:"
            f" {WEBAPP_URL}/app"
        )

    else:

        print(
            "⚠️ WEBAPP_URL não configurada."
        )


    print(
        f"❤️ Health:"
        f" /health"
    )


    print("=" * 60)


    app.run(

        host="0.0.0.0",

        port=PORT,

        debug=False

    )
