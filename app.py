import os
import hmac
import hashlib
import json
import threading
import time
import uuid
import re
import html as html_lib

from urllib.parse import parse_qsl, urljoin

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
# SESSÃO HTTP
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 15) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
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
# TELEGRAM - ENVIAR FOTO
# ============================================================

def telegram_enviar_foto(
    imagem_url,
    legenda,
    canal,
    link_compra
):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {
            "ok": False,
            "description":
                "BOT_TOKEN não está disponível."
        }

    if not canal:

        return {
            "ok": False,
            "description":
                "CHANNEL_USERNAME não configurado."
        }

    if not imagem_url:

        return telegram_enviar_mensagem(
            legenda,
            canal,
            link_compra
        )

    try:

        resposta = requests.post(
            telegram_api_url("sendPhoto"),
            json={
                "chat_id": canal,
                "photo": imagem_url,
                "caption": legenda,
                "parse_mode": "HTML",
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {
                                "text":
                                    "🛒 COMPRAR AGORA",
                                "url":
                                    link_compra
                            }
                        ]
                    ]
                }
            },
            timeout=45
        )

        try:

            return resposta.json()

        except Exception:

            return {
                "ok": False,
                "description":
                    f"Telegram retornou HTTP {resposta.status_code}"
            }

    except requests.RequestException as erro:

        return {
            "ok": False,
            "description":
                f"Erro de conexão com Telegram: {erro}"
        }


# ============================================================
# TELEGRAM - ENVIAR TEXTO
# ============================================================

def telegram_enviar_mensagem(
    texto,
    canal,
    link_compra=None
):

    token = os.environ.get(
        "BOT_TOKEN",
        ""
    ).strip()

    if not token:

        return {
            "ok": False,
            "description":
                "BOT_TOKEN não está disponível."
        }

    if not canal:

        return {
            "ok": False,
            "description":
                "CHANNEL_USERNAME não configurado."
        }

    try:

        payload = {
            "chat_id": canal,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }

        if link_compra:

            payload["reply_markup"] = {
                "inline_keyboard": [
                    [
                        {
                            "text":
                                "🛒 COMPRAR AGORA",
                            "url":
                                link_compra
                        }
                    ]
                ]
            }

        resposta = requests.post(
            telegram_api_url("sendMessage"),
            json=payload,
            timeout=30
        )

        try:

            return resposta.json()

        except Exception:

            return {
                "ok": False,
                "description":
                    f"Telegram retornou HTTP {resposta.status_code}"
            }

    except requests.RequestException as erro:

        return {
            "ok": False,
            "description":
                f"Erro de conexão com Telegram: {erro}"
        }


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
# LIMPAR TEXTO
# ============================================================

def limpar_texto(valor):

    if not valor:
        return ""

    valor = html_lib.unescape(
        str(valor)
    )

    valor = re.sub(
        r"<[^>]+>",
        " ",
        valor
    )

    valor = re.sub(
        r"\s+",
        " ",
        valor
    )

    return valor.strip()


# ============================================================
# PREÇO
# ============================================================

def normalizar_preco(valor):

    if valor is None:
        return ""

    valor = limpar_texto(
        valor
    )

    if not valor:
        return ""

    valor = valor.replace(
        "R$",
        ""
    ).strip()

    # Exemplo:
    # 59.90
    # 59,90
    # 59.900
    # 59 90

    match = re.search(
        r"\d{1,3}(?:[.,]\d{3})*[.,]\d{2}",
        valor
    )

    if match:

        numero = match.group(0)

        # 1.299,90
        if (
            "." in numero
            and "," in numero
        ):

            numero = numero.replace(
                ".",
                ""
            )

            numero = numero.replace(
                ",",
                "."
            )

        elif "," in numero:

            numero = numero.replace(
                ",",
                "."
            )

        return (
            "R$ "
            +
            numero.replace(
                ".",
                ","
            )
        )

    match = re.search(
        r"\d+(?:[.,]\d+)?",
        valor
    )

    if match:

        numero = match.group(0)

        numero = numero.replace(
            ",",
            "."
        )

        try:

            numero_float = float(
                numero
            )

            return (
                "R$ "
                +
                f"{numero_float:.2f}".replace(
                    ".",
                    ","
                )
            )

        except Exception:

            pass

    return ""


# ============================================================
# EXTRAIR JSON EMBUTIDO
# ============================================================

def extrair_jsons(html):

    encontrados = []

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    blocos = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S
    )

    for bloco in blocos:

        bloco = bloco.strip()

        if not bloco:
            continue

        try:

            dados = json.loads(
                html_lib.unescape(
                    bloco
                )
            )

            encontrados.append(
                dados
            )

        except Exception:

            continue

    # --------------------------------------------------------
    # NEXT DATA
    # --------------------------------------------------------

    blocos_next = re.findall(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S
    )

    for bloco in blocos_next:

        try:

            dados = json.loads(
                html_lib.unescape(
                    bloco
                )
            )

            encontrados.append(
                dados
            )

        except Exception:

            continue

    return encontrados


# ============================================================
# BUSCAR VALOR EM OBJETO JSON
# ============================================================

def procurar_chave(
    objeto,
    chaves
):

    if isinstance(
        objeto,
        dict
    ):

        for chave in chaves:

            if chave in objeto:

                valor = objeto[
                    chave
                ]

                if isinstance(
                    valor,
                    (str, int, float)
                ):

                    texto = str(
                        valor
                    ).strip()

                    if texto:

                        return texto

        for valor in objeto.values():

            resultado = procurar_chave(
                valor,
                chaves
            )

            if resultado:

                return resultado

    elif isinstance(
        objeto,
        list
    ):

        for item in objeto:

            resultado = procurar_chave(
                item,
                chaves
            )

            if resultado:

                return resultado

    return ""


# ============================================================
# BUSCAR IMAGEM
# ============================================================

def procurar_imagem(
    objeto
):

    if isinstance(
        objeto,
        dict
    ):

        # Primeiro tenta chaves específicas
        for chave in (
            "image",
            "imageUrl",
            "image_url",
            "thumbnail",
            "thumbnailUrl",
            "cover",
            "coverImage",
            "original",
            "url"
        ):

            valor = objeto.get(
                chave
            )

            if isinstance(
                valor,
                str
            ):

                if (
                    valor.startswith(
                        "http://"
                    )
                    or
                    valor.startswith(
                        "https://"
                    )
                ):

                    if any(
                        ext in valor.lower()
                        for ext in (
                            ".jpg",
                            ".jpeg",
                            ".png",
                            ".webp"
                        )
                    ):

                        return valor

        for valor in objeto.values():

            resultado = procurar_imagem(
                valor
            )

            if resultado:

                return resultado

    elif isinstance(
        objeto,
        list
    ):

        for item in objeto:

            resultado = procurar_imagem(
                item
            )

            if resultado:

                return resultado

    return ""


# ============================================================
# EXTRAIR META TAG
# ============================================================

def extrair_meta(
    html,
    propriedade
):

    padroes = [

        rf'<meta[^>]+property=["\']{re.escape(propriedade)}["\'][^>]+content=["\']([^"\']+)["\']',

        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(propriedade)}["\']',

        rf'<meta[^>]+name=["\']{re.escape(propriedade)}["\'][^>]+content=["\']([^"\']+)["\']',

        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(propriedade)}["\']'

    ]

    for padrao in padroes:

        resultado = re.search(
            padrao,
            html,
            flags=re.I
        )

        if resultado:

            return html_lib.unescape(
                resultado.group(1)
            ).strip()

    return ""


# ============================================================
# EXTRAIR PRODUTO DA SHOPEE
# ============================================================

def extrair_produto_shopee(
    link
):

    print(
        "[SHOPEE] Buscando dados do produto..."
    )

    try:

        resposta = session.get(
            link,
            timeout=30,
            allow_redirects=True
        )

    except Exception as erro:

        print(
            "[SHOPEE] Erro ao acessar:",
            erro
        )

        return {
            "titulo": "",
            "preco": "",
            "preco_antigo": "",
            "imagem": "",
            "link": link
        }

    print(
        "[SHOPEE] HTTP:",
        resposta.status_code
    )

    html = resposta.text

    url_final = resposta.url or link

    # ========================================================
    # TÍTULO
    # ========================================================

    titulo = ""

    for propriedade in (
        "og:title",
        "twitter:title"
    ):

        titulo = extrair_meta(
            html,
            propriedade
        )

        if titulo:
            break

    if not titulo:

        resultado = re.search(
            r"<title[^>]*>(.*?)</title>",
            html,
            flags=re.I | re.S
        )

        if resultado:

            titulo = limpar_texto(
                resultado.group(1)
            )

    # ========================================================
    # IMAGEM
    # ========================================================

    imagem = ""

    for propriedade in (
        "og:image",
        "twitter:image"
    ):

        imagem = extrair_meta(
            html,
            propriedade
        )

        if imagem:
            break

    # ========================================================
    # JSON
    # ========================================================

    jsons = extrair_jsons(
        html
    )

    # ========================================================
    # JSON-LD / DADOS ESTRUTURADOS
    # ========================================================

    for dados in jsons:

        if not titulo:

            titulo = procurar_chave(
                dados,
                (
                    "name",
                    "productName",
                    "title"
                )
            )

        if not imagem:

            imagem = procurar_imagem(
                dados
            )

    # ========================================================
    # PREÇO
    # ========================================================

    preco = ""

    # JSON-LD
    for dados in jsons:

        preco_bruto = procurar_chave(
            dados,
            (
                "lowPrice",
                "price",
                "salePrice",
                "currentPrice",
                "finalPrice"
            )
        )

        if preco_bruto:

            preco_formatado = normalizar_preco(
                preco_bruto
            )

            if preco_formatado:

                preco = preco_formatado
                break

    # ========================================================
    # PREÇO POR META
    # ========================================================

    if not preco:

        for propriedade in (
            "product:price:amount",
            "og:price:amount"
        ):

            valor = extrair_meta(
                html,
                propriedade
            )

            if valor:

                preco = normalizar_preco(
                    valor
                )

                if preco:
                    break

    # ========================================================
    # PREÇO POR TEXTO
    # ========================================================

    if not preco:

        padroes_preco = [

            r'"price"\s*:\s*"?(?:BRL)?\s*([\d.,]+)',

            r'"salePrice"\s*:\s*"?(?:BRL)?\s*([\d.,]+)',

            r'"currentPrice"\s*:\s*"?(?:BRL)?\s*([\d.,]+)',

            r'"finalPrice"\s*:\s*"?(?:BRL)?\s*([\d.,]+)',

            r'R\$\s*([\d.]+,\d{2})'

        ]

        for padrao in padroes_preco:

            resultado = re.search(
                padrao,
                html,
                flags=re.I
            )

            if resultado:

                preco = normalizar_preco(
                    resultado.group(1)
                )

                if preco:
                    break

    # ========================================================
    # PREÇO ANTIGO
    # ========================================================

    preco_antigo = ""

    for dados in jsons:

        valor_antigo = procurar_chave(
            dados,
            (
                "originalPrice",
                "oldPrice",
                "listPrice",
                "priceBeforeDiscount",
                "discountedPrice"
            )
        )

        if valor_antigo:

            possivel = normalizar_preco(
                valor_antigo
            )

            if possivel:

                if possivel != preco:

                    preco_antigo = possivel

                    break

    # ========================================================
    # PREÇO ANTIGO POR META
    # ========================================================

    if not preco_antigo:

        for propriedade in (
            "product:original_price",
            "og:price:original"
        ):

            valor = extrair_meta(
                html,
                propriedade
            )

            if valor:

                possivel = normalizar_preco(
                    valor
                )

                if (
                    possivel
                    and
                    possivel != preco
                ):

                    preco_antigo = possivel
                    break

    # ========================================================
    # LIMPEZA
    # ========================================================

    titulo = limpar_texto(
        titulo
    )

    imagem = limpar_texto(
        imagem
    )

    # Remove título genérico da Shopee
    titulos_genericos = (
        "shopee brasil",
        "shopee",
        "ofertas incríveis",
        "ofertas incriveis"
    )

    if titulo.lower() in titulos_genericos:

        titulo = ""

    # ========================================================
    # LOG
    # ========================================================

    print(
        "[SHOPEE] Título:",
        titulo or "(não encontrado)"
    )

    print(
        "[SHOPEE] Preço:",
        preco or "(não encontrado)"
    )

    print(
        "[SHOPEE] Preço antigo:",
        preco_antigo or "(não encontrado)"
    )

    print(
        "[SHOPEE] Imagem:",
        imagem or "(não encontrada)"
    )

    print(
        "[SHOPEE] Link final:",
        url_final
    )

    return {

        "titulo":
            titulo,

        "preco":
            preco,

        "preco_antigo":
            preco_antigo,

        "imagem":
            imagem,

        "link":
            url_final
    }


# ============================================================
# ESCAPAR HTML
# ============================================================

def escapar_html(
    texto
):

    return html_lib.escape(
        str(texto or "")
    )


# ============================================================
# CRIAR LEGENDA
# ============================================================

def criar_mensagem_oferta(
    produto
):

    titulo = produto.get(
        "titulo",
        ""
    ).strip()

    preco = produto.get(
        "preco",
        ""
    ).strip()

    preco_antigo = produto.get(
        "preco_antigo",
        ""
    ).strip()

    # --------------------------------------------------------
    # TÍTULO FALLBACK
    # --------------------------------------------------------

    if not titulo:

        titulo = "Oferta especial selecionada"

    # --------------------------------------------------------
    # PREÇO
    # --------------------------------------------------------

    if preco:

        if preco_antigo:

            bloco_preco = (
                f"💰 <s>{escapar_html(preco_antigo)}</s> "
                f"<b>POR APENAS {escapar_html(preco)}!</b>"
            )

        else:

            bloco_preco = (
                f"💰 <b>POR APENAS "
                f"{escapar_html(preco)}!</b>"
            )

    else:

        bloco_preco = (
            "💰 <b>Confira o preço especial da oferta!</b>"
        )

    # --------------------------------------------------------
    # MENSAGEM
    # --------------------------------------------------------

    texto = (

        "🔥 <b>OFERTA IMPERDÍVEL DO DIA!</b> 🔥\n\n"

        f"📦 <b>{escapar_html(titulo)}</b>\n\n"

        f"{bloco_preco}\n\n"

        "✨ Uma ótima oportunidade para aproveitar!\n\n"

        "🚨 <b>CORRE QUE PODE ACABAR A QUALQUER MOMENTO!</b>\n\n"

        "🛒 <b>QUERO APROVEITAR ESSA OFERTA</b>\n"

        "👇 Clique no botão abaixo para comprar:\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"

        "🦊 <b>Raposa Caçadora</b>\n"

        "📌 Ofertas selecionadas todos os dias\n"

        "━━━━━━━━━━━━━━━━━━━━"

    )

    return texto


# ============================================================
# PUBLICAR PRODUTO
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

    # ========================================================
    # BUSCA DADOS
    # ========================================================

    produto = extrair_produto_shopee(
        link
    )

    produto["link"] = (
        produto.get("link")
        or
        link
    )

    # ========================================================
    # CRIA MENSAGEM
    # ========================================================

    texto = criar_mensagem_oferta(
        produto
    )

    imagem = produto.get(
        "imagem",
        ""
    )

    link_compra = produto.get(
        "link"
    )

    print(
        "[TELEGRAM] Enviando oferta..."
    )

    # ========================================================
    # COM IMAGEM
    # ========================================================

    if imagem:

        resultado = telegram_enviar_foto(
            imagem_url=imagem,
            legenda=texto,
            canal=canal,
            link_compra=link_compra
        )

    else:

        print(
            "[TELEGRAM] Imagem não encontrada. "
            "Enviando somente texto."
        )

        resultado = telegram_enviar_mensagem(
            texto=texto,
            canal=canal,
            link_compra=link_compra
        )

    # ========================================================
    # ERRO
    # ========================================================

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

    # ========================================================
    # SUCESSO
    # ========================================================

    mensagem_telegram = resultado.get(
        "result",
        {}
    )

    message_id = mensagem_telegram.get(
        "message_id"
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

        "produto":
            produto
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

            print(
                f"[TASK] Finalizada {task_id}"
            )

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
                    / quantidade
                ) * 100
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

                    "dados":
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

        # ====================================================
        # ERRO
        # ====================================================

        if not sucesso:

            time.sleep(2)

            continue

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
# DEBUG TELEGRAM
# ============================================================

@app.route(
    "/debug-telegram",
    methods=["GET"]
)
def debug_telegram():

    resultado = telegram_get_me()

    bot = None

    if resultado.get("ok"):

        bot = resultado.get(
            "result"
        )

    return jsonify({

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
