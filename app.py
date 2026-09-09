import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re
import html

from urllib.parse import parse_qsl, urlparse

import requests

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


def telegram_enviar_mensagem(
    texto,
    canal
):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {
            "ok": False,
            "erro": "BOT_TOKEN não está disponível."
        }

    if not canal:

        return {
            "ok": False,
            "erro": "CHANNEL_USERNAME não configurado."
        }

    try:

        resposta = requests.post(
            telegram_api_url("sendMessage"),
            json={
                "chat_id": canal,
                "text": texto,
                "disable_web_page_preview": False
            },
            timeout=30
        )

        try:

            resultado = resposta.json()

        except Exception:

            return {
                "ok": False,
                "erro":
                    f"Telegram retornou HTTP {resposta.status_code}"
            }

        return resultado

    except requests.RequestException as erro:

        return {
            "ok": False,
            "erro":
                f"Erro de conexão com Telegram: {erro}"
        }


def telegram_enviar_foto(
    foto,
    legenda,
    canal
):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {
            "ok": False,
            "erro": "BOT_TOKEN não está disponível."
        }

    if not canal:

        return {
            "ok": False,
            "erro": "CHANNEL_USERNAME não configurado."
        }

    try:

        resposta = requests.post(
            telegram_api_url("sendPhoto"),
            data={
                "chat_id": canal,
                "caption": legenda
            },
            files={
                "photo": (
                    "produto.jpg",
                    foto,
                    "image/jpeg"
                )
            },
            timeout=60
        )

        try:

            return resposta.json()

        except Exception:

            return {
                "ok": False,
                "erro":
                    f"Telegram retornou HTTP {resposta.status_code}"
            }

    except requests.RequestException as erro:

        return {
            "ok": False,
            "erro":
                f"Erro ao enviar imagem para Telegram: {erro}"
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
            in sorted(dados.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            token.encode("utf-8"),
            hashlib.sha256
        ).digest()

        hash_calculado = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
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
        link_lower.startswith("http://")
        or
        link_lower.startswith("https://")
    ):
        return False

    return (
        "shopee." in link_lower
        or
        "shopee" in link_lower
    )


# ============================================================
# UTILITÁRIOS DE EXTRAÇÃO
# ============================================================

def limpar_texto(valor):

    if not valor:
        return ""

    valor = html.unescape(
        str(valor)
    )

    valor = re.sub(
        r"\s+",
        " ",
        valor
    )

    return valor.strip()


def remover_html(valor):

    if not valor:
        return ""

    valor = re.sub(
        r"<[^>]+>",
        " ",
        valor
    )

    return limpar_texto(
        valor
    )


def extrair_meta(
    conteudo,
    propriedade
):

    padroes = [

        rf'<meta[^>]+property=["\']{re.escape(propriedade)}["\'][^>]+content=["\']([^"\']+)["\']',

        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(propriedade)}["\']',

        rf'<meta[^>]+name=["\']{re.escape(propriedade)}["\'][^>]+content=["\']([^"\']+)["\']',

        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(propriedade)}["\']'
    ]

    for padrao in padroes:

        encontrado = re.search(
            padrao,
            conteudo,
            flags=re.I
        )

        if encontrado:

            return limpar_texto(
                encontrado.group(1)
            )

    return ""


def extrair_json_ld(
    conteudo
):

    resultados = []

    padrao = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.I | re.S
    )

    for bloco in padrao.findall(
        conteudo
    ):

        bloco = bloco.strip()

        try:

            dados = json.loads(
                bloco
            )

            if isinstance(
                dados,
                list
            ):

                resultados.extend(
                    dados
                )

            else:

                resultados.append(
                    dados
                )

        except Exception:

            continue

    return resultados


def procurar_produto_json(
    dados
):

    if isinstance(
        dados,
        dict
    ):

        tipo = dados.get(
            "@type",
            ""
        )

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

            return dados

        if "product" in dados:

            resultado = procurar_produto_json(
                dados["product"]
            )

            if resultado:
                return resultado

        if "@graph" in dados:

            resultado = procurar_produto_json(
                dados["@graph"]
            )

            if resultado:
                return resultado

        for valor in dados.values():

            if isinstance(
                valor,
                (dict, list)
            ):

                resultado = procurar_produto_json(
                    valor
                )

                if resultado:
                    return resultado

    elif isinstance(
        dados,
        list
    ):

        for item in dados:

            resultado = procurar_produto_json(
                item
            )

            if resultado:
                return resultado

    return None


def extrair_preco_texto(
    conteudo
):

    padroes = [

        r'R\$\s*[\d\.\,]+',

        r'BRL\s*[\d\.\,]+',

        r'"price"\s*:\s*"([\d\.\,]+)"',

        r'"price"\s*:\s*([\d\.]+)',

        r'"current_price"\s*:\s*"([\d\.\,]+)"',

        r'"current_price"\s*:\s*([\d\.]+)'
    ]

    for padrao in padroes:

        encontrados = re.findall(
            padrao,
            conteudo,
            flags=re.I
        )

        if encontrados:

            valor = encontrados[0]

            if isinstance(
                valor,
                tuple
            ):

                valor = valor[0]

            valor = limpar_texto(
                valor
            )

            if valor.startswith(
                "R$"
            ):

                return valor

            try:

                numero = float(
                    valor.replace(
                        ",",
                        "."
                    )
                )

                return formatar_preco(
                    numero
                )

            except Exception:

                continue

    return ""


def formatar_preco(
    valor
):

    try:

        if isinstance(
            valor,
            str
        ):

            valor = valor.replace(
                "R$",
                ""
            ).strip()

            valor = valor.replace(
                ".",
                ""
            ).replace(
                ",",
                "."
            )

        numero = float(
            valor
        )

        return (
            "R$ "
            +
            f"{numero:,.2f}"
            .replace(
                ",",
                "X"
            )
            .replace(
                ".",
                ","
            )
            .replace(
                "X",
                "."
            )
        )

    except Exception:

        return ""


def extrair_dados_produto(
    link
):

    resultado = {

        "nome":
            "",

        "preco_atual":
            "",

        "preco_antigo":
            "",

        "imagem":
            "",

        "descricao":
            "",

        "url":
            link
    }

    headers = {

        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8",

        "Accept":
            (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            )
    }

    try:

        resposta = requests.get(
            link,
            headers=headers,
            timeout=25,
            allow_redirects=True
        )

        print(
            "[SHOPEE] HTTP:",
            resposta.status_code
        )

        print(
            "[SHOPEE] URL final:",
            resposta.url
        )

        if resposta.status_code >= 400:

            return resultado

        conteudo = resposta.text

    except Exception as erro:

        print(
            "[SHOPEE] Erro ao acessar produto:",
            erro
        )

        return resultado


    # --------------------------------------------------------
    # OPEN GRAPH
    # --------------------------------------------------------

    nome_og = extrair_meta(
        conteudo,
        "og:title"
    )

    imagem_og = extrair_meta(
        conteudo,
        "og:image"
    )

    descricao_og = extrair_meta(
        conteudo,
        "og:description"
    )


    if nome_og:

        resultado[
            "nome"
        ] = nome_og


    if imagem_og:

        resultado[
            "imagem"
        ] = imagem_og


    if descricao_og:

        resultado[
            "descricao"
        ] = descricao_og


    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    jsons = extrair_json_ld(
        conteudo
    )

    produto = procurar_produto_json(
        jsons
    )


    if produto:

        nome = produto.get(
            "name"
        )

        if nome:

            resultado[
                "nome"
            ] = limpar_texto(
                nome
            )


        imagem = produto.get(
            "image"
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

        if imagem:

            resultado[
                "imagem"
            ] = str(
                imagem
            )


        descricao = produto.get(
            "description"
        )

        if descricao:

            resultado[
                "descricao"
            ] = remover_html(
                descricao
            )


        oferta = produto.get(
            "offers"
        )

        if isinstance(
            oferta,
            list
        ):

            oferta = (
                oferta[0]
                if oferta
                else {}
            )

        if isinstance(
            oferta,
            dict
        ):

            preco = oferta.get(
                "price"
            )

            if preco:

                resultado[
                    "preco_atual"
                ] = formatar_preco(
                    preco
                )

            preco_antigo = (
                oferta.get(
                    "highPrice"
                )
                or
                oferta.get(
                    "priceSpecification",
                    {}
                ).get(
                    "price"
                )
                if isinstance(
                    oferta.get(
                        "priceSpecification"
                    ),
                    dict
                )
                else ""
            )

            if preco_antigo:

                resultado[
                    "preco_antigo"
                ] = formatar_preco(
                    preco_antigo
                )


    # --------------------------------------------------------
    # PREÇO POR TEXTO
    # --------------------------------------------------------

    if not resultado[
        "preco_atual"
    ]:

        resultado[
            "preco_atual"
        ] = extrair_preco_texto(
            conteudo
        )


    # --------------------------------------------------------
    # LIMPEZA DO NOME
    # --------------------------------------------------------

    nome = limpar_texto(
        resultado[
            "nome"
        ]
    )

    nome = re.sub(
        r"\s*\|\s*Shopee.*$",
        "",
        nome,
        flags=re.I
    )

    nome = re.sub(
        r"\s*-\s*Shopee.*$",
        "",
        nome,
        flags=re.I
    )

    resultado[
        "nome"
    ] = nome.strip()


    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    if not resultado[
        "nome"
    ]:

        resultado[
            "nome"
        ] = "Oferta especial Shopee"


    print(
        "[SHOPEE] Produto:",
        resultado["nome"]
    )

    print(
        "[SHOPEE] Preço atual:",
        resultado["preco_atual"]
    )

    print(
        "[SHOPEE] Preço antigo:",
        resultado["preco_antigo"]
    )

    print(
        "[SHOPEE] Imagem:",
        bool(resultado["imagem"])
    )

    return resultado


# ============================================================
# MONTAR MENSAGEM
# ============================================================

def montar_mensagem(
    produto
):

    nome = produto.get(
        "nome"
    ) or "Oferta especial"


    preco_atual = produto.get(
        "preco_atual"
    )


    preco_antigo = produto.get(
        "preco_antigo"
    )


    if preco_atual:

        if preco_antigo:

            preco_texto = (
                f"💰 DE {preco_antigo} "
                f"POR APENAS {preco_atual}!"
            )

        else:

            preco_texto = (
                f"💰 POR APENAS: "
                f"{preco_atual}!"
            )

    else:

        preco_texto = (
            "💰 Confira o preço especial "
            "dessa oferta!"
        )


    descricao = produto.get(
        "descricao"
    ) or ""


    # --------------------------------------------------------
    # DESCRIÇÃO CURTA
    # --------------------------------------------------------

    descricao = limpar_texto(
        descricao
    )

    descricao = re.sub(
        r"\bShopee\b.*",
        "",
        descricao,
        flags=re.I
    )

    descricao = descricao.strip()


    if len(descricao) > 180:

        descricao = (
            descricao[:177]
            + "..."
        )


    # --------------------------------------------------------
    # BENEFÍCIOS
    # --------------------------------------------------------

    beneficios = [
        "Produto prático para facilitar seu dia a dia",
        "Excelente opção para sua rotina",
        "Ótimo custo-benefício",
        "Uma escolha prática para o dia a dia"
    ]


    texto = (
        "🔥 OFERTA IMPERDÍVEL DO DIA! 🔥\n\n"
        f"📦 {nome}\n"
    )


    if descricao:

        texto += (
            f"✨ {descricao}\n"
        )

    else:

        texto += (
            "✨ Aproveite essa oportunidade "
            "antes que o preço mude.\n"
        )


    texto += (
        "\n"
        f"{preco_texto}\n\n"
    )


    for beneficio in beneficios:

        texto += (
            f"✅ {beneficio}\n"
        )


    texto += (
        "\n"
        "🚨 CORRE QUE PODE ACABAR "
        "A QUALQUER MOMENTO!\n\n"
        "🛒 QUERO APROVEITAR ESSA OFERTA\n"
        "👇 Clique abaixo para comprar:\n\n"
        f"👉 {produto['url']}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🦊 Raposa Caçadora\n"
        "📌 Ofertas selecionadas todos os dias\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )


    return texto


# ============================================================
# PUBLICAÇÃO REAL
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
            "sucesso": False,
            "mensagem":
                "CHANNEL_USERNAME não configurado."
        }


    print(
        "----------------------------------------"
    )

    print(
        "[TELEGRAM] Publicando produto"
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


    # --------------------------------------------------------
    # OBTÉM DADOS DA SHOPEE
    # --------------------------------------------------------

    produto = extrair_dados_produto(
        link
    )


    # --------------------------------------------------------
    # MONTA MENSAGEM
    # --------------------------------------------------------

    texto = montar_mensagem(
        produto
    )


    print(
        "[TELEGRAM] Mensagem preparada:"
    )

    print(
        texto
    )


    # --------------------------------------------------------
    # IMAGEM
    # --------------------------------------------------------

    imagem_url = produto.get(
        "imagem"
    )


    if imagem_url:

        try:

            print(
                "[TELEGRAM] Baixando imagem..."
            )


            imagem_resposta = requests.get(
                imagem_url,
                headers={
                    "User-Agent":
                        "Mozilla/5.0"
                },
                timeout=30
            )


            if (
                imagem_resposta.ok
                and
                imagem_resposta.content
            ):

                print(
                    "[TELEGRAM] Enviando imagem..."
                )


                resultado = telegram_enviar_foto(
                    imagem_resposta.content,
                    texto,
                    canal
                )


                if resultado.get(
                    "ok"
                ):

                    mensagem_telegram = (
                        resultado.get(
                            "result",
                            {}
                        )
                    )


                    message_id = (
                        mensagem_telegram.get(
                            "message_id"
                        )
                    )


                    print(
                        "[TELEGRAM] "
                        "Imagem publicada:",
                        message_id
                    )


                    return {

                        "sucesso":
                            True,

                        "mensagem":
                            "Produto publicado no canal.",

                        "message_id":
                            message_id,

                        "imagem":
                            True
                    }


                else:

                    print(
                        "[TELEGRAM] "
                        "Falha ao enviar imagem:",
                        resultado.get(
                            "description"
                        )
                    )


        except Exception as erro:

            print(
                "[TELEGRAM] "
                "Erro ao processar imagem:",
                erro
            )


    # --------------------------------------------------------
    # FALLBACK: SOMENTE TEXTO
    # --------------------------------------------------------

    print(
        "[TELEGRAM] Publicando somente texto."
    )


    resultado = telegram_enviar_mensagem(
        texto,
        canal
    )


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


    mensagem_telegram = (
        resultado.get(
            "result",
            {}
        )
    )


    message_id = (
        mensagem_telegram.get(
            "message_id"
        )
    )


    print(
        "[TELEGRAM] Mensagem publicada:",
        message_id
    )


    return {

        "sucesso":
            True,

        "mensagem":
            "Produto publicado no canal.",

        "message_id":
            message_id,

        "imagem":
            False
    }


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


        # ----------------------------------------------------
        # FINALIZAÇÃO
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # PRODUTO
        # ----------------------------------------------------

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
                    / quantidade
                ) * 100
            )


        # ----------------------------------------------------
        # PUBLICAÇÃO
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # SALVA RESULTADO
        # ----------------------------------------------------

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

                    "imagem":
                        resultado.get(
                            "imagem",
                            False
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
                        / quantidade
                    ) * 100
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
                        / quantidade
                    ) * 100
                )


                tarefa[
                    "status"
                ] = "erro"


        # ----------------------------------------------------
        # ERRO
        # ----------------------------------------------------

        if not sucesso:

            time.sleep(
                1
            )

            continue


        # ----------------------------------------------------
        # ÚLTIMO
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # INTERVALO
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # TOKEN
        # ----------------------------------------------------

        token = os.environ.get(
            "BOT_TOKEN",
            ""
        ).strip()


        if not token:

            return jsonify({
                "erro":
                    "BOT_TOKEN não está disponível para o processo do Render."
            }), 500


        # ----------------------------------------------------
        # CANAL
        # ----------------------------------------------------

        canal = os.environ.get(
            "CHANNEL_USERNAME",
            ""
        ).strip()


        if not canal:

            return jsonify({
                "erro":
                    "CHANNEL_USERNAME não está disponível para o processo do Render."
            }), 500


        # ----------------------------------------------------
        # INIT DATA
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # LINKS
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # VALIDAÇÃO
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # QUANTIDADE
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # INTERVALO
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # LIMITA LINKS
        # ----------------------------------------------------

        links = links[
            :quantidade
        ]


        # ----------------------------------------------------
        # CRIA TAREFA
        # ----------------------------------------------------

        task_id = criar_tarefa(
            links=links,
            intervalo=intervalo,
            quantidade=quantidade,
            usuario=usuario
        )


        # ----------------------------------------------------
        # THREAD
        # ----------------------------------------------------

        thread = threading.Thread(
            target=executar_tarefa,
            args=(task_id,),
            daemon=True
        )


        thread.start()


        # ----------------------------------------------------
        # RESPOSTA
        # ----------------------------------------------------

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
