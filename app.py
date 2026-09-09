import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re

from urllib.parse import parse_qsl

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
# EXTRAÇÃO DE DADOS DO PRODUTO
# ============================================================

def limpar_texto(texto):

    if not texto:
        return ""

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def formatar_preco(valor):

    if valor is None:
        return ""

    valor = str(valor).strip()

    if not valor:
        return ""

    # Remove símbolos
    valor = valor.replace(
        "R$",
        ""
    ).strip()

    # Caso venha no formato brasileiro
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

        limpo = (
            preco_str
            .replace("R$", "")
            .replace(" ", "")
            .replace(".", "")
            .replace(",", ".")
        )

        return float(limpo)

    except Exception:

        return 0.0


def extrair_preco_schema(soup):

    """
    Procura preço em JSON-LD/schema.org.
    """

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        try:

            conteudo = script.string

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

                if "@graph" in dados:

                    blocos.extend(
                        dados["@graph"]
                    )

            for bloco in blocos:

                if not isinstance(
                    bloco,
                    dict
                ):
                    continue

                offers = bloco.get(
                    "offers"
                )

                if isinstance(
                    offers,
                    list
                ):
                    offers = offers[0] if offers else None

                if isinstance(
                    offers,
                    dict
                ):

                    preco = (
                        offers.get("price")
                        or
                        offers.get("lowPrice")
                    )

                    if preco:

                        preco_formatado = (
                            formatar_preco(
                                preco
                            )
                        )

                        if preco_formatado:

                            return preco_formatado

        except Exception:

            continue

    return ""


def extrair_dados_produto(link):

    """
    Acessa o link da oferta e tenta obter:

    - título
    - preço atual
    - preço antigo
    - imagem

    Primeiro tenta os elementos utilizados
    pelo Mercado Livre e depois utiliza
    meta tags / JSON-LD como fallback.
    """

    headers = {

        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),

        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8",

        "Accept-Language":
            "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache"
    }

    try:

        resposta = requests.get(
            link,
            headers=headers,
            timeout=30,
            allow_redirects=True
        )

        if resposta.status_code != 200:

            print(
                "[PRODUTO] HTTP:",
                resposta.status_code
            )

            return {
                "sucesso": False,
                "erro":
                    f"Não foi possível acessar a página. "
                    f"HTTP {resposta.status_code}"
            }

        soup = BeautifulSoup(
            resposta.text,
            "html.parser"
        )

        # ====================================================
        # TÍTULO
        # ====================================================

        titulo = ""

        titulo_elem = (
            soup.find(
                "h1",
                class_="ui-pdp-title"
            )
            or
            soup.find(
                "h1"
            )
        )

        if titulo_elem:

            titulo = limpar_texto(
                titulo_elem.get_text(
                    " ",
                    strip=True
                )
            )

        # Fallback OG:title
        if not titulo:

            meta_titulo = soup.find(
                "meta",
                property="og:title"
            )

            if meta_titulo:

                titulo = limpar_texto(
                    meta_titulo.get(
                        "content",
                        ""
                    )
                )

        # Fallback title
        if not titulo:

            title_tag = soup.find(
                "title"
            )

            if title_tag:

                titulo = limpar_texto(
                    title_tag.get_text(
                        strip=True
                    )
                )

        if not titulo:

            titulo = (
                "Oferta Imperdível"
            )

        # ====================================================
        # PREÇO ATUAL
        # ====================================================

        preco_atual = ""

        # Método principal Mercado Livre
        preco_atual_elem = soup.find(
            "span",
            class_="andes-money-amount__fraction"
        )

        if preco_atual_elem:

            fracao = limpar_texto(
                preco_atual_elem.get_text(
                    strip=True
                )
            )

            container = (
                preco_atual_elem.parent
            )

            centavos = ""

            if container:

                cents_elem = container.find(
                    "span",
                    class_="andes-money-amount__cents"
                )

                if cents_elem:

                    centavos = limpar_texto(
                        cents_elem.get_text(
                            strip=True
                        )
                    )

            if centavos:

                preco_atual = (
                    f"R$ {fracao},{centavos}"
                )

            else:

                preco_atual = (
                    f"R$ {fracao},00"
                )

        # ====================================================
        # FALLBACK: JSON-LD
        # ====================================================

        if not preco_atual:

            preco_atual = (
                extrair_preco_schema(
                    soup
                )
            )

        # ====================================================
        # FALLBACK: META TAGS
        # ====================================================

        if not preco_atual:

            metas_preco = [

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
            ]

            for params in metas_preco:

                meta = soup.find(
                    "meta",
                    attrs=params
                )

                if meta:

                    valor = meta.get(
                        "content",
                        ""
                    )

                    preco_formatado = (
                        formatar_preco(
                            valor
                        )
                    )

                    if preco_formatado:

                        preco_atual = (
                            preco_formatado
                        )

                        break

        # ====================================================
        # PREÇO ANTIGO
        # ====================================================

        preco_antigo = ""

        antigo_container = (
            soup.find(
                "s",
                class_="andes-money-amount"
            )
            or
            soup.find(
                "span",
                class_="andes-money-amount--previous"
            )
        )

        if antigo_container:

            frac_antigo = (
                antigo_container.find(
                    "span",
                    class_="andes-money-amount__fraction"
                )
            )

            cents_antigo = (
                antigo_container.find(
                    "span",
                    class_="andes-money-amount__cents"
                )
            )

            if frac_antigo:

                fracao = limpar_texto(
                    frac_antigo.get_text(
                        strip=True
                    )
                )

                if cents_antigo:

                    centavos = limpar_texto(
                        cents_antigo.get_text(
                            strip=True
                        )
                    )

                    preco_antigo = (
                        f"R$ {fracao},{centavos}"
                    )

                else:

                    preco_antigo = (
                        f"R$ {fracao},00"
                    )

        # ====================================================
        # OUTRAS TENTATIVAS DE PREÇO ANTIGO
        # ====================================================

        if not preco_antigo:

            seletores_antigo = [

                ".andes-money-amount--previous",

                ".ui-pdp-price__part--old",

                ".ui-pdp-price__original-value",

                "[class*='previous']",

                "[class*='old-price']"
            ]

            for seletor in seletores_antigo:

                try:

                    elemento = soup.select_one(
                        seletor
                    )

                    if not elemento:
                        continue

                    texto_preco = (
                        elemento.get_text(
                            " ",
                            strip=True
                        )
                    )

                    encontrado = re.search(
                        r"R\$\s*[\d\.,]+",
                        texto_preco
                    )

                    if encontrado:

                        preco_antigo = (
                            encontrado.group(
                                0
                            )
                        )

                        break

                except Exception:

                    continue

        # ====================================================
        # IMAGEM
        # ====================================================

        foto_url = ""

        # OG Image
        meta_imagem = soup.find(
            "meta",
            property="og:image"
        )

        if meta_imagem:

            foto_url = (
                meta_imagem.get(
                    "content",
                    ""
                ).strip()
            )

        # Fallback img
        if not foto_url:

            img_elem = soup.find(
                "img"
            )

            if img_elem:

                foto_url = (
                    img_elem.get(
                        "data-src"
                    )
                    or
                    img_elem.get(
                        "src"
                    )
                    or
                    img_elem.get(
                        "data-lazy"
                    )
                    or
                    ""
                )

        # ====================================================
        # VALIDAÇÃO DE PREÇOS
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

        # Só mantém preço antigo se for
        # realmente maior que o atual.
        if (
            valor_antigo <= valor_atual
            or
            valor_antigo <= 0
        ):

            preco_antigo = ""

        print(
            "[PRODUTO] Dados encontrados:"
        )

        print(
            "Título:",
            titulo
        )

        print(
            "Preço atual:",
            preco_atual
        )

        print(
            "Preço antigo:",
            preco_antigo
        )

        print(
            "Imagem:",
            foto_url
        )

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
            "[PRODUTO] Erro de conexão:",
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
                False
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
                    f"Telegram retornou HTTP "
                    f"{resposta.status_code}"
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

    try:

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
                        requests.get(
                            foto,
                            timeout=20,
                            headers={
                                "User-Agent":
                                    "Mozilla/5.0"
                            }
                        ).content
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
                    f"Telegram retornou HTTP "
                    f"{resposta.status_code}"
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
    # EXTRAI DADOS DO LINK
    # ========================================================

    dados = extrair_dados_produto(
        link
    )

    if not dados.get("sucesso"):

        return {

            "sucesso":
                False,

            "mensagem":
                dados.get(
                    "erro",
                    "Não foi possível obter os dados do produto."
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
    # MONTAGEM DO PREÇO
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
            "especial da oferta!</b>\n"
        )

    # ========================================================
    # LEGENDA
    # ========================================================

    legenda = (

        "🔥 <b>OFERTA IMPERDÍVEL DO DIA!</b> 🔥\n\n"

        f"📦 <b>{titulo}</b>\n\n"

        f"{bloco_preco}\n"

        "🚨 <b>CORRE QUE PODE ACABAR "
        "A QUALQUER MOMENTO!</b>\n\n"

        "🛒 <b>QUERO APROVEITAR ESSA OFERTA</b>\n"

        "👇 Clique no botão abaixo para comprar:\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"

        "🦊 <b>Raposa Caçadora</b>\n"

        "📌 Ofertas selecionadas todos os dias\n"

        "━━━━━━━━━━━━━━━━━━━━"
    )

    # ========================================================
    # BOTÃO REAL DO TELEGRAM
    # ========================================================

    reply_markup = {

        "inline_keyboard": [

            [

                {

                    "text":
                        "🛒 CLIQUE AQUI PARA COMPRAR",

                    "url":
                        link
                }

            ]

        ]

    }

    # ========================================================
    # ENVIA FOTO + LEGENDA
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

    else:

        resultado = telegram_enviar_mensagem(

            texto=legenda,

            canal=canal,

            reply_markup=reply_markup
        )

    # ========================================================
    # RESULTADO
    # ========================================================

    if not resultado.get("ok"):

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
