import os
import re
import hmac
import hashlib
import logging
import threading
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode

import requests
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS


# ============================================================
# APP
# ============================================================

app = Flask(__name__)


# ============================================================
# LOGS
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("raposa")


# ============================================================
# CORS
# ============================================================

FRONTEND_URL = os.getenv(
    "WEBAPP_URL",
    "https://bot-raposa-cacadora.vercel.app"
).strip().rstrip("/")


CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                FRONTEND_URL
            ]
        }
    },
    allow_headers=[
        "Content-Type",
        "X-Telegram-Init-Data"
    ],
    methods=[
        "GET",
        "POST",
        "OPTIONS"
    ],
    supports_credentials=False
)


# ============================================================
# VARIÁVEIS DE AMBIENTE
# ============================================================

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    ""
).strip()

CHAT_ID = os.getenv(
    "CHAT_ID",
    "@raposacacadora"
).strip()


ML_CLIENT_ID = os.getenv(
    "ML_CLIENT_ID",
    ""
).strip()

ML_CLIENT_SECRET = os.getenv(
    "ML_CLIENT_SECRET",
    ""
).strip()

# Estes valores podem ser inicialmente vazios.
# Depois do OAuth, ficam em memória.
INITIAL_ACCESS_TOKEN = os.getenv(
    "ML_ACCESS_TOKEN",
    ""
).strip()

INITIAL_REFRESH_TOKEN = os.getenv(
    "ML_REFRESH_TOKEN",
    ""
).strip()

INITIAL_EXPIRES_AT = os.getenv(
    "ML_TOKEN_EXPIRES_AT",
    "0"
).strip()

INITIAL_USER_ID = os.getenv(
    "ML_USER_ID",
    ""
).strip()


# ============================================================
# MERCADO LIVRE
# ============================================================

ML_AUTH_URL = (
    "https://auth.mercadolivre.com.br/authorization"
)

ML_TOKEN_URL = (
    "https://api.mercadolibre.com/oauth/token"
)

ML_API_URL = (
    "https://api.mercadolibre.com"
)

ML_REDIRECT_URI = (
    "https://bot-raposa-cacadora.onrender.com/oauth/callback"
)


# ============================================================
# CONFIGURAÇÕES
# ============================================================

HTTP_TIMEOUT = 30

PRODUCT_HISTORY_FILE = (
    "produtos_postados.txt"
)


# ============================================================
# TOKEN EM MEMÓRIA
# ============================================================

token_lock = threading.Lock()

try:
    initial_expires_at = float(
        INITIAL_EXPIRES_AT or 0
    )
except Exception:
    initial_expires_at = 0


runtime_token = {
    "access_token": INITIAL_ACCESS_TOKEN,
    "refresh_token": INITIAL_REFRESH_TOKEN,
    "expires_at": initial_expires_at,
    "user_id": INITIAL_USER_ID,
}


# ============================================================
# ESTADO OAUTH
# ============================================================

oauth_state_lock = threading.Lock()

oauth_states = set()


# ============================================================
# HISTÓRICO
# ============================================================

def load_history():
    """
    Lê produtos já publicados.
    """

    if not os.path.exists(
        PRODUCT_HISTORY_FILE
    ):
        return set()

    try:
        with open(
            PRODUCT_HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return {
                line.strip()
                for line in file
                if line.strip()
            }

    except Exception:

        logger.exception(
            "Erro lendo %s",
            PRODUCT_HISTORY_FILE
        )

        return set()


def save_history(product_id):
    """
    Salva o ID do produto depois de
    publicação bem-sucedida.
    """

    try:

        with open(
            PRODUCT_HISTORY_FILE,
            "a",
            encoding="utf-8"
        ) as file:

            file.write(
                f"{product_id}\n"
            )

    except Exception:

        logger.exception(
            "Erro salvando histórico do produto %s",
            product_id
        )


# ============================================================
# TELEGRAM INIT DATA
# ============================================================

def validate_telegram_init_data(
    init_data
):
    """
    Valida o initData recebido do Telegram Mini App.

    O frontend deve enviar:

    X-Telegram-Init-Data: <Telegram.WebApp.initData>
    """

    if not init_data:

        logger.warning(
            "Telegram initData não recebido."
        )

        return False

    if not TELEGRAM_TOKEN:

        logger.error(
            "TELEGRAM_TOKEN não configurado."
        )

        return False

    try:

        # parse_qsl decodifica corretamente
        # os valores URL encoded.
        parsed = parse_qsl(
            init_data,
            keep_blank_values=True
        )

        data = dict(parsed)

        received_hash = data.pop(
            "hash",
            None
        )

        if not received_hash:

            logger.warning(
                "Hash do Telegram não encontrado."
            )

            return False

        data_check_string = "\n".join(
            f"{key}={data[key]}"
            for key in sorted(data.keys())
        )

        # Telegram WebApp validation.
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=TELEGRAM_TOKEN.encode(
                "utf-8"
            ),
            digestmod=hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(
                "utf-8"
            ),
            digestmod=hashlib.sha256
        ).hexdigest()

        valid = hmac.compare_digest(
            calculated_hash,
            received_hash
        )

        if valid:

            logger.info(
                "✅ Telegram initData válido."
            )

        else:

            logger.warning(
                "❌ Telegram initData inválido."
            )

        return valid

    except Exception:

        logger.exception(
            "Erro validando Telegram initData."
        )

        return False


# ============================================================
# OAUTH MERCADO LIVRE
# ============================================================

def mercado_livre_configurado():
    return bool(
        ML_CLIENT_ID
        and
        ML_CLIENT_SECRET
    )


def create_oauth_state():
    """
    Cria um state simples para proteger
    o fluxo OAuth contra respostas não
    iniciadas pelo nosso backend.
    """

    import secrets

    state = secrets.token_urlsafe(
        32
    )

    with oauth_state_lock:
        oauth_states.add(state)

    return state


def consume_oauth_state(state):
    if not state:
        return False

    with oauth_state_lock:

        if state not in oauth_states:
            return False

        oauth_states.remove(state)

    return True


def oauth_authorization_url():
    state = create_oauth_state()

    params = {
        "response_type": "code",
        "client_id": ML_CLIENT_ID,
        "redirect_uri": ML_REDIRECT_URI,
        "state": state,
    }

    return (
        f"{ML_AUTH_URL}?"
        f"{urlencode(params)}"
    )


@app.route(
    "/oauth/mercadolivre",
    methods=["GET"]
)
def oauth_mercadolivre():

    if not mercado_livre_configurado():

        return (
            "ML_CLIENT_ID ou "
            "ML_CLIENT_SECRET não configurado.",
            500
        )

    return redirect(
        oauth_authorization_url()
    )


# ============================================================
# TROCAR CODE POR TOKEN
# ============================================================

def exchange_authorization_code(
    code
):
    """
    Authorization Code -> Access Token.

    Fluxo oficial do Mercado Livre.
    """

    payload = {
        "grant_type": "authorization_code",
        "client_id": ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
        "code": code,
        "redirect_uri": ML_REDIRECT_URI,
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": (
            "application/x-www-form-urlencoded"
        ),
    }

    logger.info(
        "🔐 Trocando authorization code "
        "por access token..."
    )

    response = requests.post(
        ML_TOKEN_URL,
        data=payload,
        headers=headers,
        timeout=HTTP_TIMEOUT
    )

    if response.status_code != 200:

        logger.error(
            "❌ OAuth Mercado Livre HTTP %s",
            response.status_code
        )

        logger.error(
            "Resposta: %s",
            response.text[:1000]
        )

        raise RuntimeError(
            "Falha ao obter access token "
            f"(HTTP {response.status_code})"
        )

    return response.json()


# ============================================================
# SALVAR TOKEN EM MEMÓRIA
# ============================================================

def save_runtime_token(
    token_data
):
    global runtime_token

    access_token = token_data.get(
        "access_token"
    )

    refresh_token = token_data.get(
        "refresh_token"
    )

    expires_in = int(
        token_data.get(
            "expires_in",
            0
        )
    )

    user_id = token_data.get(
        "user_id"
    )

    with token_lock:

        runtime_token[
            "access_token"
        ] = access_token or ""

        # IMPORTANTE:
        # Mercado Livre devolve um novo
        # refresh_token ao renovar.
        runtime_token[
            "refresh_token"
        ] = refresh_token or ""

        runtime_token[
            "expires_at"
        ] = (
            time.time()
            +
            max(
                0,
                expires_in - 120
            )
        )

        if user_id:

            runtime_token[
                "user_id"
            ] = str(user_id)

    logger.info(
        "✅ Token Mercado Livre atualizado."
    )

    logger.info(
        "👤 User ID: %s",
        runtime_token.get(
            "user_id"
        )
    )

    logger.info(
        "⏱️ Expiração: %s segundos",
        expires_in
    )


# ============================================================
# CALLBACK OAUTH
# ============================================================

@app.route(
    "/oauth/callback",
    methods=["GET"]
)
def oauth_callback():

    error = request.args.get(
        "error"
    )

    error_description = request.args.get(
        "error_description",
        ""
    )

    code = request.args.get(
        "code"
    )

    state = request.args.get(
        "state"
    )

    if error:

        logger.error(
            "❌ OAuth recusado: %s",
            error
        )

        logger.error(
            "Descrição: %s",
            error_description
        )

        return (
            f"""
            <!doctype html>
            <html lang="pt-BR">
            <head>
                <meta charset="utf-8">
                <title>Raposa Caçadora</title>
            </head>
            <body>
                <h2>❌ Autorização não concluída</h2>
                <p>{error}</p>
                <p>{error_description}</p>
            </body>
            </html>
            """,
            400
        )

    if not consume_oauth_state(
        state
    ):

        logger.warning(
            "❌ OAuth state inválido."
        )

        return (
            """
            <h2>❌ Solicitação OAuth inválida.</h2>
            <p>O state não é válido ou já foi utilizado.</p>
            """,
            400
        )

    if not code:

        return (
            """
            <h2>❌ Authorization code não recebido.</h2>
            """,
            400
        )

    try:

        token_data = (
            exchange_authorization_code(
                code
            )
        )

        save_runtime_token(
            token_data
        )

        user_id = runtime_token.get(
            "user_id"
        )

        logger.info(
            "🎉 Mercado Livre conectado."
        )

        return (
            f"""
            <!doctype html>
            <html lang="pt-BR">
            <head>
                <meta charset="utf-8">
                <title>Raposa Caçadora</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        text-align: center;
                        padding: 40px;
                    }}

                    .ok {{
                        color: #16803c;
                        font-size: 22px;
                    }}
                </style>
            </head>
            <body>

                <h2 class="ok">
                    ✅ Mercado Livre conectado!
                </h2>

                <p>
                    Usuário autorizado:
                    <strong>{user_id}</strong>
                </p>

                <p>
                    Você pode fechar esta janela.
                </p>

            </body>
            </html>
            """
        )

    except Exception as exc:

        logger.exception(
            "❌ Erro no callback OAuth."
        )

        return (
            f"""
            <h2>❌ Erro ao conectar Mercado Livre</h2>
            <p>{str(exc)}</p>
            """,
            500
        )


# ============================================================
# REFRESH TOKEN
# ============================================================

def refresh_access_token():

    with token_lock:

        refresh_token = runtime_token.get(
            "refresh_token"
        )

    if not refresh_token:

        raise RuntimeError(
            "Nenhum refresh token disponível."
        )

    payload = {
        "grant_type": "refresh_token",
        "client_id": ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": (
            "application/x-www-form-urlencoded"
        ),
    }

    logger.info(
        "🔄 Renovando access token Mercado Livre..."
    )

    response = requests.post(
        ML_TOKEN_URL,
        data=payload,
        headers=headers,
        timeout=HTTP_TIMEOUT
    )

    if response.status_code != 200:

        logger.error(
            "❌ Falha no refresh HTTP %s",
            response.status_code
        )

        logger.error(
            "Resposta: %s",
            response.text[:1000]
        )

        raise RuntimeError(
            "Não foi possível renovar "
            "o token Mercado Livre."
        )

    token_data = response.json()

    # IMPORTANTE:
    # O Mercado Livre devolve um NOVO
    # refresh_token. O anterior deixa
    # de ser válido.
    save_runtime_token(
        token_data
    )

    return runtime_token[
        "access_token"
    ]


def get_valid_access_token():

    with token_lock:

        access_token = runtime_token.get(
            "access_token"
        )

        expires_at = runtime_token.get(
            "expires_at",
            0
        )

        refresh_token = runtime_token.get(
            "refresh_token"
        )

    if (
        access_token
        and
        time.time() < expires_at
    ):

        return access_token

    if not refresh_token:

        raise RuntimeError(
            "Mercado Livre não autorizado. "
            "Abra /oauth/mercadolivre."
        )

    return refresh_access_token()


# ============================================================
# API MERCADO LIVRE
# ============================================================

def ml_request(
    method,
    path,
    params=None,
    data=None,
    retry_on_429=True
):
    """
    Faz requisição autenticada à API oficial.
    """

    access_token = (
        get_valid_access_token()
    )

    url = (
        ML_API_URL.rstrip("/")
        +
        "/"
        +
        path.lstrip("/")
    )

    headers = {
        "Authorization": (
            f"Bearer {access_token}"
        ),
        "Accept": "application/json",
    }

    response = requests.request(
        method,
        url,
        headers=headers,
        params=params,
        json=data,
        timeout=HTTP_TIMEOUT
    )

    # Token expirado/rejeitado.
    if response.status_code == 401:

        logger.warning(
            "⚠️ Mercado Livre retornou 401."
        )

        new_token = (
            refresh_access_token()
        )

        headers[
            "Authorization"
        ] = (
            f"Bearer {new_token}"
        )

        response = requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=data,
            timeout=HTTP_TIMEOUT
        )

    # Rate limit.
    if (
        response.status_code == 429
        and
        retry_on_429
    ):

        retry_after = (
            response.headers.get(
                "Retry-After"
            )
        )

        try:
            wait_seconds = float(
                retry_after
            )
        except (
            TypeError,
            ValueError
        ):
            wait_seconds = 3

        wait_seconds = min(
            max(
                wait_seconds,
                1
            ),
            30
        )

        logger.warning(
            "⚠️ Mercado Livre 429. "
            "Esperando %.1f segundos.",
            wait_seconds
        )

        time.sleep(
            wait_seconds
        )

        return ml_request(
            method,
            path,
            params=params,
            data=data,
            retry_on_429=False
        )

    if response.status_code >= 400:

        logger.error(
            "❌ Mercado Livre HTTP %s",
            response.status_code
        )

        logger.error(
            "%s",
            response.text[:1500]
        )

    return response


# ============================================================
# TESTE DE USUÁRIO
# ============================================================

def get_ml_user():

    response = ml_request(
        "GET",
        "/users/me"
    )

    if response.status_code != 200:

        raise RuntimeError(
            "Falha ao consultar /users/me: "
            f"HTTP {response.status_code}"
        )

    return response.json()


# ============================================================
# BUSCA DE ITENS
# ============================================================

def get_items_bulk(
    item_ids
):
    """
    Consulta vários anúncios utilizando:

        GET /items/bulk?ids=...

    O Mercado Livre informa que /items/bulk
    deve ser usado para novas integrações.
    """

    unique_ids = list(
        dict.fromkeys(
            item_ids
        )
    )

    if not unique_ids:
        return []

    products = []

    # A documentação atual informa máximo
    # de 20 resultados por chamada.
    for start in range(
        0,
        len(unique_ids),
        20
    ):

        batch = unique_ids[
            start:start + 20
        ]

        response = ml_request(
            "GET",
            "/items/bulk",
            params={
                "ids": ",".join(
                    batch
                )
            }
        )

        if response.status_code != 200:

            logger.error(
                "Erro /items/bulk HTTP %s",
                response.status_code
            )

            continue

        try:

            results = response.json()

        except Exception:

            logger.exception(
                "Resposta inválida de /items/bulk."
            )

            continue

        if not isinstance(
            results,
            list
        ):
            continue

        for result in results:

            status_code = result.get(
                "status_code"
            )

            item_id = result.get(
                "id"
            )

            body = result.get(
                "body"
            )

            if (
                status_code == 200
                and
                body
            ):

                products.append(
                    body
                )

            else:

                logger.warning(
                    "Item %s não retornado. "
                    "status=%s",
                    item_id,
                    status_code
                )

    return products


# ============================================================
# EXTRAÇÃO DE IDs MLB
# ============================================================

MLB_PATTERN = re.compile(
    r"\bMLB\d{6,15}\b",
    re.IGNORECASE
)


def extract_mlb_ids(
    text
):
    if not text:
        return []

    found = MLB_PATTERN.findall(
        text
    )

    result = []

    for item_id in found:

        item_id = item_id.upper()

        if item_id not in result:

            result.append(
                item_id
            )

    return result


# ============================================================
# EXTRAÇÃO DE POSSÍVEIS LINKS
# ============================================================

def extract_possible_links(
    html
):
    """
    Procura links no documento que contenham
    algum MLB ID.

    Isso NÃO assume endpoint privado.
    """

    mapping = {}

    if not html:
        return mapping

    # href="..."
    hrefs = re.findall(
        r'''href=["']([^"']+)["']''',
        html,
        flags=re.IGNORECASE
    )

    for href in hrefs:

        ids = extract_mlb_ids(
            href
        )

        for item_id in ids:

            mapping[
                item_id
            ] = href

    # URLs absolutas.
    urls = re.findall(
        r'''https?://[^"'\\\s<>]+''',
        html,
        flags=re.IGNORECASE
    )

    for url in urls:

        ids = extract_mlb_ids(
            url
        )

        for item_id in ids:

            mapping[
                item_id
            ] = url

    return mapping


# ============================================================
# VITRINE
# ============================================================

def fetch_vitrine(
    vitrine_url
):
    """
    Faz somente uma requisição HTTP normal.

    Não tenta contornar bloqueio anti-bot.
    """

    logger.info(
        "🔎 ACESSANDO VITRINE"
    )

    logger.info(
        "🔗 %s",
        vitrine_url
    )

    response = requests.get(
        vitrine_url,
        timeout=HTTP_TIMEOUT,
        allow_redirects=True,
        headers={
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Accept-Language": (
                "pt-BR,pt;q=0.9"
            ),
        }
    )

    logger.info(
        "📊 HTTP: %s",
        response.status_code
    )

    logger.info(
        "🔗 URL final: %s",
        response.url
    )

    logger.info(
        "📄 HTML: %s bytes",
        len(response.content)
    )

    return response


def extract_products_from_vitrine(
    vitrine_url
):
    """
    Obtém IDs MLB encontrados no documento.

    Se o meli.la devolver 403 para o servidor,
    não fazemos bypass.
    """

    response = fetch_vitrine(
        vitrine_url
    )

    if response.status_code == 403:

        logger.warning(
            "⚠️ MERCADO LIVRE RETORNOU 403."
        )

        logger.warning(
            "⚠️ O acesso automatizado foi bloqueado."
        )

        return []

    if response.status_code != 200:

        logger.warning(
            "⚠️ Vitrine retornou HTTP %s.",
            response.status_code
        )

        return []

    html = response.text

    item_ids = extract_mlb_ids(
        html
    )

    affiliate_links = (
        extract_possible_links(
            html
        )
    )

    logger.info(
        "📦 Cards/IDs detectados: %s",
        len(item_ids)
    )

    products = []

    for item_id in item_ids:

        logger.info(
            "🛒 Produto detectado: %s",
            item_id
        )

        products.append({
            "item_id": item_id,
            "affiliate_url": (
                affiliate_links.get(
                    item_id
                )
            )
        })

    return products


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalize_item(
    item,
    affiliate_url=None
):
    if not item:
        return None

    pictures = item.get(
        "pictures",
        []
    )

    image_url = None

    if pictures:

        first_picture = pictures[0]

        image_url = (
            first_picture.get(
                "secure_url"
            )
            or
            first_picture.get(
                "url"
            )
        )

    return {
        "id": item.get(
            "id"
        ),

        "title": item.get(
            "title",
            "Produto Mercado Livre"
        ),

        "image_url": image_url,

        "price": item.get(
            "price"
        ),

        "original_price": item.get(
            "original_price"
        ),

        "currency": item.get(
            "currency_id",
            "BRL"
        ),

        "permalink": item.get(
            "permalink"
        ),

        "affiliate_url": (
            affiliate_url
            or
            item.get(
                "permalink"
            )
        ),
    }


# ============================================================
# CUPOM
# ============================================================

def get_coupon_for_item(
    item_id
):
    """
    Não inventamos endpoint de cupons.

    Retorna None até termos um recurso
    oficial confirmado para esse dado.
    """

    return None


# ============================================================
# FORMATAÇÃO DE PREÇO
# ============================================================

def format_brl(
    value
):
    if value is None:
        return None

    try:

        number = float(
            value
        )

    except (
        TypeError,
        ValueError
    ):

        return None

    formatted = (
        f"{number:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    return f"R$ {formatted}"


# ============================================================
# TEXTO DA OFERTA
# ============================================================

def format_offer(
    product
):
    title = product.get(
        "title",
        "Produto Mercado Livre"
    )

    current_price = format_brl(
        product.get(
            "price"
        )
    )

    original_price = format_brl(
        product.get(
            "original_price"
        )
    )

    coupon = product.get(
        "coupon"
    )

    lines = [
        "🚨 OFERTA RELÂMPAGO DO DIA 🚨",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📦 {title}",
        "",
    ]

    # Só mostra "De:" quando existir
    # preço anterior.
    if original_price:

        lines.append(
            f"❌ De: {original_price}"
        )

    # Só mostra preço atual se existir.
    if current_price:

        lines.append(
            f"🔥 POR APENAS: {current_price}"
        )

    # Só mostra cupom se existir.
    if coupon:

        lines.extend([
            "",
            f"🎟️ CUPOM EXTRA: {coupon}"
        ])

    lines.extend([
        "",
        "🚚 Frete Rápido & Compra 100% Segura",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "👇 GARANTA O SEU ANTES QUE ACABE:",
        "",
        "📌 Canal Oficial @raposacacadora",
    ])

    return "\n".join(
        lines
    )


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api_url(
    method
):
    return (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/"
        f"{method}"
    )


def send_telegram(
    method,
    payload
):
    if not TELEGRAM_TOKEN:

        logger.error(
            "TELEGRAM_TOKEN não configurado."
        )

        return None

    try:

        response = requests.post(
            telegram_api_url(
                method
            ),
            json=payload,
            timeout=HTTP_TIMEOUT
        )

    except Exception:

        logger.exception(
            "Erro de conexão com Telegram."
        )

        return None

    if response.status_code != 200:

        logger.error(
            "Telegram HTTP %s",
            response.status_code
        )

        logger.error(
            "%s",
            response.text[:1000]
        )

        return None

    try:

        data = response.json()

    except Exception:

        logger.error(
            "Telegram retornou resposta inválida."
        )

        return None

    if not data.get(
        "ok"
    ):

        logger.error(
            "Telegram API erro: %s",
            data
        )

        return None

    return data


def send_offer_to_telegram(
    product
):
    affiliate_url = product.get(
        "affiliate_url"
    )

    if not affiliate_url:

        affiliate_url = product.get(
            "permalink"
        )

    if not affiliate_url:

        logger.error(
            "Produto %s sem URL.",
            product.get("id")
        )

        return False

    text = format_offer(
        product
    )

    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "🛒 COMPRAR AGORA",
                    "url": affiliate_url
                }
            ]
        ]
    }

    image_url = product.get(
        "image_url"
    )

    if image_url:

        result = send_telegram(
            "sendPhoto",
            {
                "chat_id": CHAT_ID,
                "photo": image_url,
                "caption": text,
                "reply_markup": reply_markup,
            }
        )

    else:

        result = send_telegram(
            "sendMessage",
            {
                "chat_id": CHAT_ID,
                "text": text,
                "reply_markup": reply_markup,
                "disable_web_page_preview": False,
            }
        )

    return result is not None


# ============================================================
# PROCESSAMENTO DA VITRINE
# ============================================================

def processar_vitrine(
    vitrine_url,
    quantidade,
    intervalo_segundos
):
    logger.info("")
    logger.info(
        "🦊 RAPOSA CAÇADORA"
    )

    logger.info(
        "🔗 Vitrine: %s",
        vitrine_url
    )

    logger.info(
        "📦 Quantidade: %s",
        quantidade
    )

    logger.info(
        "⏱️ Intervalo: %s segundos",
        intervalo_segundos
    )

    try:

        # ----------------------------------------------------
        # 1. Encontrar IDs na vitrine
        # ----------------------------------------------------

        candidates = (
            extract_products_from_vitrine(
                vitrine_url
            )
        )

        if not candidates:

            logger.warning(
                "❌ NENHUM PRODUTO FOI ENCONTRADO."
            )

            return

        # ----------------------------------------------------
        # 2. Histórico
        # ----------------------------------------------------

        history = load_history()

        new_candidates = [
            candidate
            for candidate in candidates
            if candidate[
                "item_id"
            ] not in history
        ]

        if not new_candidates:

            logger.info(
                "ℹ️ Todos os produtos já foram publicados."
            )

            return

        # ----------------------------------------------------
        # 3. Limitar quantidade
        # ----------------------------------------------------

        selected = new_candidates[
            :quantidade
        ]

        item_ids = [
            candidate[
                "item_id"
            ]
            for candidate in selected
        ]

        affiliate_map = {
            candidate[
                "item_id"
            ]: candidate.get(
                "affiliate_url"
            )
            for candidate in selected
        }

        logger.info(
            "📦 Produtos novos selecionados: %s",
            len(item_ids)
        )

        # ----------------------------------------------------
        # 4. API oficial Mercado Livre
        # ----------------------------------------------------

        ml_items = get_items_bulk(
            item_ids
        )

        if not ml_items:

            logger.warning(
                "❌ Nenhum item retornado pela API."
            )

            return

        logger.info(
            "✅ API retornou %s produto(s).",
            len(ml_items)
        )

        # ----------------------------------------------------
        # 5. Publicar
        # ----------------------------------------------------

        published = 0

        for item in ml_items:

            item_id = item.get(
                "id"
            )

            if not item_id:

                continue

            if item_id in history:

                logger.info(
                    "⏭️ Ignorando duplicado %s",
                    item_id
                )

                continue

            product = normalize_item(
                item,
                affiliate_url=affiliate_map.get(
                    item_id
                )
            )

            if not product:

                continue

            product[
                "coupon"
            ] = get_coupon_for_item(
                item_id
            )

            logger.info(
                "📤 Publicando: %s",
                product[
                    "title"
                ]
            )

            success = (
                send_offer_to_telegram(
                    product
                )
            )

            if success:

                save_history(
                    item_id
                )

                history.add(
                    item_id
                )

                published += 1

                logger.info(
                    "✅ Produto publicado: %s",
                    item_id
                )

            else:

                logger.error(
                    "❌ Falha ao publicar: %s",
                    item_id
                )

            # Intervalo entre publicações.
            if (
                published > 0
                and
                published < len(ml_items)
                and
                intervalo_segundos > 0
            ):

                logger.info(
                    "⏳ Aguardando %s segundos...",
                    intervalo_segundos
                )

                time.sleep(
                    intervalo_segundos
                )

        logger.info(
            "🏁 Processamento finalizado. "
            "Publicados: %s",
            published
        )

    except Exception:

        logger.exception(
            "🔥 ERRO NO PROCESSAMENTO DA VITRINE."
        )


# ============================================================
# API CONFIGURAR - OPTIONS
# ============================================================

@app.route(
    "/api/configurar",
    methods=["OPTIONS"]
)
def configurar_options():

    logger.info(
        "🌐 OPTIONS /api/configurar"
    )

    return "", 204


# ============================================================
# API CONFIGURAR - POST
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    logger.info(
        "📥 POST /api/configurar"
    )

    # --------------------------------------------------------
    # Telegram initData
    # --------------------------------------------------------

    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        ""
    )

    logger.info(
        "🔐 Telegram initData recebido: %s",
        bool(init_data)
    )

    if not validate_telegram_init_data(
        init_data
    ):

        logger.warning(
            "❌ initData inválido."
        )

        return jsonify({
            "ok": False,
            "error": (
                "Telegram initData inválido."
            )
        }), 401

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    )

    if not isinstance(
        data,
        dict
    ):

        data = {}

    logger.info(
        "📦 JSON recebido: %s",
        data
    )

    # --------------------------------------------------------
    # Link
    # --------------------------------------------------------

    vitrine_url = str(
        data.get(
            "link"
        )
        or
        data.get(
            "vitrine"
        )
        or
        data.get(
            "url"
        )
        or
        ""
    ).strip()

    # --------------------------------------------------------
    # Quantidade
    # --------------------------------------------------------

    try:

        quantidade = int(
            data.get(
                "quantidade",
                data.get(
                    "quantity",
                    5
                )
            )
        )

    except Exception:

        quantidade = 5

    # --------------------------------------------------------
    # Intervalo
    # --------------------------------------------------------

    try:

        intervalo_minutos = float(
            data.get(
                "intervalo",
                data.get(
                    "interval",
                    1
                )
            )
        )

    except Exception:

        intervalo_minutos = 1

    # --------------------------------------------------------
    # Validação link
    # --------------------------------------------------------

    if not vitrine_url:

        return jsonify({
            "ok": False,
            "error": (
                "Link da vitrine não informado."
            )
        }), 400

    allowed_hosts = (
        "meli.la/",
        "www.mercadolivre.com.br/",
        "mercadolivre.com.br/",
    )

    valid_link = any(
        vitrine_url.startswith(
            f"https://{host}"
        )
        for host in allowed_hosts
    )

    if not valid_link:

        return jsonify({
            "ok": False,
            "error": (
                "Link do Mercado Livre inválido."
            )
        }), 400

    # --------------------------------------------------------
    # Limites
    # --------------------------------------------------------

    quantidade = max(
        1,
        min(
            quantidade,
            100
        )
    )

    intervalo_segundos = max(
        0,
        int(
            intervalo_minutos * 60
        )
    )

    # --------------------------------------------------------
    # Logs
    # --------------------------------------------------------

    logger.info(
        "========================================"
    )

    logger.info(
        "📥 NOVA CONFIGURAÇÃO"
    )

    logger.info(
        "🔗 Link: %s",
        vitrine_url
    )

    logger.info(
        "📦 Quantidade: %s",
        quantidade
    )

    logger.info(
        "⏱️ Intervalo: %s minuto(s)",
        intervalo_minutos
    )

    logger.info(
        "✅ Telegram initData válido."
    )

    # --------------------------------------------------------
    # THREAD
    # --------------------------------------------------------

    worker = threading.Thread(
        target=processar_vitrine,
        args=(
            vitrine_url,
            quantidade,
            intervalo_segundos,
        ),
        daemon=True
    )

    worker.start()

    logger.info(
        "🚀 Worker iniciado."
    )

    # --------------------------------------------------------
    # RESPOSTA IMEDIATA
    # --------------------------------------------------------

    return jsonify({
        "ok": True,
        "message": (
            "Automação iniciada "
            "em segundo plano."
        ),
        "quantidade": quantidade,
        "intervalo_segundos": (
            intervalo_segundos
        ),
    }), 200


# ============================================================
# HEALTH
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    with token_lock:

        authorized = bool(
            runtime_token.get(
                "access_token"
            )
            or
            runtime_token.get(
                "refresh_token"
            )
        )

    return jsonify({
        "status": "ok",
        "service": (
            "bot-raposa-cacadora"
        ),

        "telegram_configurado": bool(
            TELEGRAM_TOKEN
        ),

        "chat_id": CHAT_ID,

        "cors_frontend": FRONTEND_URL,

        "mercado_livre_configurado": (
            mercado_livre_configurado()
        ),

        "mercado_livre_autorizado": (
            authorized
        ),

        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
    })


# ============================================================
# HOME
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def index():

    return jsonify({
        "service": (
            "Bot Raposa Caçadora"
        ),
        "status": "online",
        "health": "/health",
        "oauth": (
            "/oauth/mercadolivre"
        ),
        "api": (
            "/api/configurar"
        )
    })


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
