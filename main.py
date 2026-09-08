import os
import re
import json
import time
import threading
import hashlib
import hmac
from urllib.parse import parse_qsl

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ============================================================
# RAPOSA CAÇADORA - main.py
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE_DIR, "index.html")
ARQUIVO_HISTORICO = os.path.join(BASE_DIR, "produtos_postados.txt")

# ============================================================
# CONFIGURAÇÕES
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "@raposacacadora").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

PORT = int(os.getenv("PORT", "10000"))

MAX_QUANTIDADE = 50
MIN_INTERVALO = 10
HTTP_TIMEOUT = 30

# ============================================================
# FLASK
# ============================================================

app = Flask(__name__, static_folder=BASE_DIR)

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
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"]
)

# ============================================================
# CONTROLES
# ============================================================

automacoes_lock = threading.Lock()
automacoes_ativas = 0

historico_lock = threading.Lock()

session = requests.Session()


# ============================================================
# HEADERS
# ============================================================

def obter_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Connection": "keep-alive"
    }


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
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Raposa Caçadora</title>

        <style>
            body {
                background: #05070a;
                color: white;
                font-family: Arial, sans-serif;
                text-align: center;
                padding-top: 50px;
            }

            h1 {
                color: #f97316;
            }

            a {
                color: #fb923c;
                text-decoration: none;
                font-weight: bold;
            }

            .status {
                margin-top: 20px;
                color: #22c55e;
            }
        </style>
    </head>

    <body>

        <h1>🦊 Raposa Caçadora VIP</h1>

        <p class="status">
            ● SERVIDOR ONLINE E OPERACIONAL
        </p>

        <p>
            <a href="/app">
                Abrir Painel Mini App
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

@app.route("/app", methods=["GET"])
def mini_app():

    if not os.path.isfile(INDEX_FILE):
        return (
            "❌ Arquivo index.html não encontrado "
            "no servidor.",
            404
        )

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health", methods=["GET"])
def health():

    with automacoes_lock:
        ativas = automacoes_ativas

    return jsonify({
        "ok": True,
        "servico": "Raposa Caçadora",
        "status": "online",
        "telegram_configurado": bool(TELEGRAM_TOKEN),
        "chat_configurado": bool(CHAT_ID),
        "automacoes_ativas": ativas
    })


# ============================================================
# VALIDAR TELEGRAM WEB APP
# ============================================================

def validar_init_data(init_data):

    if not init_data:
        print("⚠️ initData não informado.")
        return False

    if not TELEGRAM_TOKEN:
        print("⚠️ TELEGRAM_TOKEN não configurado.")
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
                "⚠️ Hash do Telegram não encontrado."
            )
            return False

        data_check_string = "\n".join(
            f"{k}={v}"
            for k, v in sorted(dados.items())
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

        valido = hmac.compare_digest(
            calculado,
            hash_recebido
        )

        if not valido:
            print(
                "⚠️ initData inválido."
            )

        return valido

    except Exception as e:

        print(
            f"⚠️ Erro ao validar initData: {e}"
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
            ) as f:

                return {
                    linha.strip()
                    for linha in f
                    if linha.strip()
                }

    except Exception as e:

        print(
            f"⚠️ Erro ao carregar histórico: {e}"
        )

        return set()


def salvar_historico(link):

    if not link:
        return False

    try:

        with historico_lock:

            with open(
                ARQUIVO_HISTORICO,
                "a",
                encoding="utf-8"
            ) as f:

                f.write(
                    link.strip() + "\n"
                )

        return True

    except Exception as e:

        print(
            f"⚠️ Erro ao salvar histórico: {e}"
        )

        return False


# ============================================================
# ENVIAR OFERTA PARA TELEGRAM
# ============================================================

def enviar_oferta(
    foto_url,
    legenda,
    link_produto
):

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

    if not foto_url:

        print(
            "❌ URL da imagem não encontrada."
        )

        return False

    if not link_produto:

        print(
            "❌ Link do produto não encontrado."
        )

        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendPhoto"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "🛒 COMPRAR AGORA",
                    "url": link_produto
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
            keyboard
        )
    }

    try:

        res = session.post(
            url,
            data=payload,
            timeout=HTTP_TIMEOUT
        )

        try:
            resultado = res.json()
        except Exception:
            resultado = {}

        if resultado.get("ok"):

            print(
                "✅ Telegram aceitou a publicação."
            )

            return True

        print(
            "❌ Telegram recusou o envio:"
        )

        print(resultado)

        return False

    except Exception as e:

        print(
            f"❌ Erro ao enviar para o Telegram: {e}"
        )

        return False


# ============================================================
# NATURA
# ============================================================

def extrair_dados_natura(
    url_produto
):

    headers = obter_headers()

    try:

        print(
            "🌿 Acessando página da Natura..."
        )

        res = session.get(
            url_produto,
            headers=headers,
            timeout=HTTP_TIMEOUT
        )

        print(
            f"🌿 Status Natura: "
            f"{res.status_code}"
        )

        res.raise_for_status()

        soup = BeautifulSoup(
            res.text,
            "html.parser"
        )

        # ----------------------------------------------------
        # TÍTULO
        # ----------------------------------------------------

        og_title = soup.find(
            "meta",
            property="og:title"
        )

        titulo = (
            og_title.get(
                "content",
                ""
            ).strip()
            if og_title
            else ""
        )

        if not titulo:

            h1 = soup.find("h1")

            titulo = (
                h1.get_text(
                    " ",
                    strip=True
                )
                if h1
                else "Oferta Exclusiva Natura!"
            )

        # ----------------------------------------------------
        # IMAGEM
        # ----------------------------------------------------

        og_image = soup.find(
            "meta",
            property="og:image"
        )

        foto_url = (
            og_image.get(
                "content",
                ""
            ).strip()
            if og_image
            else ""
        )

        if not foto_url:

            img = soup.find(
                "img",
                src=re.compile(
                    r"natura|product",
                    re.IGNORECASE
                )
            )

            if img:

                foto_url = (
                    img.get("src")
                    or img.get("data-src")
                    or ""
                )

        print(
            f"🌿 Título encontrado: {titulo}"
        )

        print(
            f"🌿 Imagem encontrada: "
            f"{bool(foto_url)}"
        )

        return titulo, foto_url

    except Exception as e:

        print(
            f"⚠️ Erro ao extrair dados da Natura: "
            f"{e}"
        )

        return None, None


# ============================================================
# MERCADO LIVRE
# ============================================================

def extrair_produtos_mercado_livre(
    url_final
):

    headers = obter_headers()

    try:

        print(
            "🛒 Acessando página do Mercado Livre..."
        )

        res = session.get(
            url_final,
            headers=headers,
            timeout=HTTP_TIMEOUT
        )

        print(
            f"🛒 Status Mercado Livre: "
            f"{res.status_code}"
        )

        print(
            f"🛒 Tamanho do HTML: "
            f"{len(res.text)} caracteres"
        )

        res.raise_for_status()

        soup = BeautifulSoup(
            res.text,
            "html.parser"
        )

        links_encontrados = []

        # ----------------------------------------------------
        # ENCONTRAR LINKS
        # ----------------------------------------------------

        for a in soup.find_all(
            "a",
            href=True
        ):

            href = a["href"]

            if any(
                p in href
                for p in [
                    "produto.mercadolivre.com.br",
                    "/p/MLB",
                    "MLB-",
                    "/sec/"
                ]
            ):

                links_encontrados.append(
                    href.split("#")[0]
                )

        # ----------------------------------------------------
        # META TAGS
        # ----------------------------------------------------

        for meta in soup.find_all(
            "meta"
        ):

            content = meta.get(
                "content",
                ""
            )

            if not content:
                continue

            if (
                "mercadolivre.com.br"
                in content
            ):

                if any(
                    p in content
                    for p in [
                        "/p/MLB",
                        "MLB-",
                        "produto.mercadolivre"
                    ]
                ):

                    links_encontrados.append(
                        content
                    )

        # ----------------------------------------------------
        # REMOVER DUPLICADOS
        # ----------------------------------------------------

        links_unicos = list(
            dict.fromkeys(
                links_encontrados
            )
        )

        print(
            f"🔎 Links encontrados no HTML: "
            f"{len(links_unicos)}"
        )

        return links_unicos

    except requests.exceptions.Timeout:

        print(
            "❌ Timeout ao acessar "
            "o Mercado Livre."
        )

        return []

    except requests.exceptions.RequestException as e:

        print(
            f"❌ Erro HTTP Mercado Livre: {e}"
        )

        return []

    except Exception as e:

        print(
            f"⚠️ Erro ao extrair produtos "
            f"do Mercado Livre: {e}"
        )

        return []


# ============================================================
# DADOS DO PRODUTO MERCADO LIVRE
# ============================================================

def extrair_dados_produto_mercado_livre(
    link
):

    headers = obter_headers()

    try:

        print(
            f"🔎 Abrindo produto: {link}"
        )

        prod_res = session.get(
            link,
            headers=headers,
            allow_redirects=True,
            timeout=HTTP_TIMEOUT
        )

        print(
            f"📊 Status produto: "
            f"{prod_res.status_code}"
        )

        prod_res.raise_for_status()

        prod_soup = BeautifulSoup(
            prod_res.text,
            "html.parser"
        )

        # ----------------------------------------------------
        # TÍTULO
        # ----------------------------------------------------

        titulo_elem = prod_soup.find(
            "h1",
            {
                "class": "ui-pdp-title"
            }
        )

        titulo = (
            titulo_elem.get_text(
                " ",
                strip=True
            )
            if titulo_elem
            else ""
        )

        # ----------------------------------------------------
        # FALLBACK OG TITLE
        # ----------------------------------------------------

        if not titulo:

            og_title = prod_soup.find(
                "meta",
                property="og:title"
            )

            if og_title:

                titulo = (
                    og_title.get(
                        "content",
                        ""
                    ).strip()
                )

        if not titulo:

            titulo = (
                "🔥 Oferta Imperdível "
                "Mercado Livre!"
            )

        # ----------------------------------------------------
        # IMAGEM
        # ----------------------------------------------------

        foto_url = ""

        foto_elem = prod_soup.find(
            "img",
            {
                "class": "ui-pdp-image"
            }
        )

        if foto_elem:

            foto_url = (
                foto_elem.get("src")
                or foto_elem.get("data-src")
                or ""
            )

        # ----------------------------------------------------
        # FALLBACK OG IMAGE
        # ----------------------------------------------------

        if not foto_url:

            og_image = prod_soup.find(
                "meta",
                property="og:image"
            )

            if og_image:

                foto_url = (
                    og_image.get(
                        "content",
                        ""
                    ).strip()
                )

        print(
            f"📝 Título: {titulo}"
        )

        print(
            f"🖼️ Imagem encontrada: "
            f"{bool(foto_url)}"
        )

        return titulo, foto_url

    except requests.exceptions.Timeout:

        print(
            "❌ Timeout ao abrir produto."
        )

        return None, None

    except requests.exceptions.RequestException as e:

        print(
            f"❌ Erro HTTP ao abrir produto: "
            f"{e}"
        )

        return None, None

    except Exception as e:

        print(
            f"⚠️ Erro ao extrair produto: "
            f"{e}"
        )

        return None, None


# ============================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================

def processar_e_postar_vitrine(
    url_vitrine,
    quantidade_maxima,
    intervalo_seg
):

    global automacoes_ativas

    headers = obter_headers()

    with automacoes_lock:
        automacoes_ativas += 1

    try:

        print("")
        print("=" * 60)
        print(
            f"🦊 Processando URL: "
            f"{url_vitrine}"
        )
        print("=" * 60)

        # ====================================================
        # EXPANDIR LINK
        # ====================================================

        print(
            "🔄 Tentando expandir o link..."
        )

        try:

            inicio = time.time()

            res_redir = session.get(
                url_vitrine,
                headers=headers,
                allow_redirects=True,
                timeout=HTTP_TIMEOUT
            )

            tempo = time.time() - inicio

            url_final = res_redir.url

            print(
                f"✅ Redirecionamento concluído "
                f"em {tempo:.2f}s"
            )

            print(
                f"📊 Status HTTP: "
                f"{res_redir.status_code}"
            )

            print(
                f"🔗 URL final: "
                f"{url_final}"
            )

            print(
                f"↪️ Histórico de "
                f"redirecionamentos: "
                f"{len(res_redir.history)}"
            )

            for i, redirect in enumerate(
                res_redir.history,
                start=1
            ):

                print(
                    f"   {i}. "
                    f"{redirect.status_code} -> "
                    f"{redirect.headers.get('location', '')}"
                )

        except requests.exceptions.Timeout:

            print(
                "❌ TIMEOUT ao tentar expandir "
                "o link meli.la."
            )

            return

        except requests.exceptions.TooManyRedirects:

            print(
                "❌ Muitos redirecionamentos "
                "no meli.la."
            )

            return

        except requests.exceptions.RequestException as e:

            print(
                f"❌ Erro HTTP ao expandir "
                f"o meli.la: {e}"
            )

            return

        except Exception as e:

            print(
                f"❌ Erro inesperado ao expandir "
                f"o link: {e}"
            )

            return

        # ====================================================
        # NATURA
        # ====================================================

        if "natura.com.br" in url_final.lower():

            print(
                "🌿 Plataforma detectada: NATURA"
            )

            titulo, foto_url = (
                extrair_dados_natura(
                    url_final
                )
            )

            if not titulo:

                print(
                    "❌ Não foi possível obter "
                    "o título da Natura."
                )

                return

            if not foto_url:

                print(
                    "❌ Não foi possível obter "
                    "a imagem da Natura."
                )

                return

            legenda = (
                f"🌿 <b>{titulo}</b>\n\n"
                f"✨ <i>Aproveite esta oferta "
                f"no meu Espaço Natura!</i>\n\n"
                f"👉 <b>Clique abaixo para "
                f"ver a oferta:</b>"
            )

            if enviar_oferta(
                foto_url,
                legenda,
                url_vitrine
            ):

                salvar_historico(
                    url_vitrine
                )

                print(
                    "✅ Oferta da Natura "
                    "postada com sucesso!"
                )

            return

        # ====================================================
        # MERCADO LIVRE
        # ====================================================

        if (
            "mercadolivre.com.br"
            in url_final.lower()
            or
            "mercadolibre.com"
            in url_final.lower()
            or
            "meli.la"
            in url_vitrine.lower()
        ):

            print(
                "🛒 Plataforma detectada: "
                "MERCADO LIVRE"
            )

            print(
                "🔍 Buscando produtos..."
            )

            links_unicos = (
                extrair_produtos_mercado_livre(
                    url_final
                )
            )

            print(
                f"🔎 Produtos encontrados: "
                f"{len(links_unicos)}"
            )

            # =================================================
            # LINK INDIVIDUAL
            # =================================================

            if not links_unicos and (
                "/p/MLB" in url_final
                or
                "MLB-" in url_final
                or
                "produto.mercadolivre.com.br"
                in url_final
            ):

                print(
                    "🎯 O link final parece ser "
                    "um produto individual."
                )

                links_unicos = [
                    url_final
                ]

            # =================================================
            # NENHUM PRODUTO
            # =================================================

            if not links_unicos:

                print(
                    "⚠️ Nenhum produto encontrado "
                    "no HTML."
                )

                print(
                    "📄 O Mercado Livre pode estar "
                    "usando conteúdo dinâmico ou "
                    "proteção contra scraping."
                )

                return

            # =================================================
            # HISTÓRICO
            # =================================================

            historico = carregar_historico()

            postados = 0

            # =================================================
            # PROCESSAR PRODUTOS
            # =================================================

            for link in links_unicos:

                if postados >= quantidade_maxima:

                    break

                if link in historico:

                    print(
                        "⏭️ Produto já publicado. "
                        "Ignorando."
                    )

                    continue

                try:

                    titulo, foto_url = (
                        extrair_dados_produto_mercado_livre(
                            link
                        )
                    )

                    if not titulo:

                        print(
                            "⚠️ Título não encontrado."
                        )

                        continue

                    if not foto_url:

                        print(
                            "⚠️ Imagem não encontrada."
                        )

                        continue

                    legenda = (
                        f"🔥 <b>{titulo}</b>\n\n"
                        f"⚡ <i>Aproveite esta "
                        f"promoção no Mercado Livre!</i>\n\n"
                        f"👉 <b>Clique abaixo para "
                        f"ver a oferta:</b>"
                    )

                    if enviar_oferta(
                        foto_url,
                        legenda,
                        link
                    ):

                        salvar_historico(
                            link
                        )

                        postados += 1

                        print(
                            f"✅ [POSTADO "
                            f"{postados}/"
                            f"{quantidade_maxima}] "
                            f"{titulo[:60]}..."
                        )

                        if (
                            postados
                            < quantidade_maxima
                        ):

                            print(
                                f"⏳ Aguardando "
                                f"{intervalo_seg}s..."
                            )

                            time.sleep(
                                intervalo_seg
                            )

                except Exception as e:

                    print(
                        f"⚠️ Erro ao processar "
                        f"produto: {e}"
                    )

            print("")
            print(
                f"🏁 Processamento finalizado. "
                f"Total publicado: {postados}"
            )

            return

        # ====================================================
        # PLATAFORMA NÃO RECONHECIDA
        # ====================================================

        print(
            "⚠️ Plataforma não reconhecida."
        )

        print(
            f"🔗 URL final: {url_final}"
        )

    except Exception as e:

        print(
            f"❌ ERRO GERAL NA AUTOMAÇÃO: {e}"
        )

    finally:

        with automacoes_lock:
            automacoes_ativas -= 1

        print(
            "🦊 Thread da automação encerrada."
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

    # ========================================================
    # CORS PREFLIGHT
    # ========================================================

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
        print("=" * 60)
        print("📥 NOVA CONFIGURAÇÃO RECEBIDA")
        print("=" * 60)

        # ====================================================
        # LINK
        # Aceita "link" e "linkCanal"
        # ====================================================

        link = str(
            dados.get(
                "link",
                dados.get(
                    "linkCanal",
                    ""
                )
            )
        ).strip()

        # ====================================================
        # INTERVALO
        # ====================================================

        try:

            intervalo = int(
                dados.get(
                    "intervalo",
                    300
                )
            )

        except Exception:

            intervalo = 300

        # ====================================================
        # QUANTIDADE
        # ====================================================

        try:

            quantidade = int(
                dados.get(
                    "quantidade",
                    5
                )
            )

        except Exception:

            quantidade = 5

        # ====================================================
        # INIT DATA
        # ====================================================

        init_data = str(
            dados.get(
                "initData",
                ""
            )
        ).strip()

        print(
            f"🔗 Link recebido: {link}"
        )

        print(
            f"⏱️ Intervalo: {intervalo}s"
        )

        print(
            f"📦 Quantidade: {quantidade}"
        )

        print(
            f"🔐 initData recebido: "
            f"{bool(init_data)}"
        )

        # ====================================================
        # VALIDAR LINK
        # ====================================================

        if not link:

            return jsonify({
                "erro": (
                    "O link da vitrine "
                    "é obrigatório."
                )
            }), 400

        # ====================================================
        # LIMITES
        # ====================================================

        if quantidade < 1:

            quantidade = 1

        if quantidade > MAX_QUANTIDADE:

            quantidade = MAX_QUANTIDADE

        if intervalo < MIN_INTERVALO:

            intervalo = MIN_INTERVALO

        # ====================================================
        # VALIDAR TELEGRAM
        # ====================================================

        if not validar_init_data(
            init_data
        ):

            return jsonify({
                "erro": (
                    "Autenticação do Telegram "
                    "inválida ou expirada."
                )
            }), 403

        # ====================================================
        # INICIAR THREAD
        # ====================================================

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
            "🚀 Automação iniciada."
        )

        return jsonify({

            "sucesso": True,

            "mensagem": (
                "🦊 Automação iniciada "
                "com sucesso!"
            ),

            "link": link,

            "quantidade": quantidade,

            "intervalo": intervalo

        }), 200

    except Exception as e:

        print(
            f"❌ Erro interno na API: {e}"
        )

        return jsonify({

            "erro": (
                f"Erro interno no servidor: "
                f"{str(e)}"
            )

        }), 500


# ============================================================
# INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":

    print("")
    print("=" * 60)
    print("🦊 RAPOSA CAÇADORA")
    print("=" * 60)

    print(
        f"🌐 Porta: {PORT}"
    )

    print(
        f"🤖 Telegram configurado: "
        f"{bool(TELEGRAM_TOKEN)}"
    )

    print(
        f"📢 Chat configurado: "
        f"{bool(CHAT_ID)}"
    )

    print(
        "🌐 CORS: Vercel autorizado"
    )

    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=PORT
    )
