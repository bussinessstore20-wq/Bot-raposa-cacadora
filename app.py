import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re
import html

from urllib.parse import parse_qsl, unquote

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
    canal,
    botao_url=None
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

        dados = {
            "chat_id": canal,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        if botao_url:

            dados["reply_markup"] = json.dumps({
                "inline_keyboard": [
                    [
                        {
                            "text": "🛒 CLIQUE AQUI PARA COMPRAR",
                            "url": botao_url
                        }
                    ]
                ]
            })

        resposta = requests.post(
            telegram_api_url("sendMessage"),
            json=dados,
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
# LIMPEZA DE TEXTO
# ============================================================

def limpar_texto(texto):

    if not texto:
        return ""

    texto = html.unescape(
        texto
    )

    texto = re.sub(
        r"<[^>]+>",
        " ",
        texto
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


# ============================================================
# EXTRAIR META TAG
# ============================================================

def extrair_meta(
    pagina,
    propriedade
):

    padroes = [

        rf'<meta[^>]+property=["\']{re.escape(propriedade)}["\'][^>]+content=["\']([^"\']*)["\']',

        rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']{re.escape(propriedade)}["\']',

        rf'<meta[^>]+name=["\']{re.escape(propriedade)}["\'][^>]+content=["\']([^"\']*)["\']',

        rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']{re.escape(propriedade)}["\']'
    ]

    for padrao in padroes:

        resultado = re.search(
            padrao,
            pagina,
            re.IGNORECASE
        )

        if resultado:

            return limpar_texto(
                resultado.group(1)
            )

    return ""


# ============================================================
# EXTRAIR PREÇO
# ============================================================

def extrair_preco(
    pagina
):

    candidatos = []

    propriedades = [
        "product:price:amount",
        "og:price:amount",
        "price",
        "product_price",
        "current_price"
    ]

    for propriedade in propriedades:

        valor = extrair_meta(
            pagina,
            propriedade
        )

        if valor:
            candidatos.append(
                valor
            )

    padroes = [

        r'"price"\s*:\s*"([^"]+)"',

        r'"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',

        r'"current_price"\s*:\s*"([^"]+)"',

        r'"current_price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',

        r'"priceMin"\s*:\s*"([^"]+)"',

        r'"priceMin"\s*:\s*([0-9]+(?:\.[0-9]+)?)',

        r'R\$\s*([0-9]+[.,][0-9]{2})'
    ]

    for padrao in padroes:

        encontrados = re.findall(
            padrao,
            pagina,
            re.IGNORECASE
        )

        candidatos.extend(
            encontrados
        )

    for valor in candidatos:

        if valor is None:
            continue

        valor = str(valor).strip()

        if not valor:
            continue

        valor = valor.replace(
            ",",
            "."
        )

        try:

            numero = float(
                valor
            )

            if numero <= 0:
                continue

            return (
                f"R$ {numero:,.2f}"
                .replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )

        except Exception:
            pass

    return ""


# ============================================================
# EXTRAIR PRODUTO DA SHOPEE
# ============================================================

def obter_dados_produto(
    link
):

    print(
        "[SHOPEE] Buscando informações do produto..."
    )

    headers = {

        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Linux; Android 15) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 "
                "Mobile Safari/537.36"
            ),

        "Accept-Language":
            "pt-BR,pt;q=0.9,en;q=0.8",

        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
    }

    try:

        resposta = requests.get(
            link,
            headers=headers,
            timeout=30,
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

        pagina = resposta.text

        titulo = ""

        # ----------------------------------------------------
        # TÍTULO
        # ----------------------------------------------------

        titulo = extrair_meta(
            pagina,
            "og:title"
        )

        if not titulo:

            titulo = extrair_meta(
                pagina,
                "twitter:title"
            )

        if not titulo:

            resultado = re.search(
                r"<title[^>]*>(.*?)</title>",
                pagina,
                re.IGNORECASE |
                re.DOTALL
            )

            if resultado:

                titulo = limpar_texto(
                    resultado.group(1)
                )

        # ----------------------------------------------------
        # DESCRIÇÃO
        # ----------------------------------------------------

        descricao = extrair_meta(
            pagina,
            "og:description"
        )

        if not descricao:

            descricao = extrair_meta(
                pagina,
                "description"
            )

        # ----------------------------------------------------
        # PREÇO
        # ----------------------------------------------------

        preco = extrair_preco(
            pagina
        )

        # ----------------------------------------------------
        # LIMPA TÍTULO
        # ----------------------------------------------------

        titulo = limpar_texto(
            titulo
        )

        descricao = limpar_texto(
            descricao
        )

        # Remove sufixos comuns da Shopee
        titulo = re.sub(
            r"\s*\|\s*Shopee.*$",
            "",
            titulo,
            flags=re.IGNORECASE
        )

        titulo = re.sub(
            r"\s*-\s*Shopee.*$",
            "",
            titulo,
            flags=re.IGNORECASE
        )

        titulo = titulo.strip()

        # ----------------------------------------------------
        # LIMITA TAMANHO
        # ----------------------------------------------------

        if len(titulo) > 180:

            titulo = (
                titulo[:177].rstrip()
                + "..."
            )

        if len(descricao) > 220:

            descricao = (
                descricao[:217].rstrip()
                + "..."
            )

        print(
            "[SHOPEE] Nome:",
            titulo or "(não encontrado)"
        )

        print(
            "[SHOPEE] Preço:",
            preco or "(não encontrado)"
        )

        print(
            "[SHOPEE] Descrição:",
            descricao or "(não encontrada)"
        )

        return {

            "nome":
                titulo,

            "preco":
                preco,

            "descricao":
                descricao,

            "url_final":
                resposta.url

        }

    except Exception as erro:

        print(
            "[SHOPEE] Erro ao obter produto:",
            erro
        )

        return {

            "nome": "",

            "preco": "",

            "descricao": "",

            "url_final":
                link
        }


# ============================================================
# GERAR BENEFÍCIOS
# ============================================================

def gerar_beneficios(
    nome,
    descricao
):

    texto = (
        f"{nome} {descricao}"
    ).lower()

    beneficios = []

    # --------------------------------------------------------
    # REGRAS DE BENEFÍCIOS
    # --------------------------------------------------------

    regras = [

        (
            [
                "pote",
                "organizador",
                "organização",
                "mantimento"
            ],
            "Ideal para organizar e armazenar seus produtos"
        ),

        (
            [
                "cozinha",
                "cozinha"
            ],
            "Perfeito para deixar sua cozinha mais organizada"
        ),

        (
            [
                "plástico",
                "plastico"
            ],
            "Prático e fácil de usar no dia a dia"
        ),

        (
            [
                "tampa",
                "trava"
            ],
            "Praticidade e segurança para armazenar seus produtos"
        ),

        (
            [
                "geladeira",
                "freezer"
            ],
            "Ótimo para organizar alimentos na geladeira ou freezer"
        ),

        (
            [
                "kit",
                "conjunto"
            ],
            "Excelente opção para quem busca praticidade e economia"
        ),

        (
            [
                "casa",
                "lar"
            ],
            "Uma solução prática para facilitar sua rotina"
        )
    ]

    for palavras, beneficio in regras:

        if any(
            palavra in texto
            for palavra in palavras
        ):

            if beneficio not in beneficios:

                beneficios.append(
                    beneficio
                )

    # --------------------------------------------------------
    # BENEFÍCIOS GENÉRICOS
    # --------------------------------------------------------

    if not beneficios:

        beneficios = [
            "Produto prático para facilitar seu dia a dia",
            "Excelente opção para sua rotina",
            "Ótimo custo-benefício",
            "Uma escolha prática para o dia a dia"
        ]

    return beneficios[:4]


# ============================================================
# GERAR MENSAGEM DA OFERTA
# ============================================================

def gerar_mensagem_oferta(
    produto,
    link
):

    nome = (
        produto.get("nome")
        or
        "Oferta especial encontrada"
    )

    preco = (
        produto.get("preco")
        or
        ""
    )

    descricao = (
        produto.get("descricao")
        or
        ""
    )

    beneficios = gerar_beneficios(
        nome,
        descricao
    )

    # --------------------------------------------------------
    # ESCAPA HTML PARA TELEGRAM
    # --------------------------------------------------------

    def esc(texto):

        return html.escape(
            str(texto)
        )

    nome_html = esc(
        nome
    )

    preco_html = esc(
        preco
    )

    descricao_limpa = (
        descricao
        if descricao
        and descricao.lower() != nome.lower()
        else ""
    )

    # --------------------------------------------------------
    # DESCRIÇÃO
    # --------------------------------------------------------

    if descricao_limpa:

        descricao_limpa = re.sub(
            r"\s+",
            " ",
            descricao_limpa
        ).strip()

        if len(descricao_limpa) > 220:

            descricao_limpa = (
                descricao_limpa[:217].rstrip()
                + "..."
            )

    # --------------------------------------------------------
    # MONTA TEXTO
    # --------------------------------------------------------

    partes = []

    partes.append(
        "🔥 <b>OFERTA IMPERDÍVEL DO DIA!</b> 🔥"
    )

    partes.append(
        ""
    )

    partes.append(
        f"📦 <b>{nome_html}</b>"
    )

    if descricao_limpa:

        partes.append(
            f"✨ {esc(descricao_limpa)}"
        )

    else:

        partes.append(
            "✨ Uma oportunidade especial para aproveitar agora."
        )

    partes.append(
        ""
    )

    if preco_html:

        partes.append(
            f"💰 <b>POR APENAS: {preco_html}!</b>"
        )

    else:

        partes.append(
            "💰 <b>Confira o preço especial da oferta!</b>"
        )

    partes.append(
        ""
    )

    # --------------------------------------------------------
    # BENEFÍCIOS
    # --------------------------------------------------------

    for beneficio in beneficios:

        partes.append(
            f"✅ {esc(beneficio)}"
        )

    partes.append(
        ""
    )

    partes.append(
        "🚨 <b>CORRE QUE PODE ACABAR A QUALQUER MOMENTO!</b>"
    )

    partes.append(
        ""
    )

    partes.append(
        "🛒 <b>QUERO APROVEITAR ESSA OFERTA</b>"
    )

    partes.append(
        "👇 Clique no botão abaixo para comprar:"
    )

    partes.append(
        ""
    )

    partes.append(
        "━━━━━━━━━━━━━━━━━━━━"
    )

    partes.append(
        "🦊 <b>Raposa Caçadora</b>"
    )

    partes.append(
        "📌 Ofertas selecionadas todos os dias"
    )

    partes.append(
        "━━━━━━━━━━━━━━━━━━━━"
    )

    return "\n".join(
        partes
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
    # OBTÉM DADOS DO PRODUTO
    # --------------------------------------------------------

    produto = obter_dados_produto(
        link
    )

    url_compra = (
        produto.get("url_final")
        or
        link
    )

    # --------------------------------------------------------
    # GERA MENSAGEM
    # --------------------------------------------------------

    texto = gerar_mensagem_oferta(
        produto,
        url_compra
    )

    print(
        "[TELEGRAM] Mensagem gerada:"
    )

    print(
        texto
    )

    # --------------------------------------------------------
    # ENVIA
    # --------------------------------------------------------

    resultado = telegram_enviar_mensagem(
        texto,
        canal,
        url_compra
    )

    if not resultado.get("ok"):

        erro = (
            resultado.get("description")
            or
            resultado.get("erro")
            or
            "Erro desconhecido do Telegram."
        )

        print(
            "[TELEGRAM] ERRO:",
            erro
        )

        return {
            "sucesso": False,
            "mensagem": erro
        }

    mensagem_telegram = resultado.get(
        "result",
        {}
    )

    print(
        "[TELEGRAM] Mensagem publicada:",
        mensagem_telegram.get(
            "message_id"
        )
    )

    return {

        "sucesso":
            True,

        "mensagem":
            "Produto publicado no canal.",

        "message_id":
            mensagem_telegram.get(
                "message_id"
            ),

        "produto":
            produto,

        "url_compra":
            url_compra
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

                    "dados_produto":
                        resultado.get(
                            "produto",
                            {}
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

            time.sleep(1)

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

            time.sleep(1)

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
