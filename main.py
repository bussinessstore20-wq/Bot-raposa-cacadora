import os
import re
import json
import time
import hmac
import hashlib
import logging
import threading
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify, redirect

# ============================================================
# CONFIGURAÇÃO
# ============================================================

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("raposa")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "@raposacacadora").strip()
WEBAPP_URL = os.getenv(
    "WEBAPP_URL",
    "https://bot-raposa-cacadora.vercel.app"
).strip()

ML_CLIENT_ID = os.getenv("ML_CLIENT_ID", "").strip()
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET", "").strip()

# Podem ficar vazios antes da primeira autorização.
ML_ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN", "").strip()
ML_REFRESH_TOKEN = os.getenv("ML_REFRESH_TOKEN", "").strip()
ML_TOKEN_EXPIRES_AT = os.getenv("ML_TOKEN_EXPIRES_AT", "0").strip()
ML_USER_ID = os.getenv("ML_USER_ID", "").strip()

TELEGRAM_INIT_DATA_MAX_AGE = 86400

PRODUCT_HISTORY_FILE = "produtos_postados.txt"

ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_API_URL = "https://api.mercadolibre.com"

# IMPORTANTE:
# Este valor precisa ser exatamente o mesmo configurado
# no painel do Mercado Livre.
ML_REDIRECT_URI = (
    "https://bot-raposa-cacadora.onrender.com/oauth/callback"
)

HTTP_TIMEOUT = 30

# ============================================================
# ESTADO EM MEMÓRIA
# ============================================================

token_lock = threading.Lock()

runtime_token = {
    "access_token": ML_ACCESS_TOKEN,
    "refresh_token": ML_REFRESH_TOKEN,
    "expires_at": float(ML_TOKEN_EXPIRES_AT or 0),
    "user_id": ML_USER_ID,
}

# ============================================================
# HISTÓRICO
# ============================================================


def load_history():
    if not os.path.exists(PRODUCT_HISTORY_FILE):
        return set()

    try:
        with open(
            PRODUCT_HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return {
                line.strip()
                for line in f
                if line.strip()
            }
    except Exception:
        logger.exception("Erro lendo histórico.")
        return set()


def save_history(product_id):
    try:
        with open(
            PRODUCT_HISTORY_FILE,
            "a",
            encoding="utf-8"
        ) as f:
            f.write(f"{product_id}\n")
    except Exception:
        logger.exception(
            "Erro salvando produto %s no histórico.",
            product_id
        )


# ============================================================
# TELEGRAM INIT DATA
# ============================================================


def validate_telegram_init_data(init_data):
    """
    Validação oficial do initData do Telegram WebApp.

    O Mini App deve enviar:
        initData
    no header:
        X-Telegram-Init-Data
    """

    if not init_data:
        return False

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN não configurado.")
        return False

    try:
        pairs = init_data.split("&")
        data = {}

        for pair in pairs:
            if "=" not in pair:
                continue

            key, value = pair.split("=", 1)

            if key != "hash":
                data[key] = value

        received_hash = None

        for pair in pairs:
            if pair.startswith("hash="):
                received_hash = pair.split("=", 1)[1]
                break

        if not received_hash:
            return False

        data_check_string = "\n".join(
            f"{key}={data[key]}"
            for key in sorted(data.keys())
        )

        secret_key = hmac.new(
            b"WebAppData",
            TELEGRAM_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash
        ):
            logger.warning(
                "Telegram initData inválido."
            )
            return False

        return True

    except Exception:
        logger.exception(
            "Erro validando Telegram initData."
        )
        return False


# ============================================================
# MERCADO LIVRE - OAUTH
# ============================================================


def mercado_livre_configurado():
    return bool(
        ML_CLIENT_ID and
        ML_CLIENT_SECRET
    )


def oauth_authorization_url():
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": ML_CLIENT_ID,
        "redirect_uri": ML_REDIRECT_URI,
    }

    return f"{ML_AUTH_URL}?{urlencode(params)}"


@app.route("/oauth/mercadolivre", methods=["GET"])
def oauth_mercadolivre():
    if not mercado_livre_configurado():
        return (
            "ML_CLIENT_ID ou ML_CLIENT_SECRET não configurado.",
            500
        )

    return redirect(oauth_authorization_url())


def exchange_authorization_code(code):
    payload = {
        "grant_type": "authorization_code",
        "client_id": ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
        "code": code,
        "redirect_uri": ML_REDIRECT_URI,
    }

    logger.info(
        "Trocando authorization code por token."
    )

    response = requests.post(
        ML_TOKEN_URL,
        data=payload,
        timeout=HTTP_TIMEOUT
    )

    if response.status_code != 200:
        logger.error(
            "Erro OAuth HTTP %s: %s",
            response.status_code,
            response.text[:1000]
        )

        raise RuntimeError(
            f"Mercado Livre OAuth HTTP "
            f"{response.status_code}"
        )

    return response.json()


def save_runtime_token(token_data):
    global runtime_token

    with token_lock:
        runtime_token["access_token"] = (
            token_data.get("access_token", "")
        )

        runtime_token["refresh_token"] = (
            token_data.get("refresh_token", "")
        )

        expires_in = int(
            token_data.get("expires_in", 0)
        )

        # Margem de segurança de 2 minutos.
        runtime_token["expires_at"] = (
            time.time() +
            max(0, expires_in - 120)
        )

        if token_data.get("user_id"):
            runtime_token["user_id"] = str(
                token_data["user_id"]
            )

    logger.info(
        "Token Mercado Livre atualizado. "
        "user_id=%s expires_in=%ss",
        runtime_token["user_id"],
        token_data.get("expires_in")
    )


@app.route("/oauth/callback", methods=["GET"])
def oauth_callback():
    error = request.args.get("error")
    code = request.args.get("code")

    if error:
        description = request.args.get(
            "error_description",
            ""
        )

        logger.error(
            "OAuth Mercado Livre recusado: %s %s",
            error,
            description
        )

        return (
            f"""
            <h2>Autorização não concluída</h2>
            <p>{error}</p>
            <p>{description}</p>
            """,
            400
        )

    if not code:
        return (
            "<h2>Authorization code não recebido.</h2>",
            400
        )

    try:
        token_data = exchange_authorization_code(code)
        save_runtime_token(token_data)

        user_id = runtime_token.get("user_id")

        return f"""
        <html>
        <head>
            <meta charset="utf-8">
            <title>Raposa Caçadora</title>
        </head>
        <body>
            <h2>✅ Mercado Livre conectado!</h2>
            <p>Usuário autorizado: {user_id}</p>
            <p>Você pode fechar esta janela.</p>
        </body>
        </html>
        """

    except Exception as exc:
        logger.exception(
            "Falha no callback OAuth."
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
    global runtime_token

    with token_lock:
        refresh_token = runtime_token.get(
            "refresh_token"
        )

    if not refresh_token:
        raise RuntimeError(
            "Nenhum ML_REFRESH_TOKEN disponível."
        )

    payload = {
        "grant_type": "refresh_token",
        "client_id": ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }

    logger.info(
        "Renovando access token Mercado Livre..."
    )

    response = requests.post(
        ML_TOKEN_URL,
        data=payload,
        timeout=HTTP_TIMEOUT
    )

    if response.status_code != 200:
        logger.error(
            "Falha refresh token HTTP %s: %s",
            response.status_code,
            response.text[:1000]
        )

        raise RuntimeError(
            "Não foi possível renovar o token Mercado Livre."
        )

    token_data = response.json()

    save_runtime_token(token_data)

    return runtime_token["access_token"]


def get_valid_access_token():
    with token_lock:
        access_token = runtime_token.get(
            "access_token"
        )
        expires_at = runtime_token.get(
            "expires_at",
            0
        )

    if access_token and time.time() < expires_at:
        return access_token

    if not runtime_token.get("refresh_token"):
        raise RuntimeError(
            "Mercado Livre ainda não autorizado. "
            "Abra /oauth/mercadolivre."
        )

    return refresh_access_token()


# ============================================================
# REQUEST PARA API MERCADO LIVRE
# ============================================================


def ml_request(
    method,
    path,
    params=None,
    data=None,
    retry_on_429=True
):
    access_token = get_valid_access_token()

    url = (
        f"{ML_API_URL.rstrip('/')}/"
        f"{path.lstrip('/')}"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
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

    if response.status_code == 401:
        logger.warning(
            "Mercado Livre retornou 401. "
            "Tentando renovar token."
        )

        new_token = refresh_access_token()

        headers["Authorization"] = (
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

    if response.status_code == 429 and retry_on_429:
        retry_after = response.headers.get(
            "Retry-After"
        )

        try:
            wait = float(retry_after)
        except (TypeError, ValueError):
            wait = 2

        wait = min(max(wait, 1), 30)

        logger.warning(
            "Mercado Livre 429. "
            "Aguardando %.1fs.",
            wait
        )

        time.sleep(wait)

        return ml_request(
            method,
            path,
            params=params,
            data=data,
            retry_on_429=False
        )

    if response.status_code >= 400:
        logger.error(
            "Mercado Livre HTTP %s: %s",
            response.status_code,
            response.text[:1500]
        )

    return response


# ============================================================
# MERCADO LIVRE - USER
# ============================================================


def get_ml_user():
    response = ml_request(
        "GET",
        "/users/me"
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Falha /users/me: HTTP "
            f"{response.status_code}"
        )

    return response.json()


# ============================================================
# MERCADO LIVRE - ITENS
# ============================================================


def get_items_bulk(item_ids):
    """
    Usa o endpoint atual recomendado:
        /items/bulk?ids=...

    A documentação atual informa que /items?ids=
    está em processo de descontinuação e recomenda
    /items/bulk?ids=.
    """

    item_ids = list(dict.fromkeys(item_ids))

    if not item_ids:
        return []

    all_items = []

    # Mantemos no máximo 20 por chamada.
    for start in range(0, len(item_ids), 20):
        batch = item_ids[start:start + 20]

        params = {
            "ids": ",".join(batch)
        }

        response = ml_request(
            "GET",
            "/items/bulk",
            params=params
        )

        if response.status_code != 200:
            logger.error(
                "Erro /items/bulk: HTTP %s",
                response.status_code
            )
            continue

        try:
            data = response.json()
        except Exception:
            logger.error(
                "Resposta inválida de /items/bulk."
            )
            continue

        if not isinstance(data, list):
            continue

        for result in data:
            status_code = result.get(
                "status_code",
                result.get("code")
            )

            body = result.get("body")

            if status_code == 200 and body:
                all_items.append(body)

            else:
                logger.warning(
                    "Item não retornado: %s "
                    "status=%s",
                    result.get("id"),
                    status_code
                )

    return all_items


def get_item(item_id):
    response = ml_request(
        "GET",
        f"/items/{item_id}"
    )

    if response.status_code != 200:
        return None

    return response.json()


# ============================================================
# EXTRAÇÃO DOS IDs MLB DA VITRINE
# ============================================================


MLB_PATTERN = re.compile(
    r"\bMLB\d{6,15}\b",
    re.IGNORECASE
)


def extract_mlb_ids_from_text(text):
    if not text:
        return []

    found = MLB_PATTERN.findall(text)

    result = []

    for item_id in found:
        item_id = item_id.upper()

        if item_id not in result:
            result.append(item_id)

    return result


def extract_possible_affiliate_links(html):
    """
    Procura links no HTML que possam estar associados
    a anúncios.

    NÃO presume nenhum endpoint privado do Mercado Livre.

    Esta função apenas examina o documento recebido.
    """

    if not html:
        return {}

    mapping = {}

    # href="..."
    hrefs = re.findall(
        r'''href=["']([^"']+)["']''',
        html,
        flags=re.IGNORECASE
    )

    for href in hrefs:
        ids = extract_mlb_ids_from_text(href)

        for item_id in ids:
            mapping[item_id] = href

    # Também procura URLs em JSON/JS.
    urls = re.findall(
        r'''https?://[^"'\\\s<>]+''',
        html,
        flags=re.IGNORECASE
    )

    for url in urls:
        ids = extract_mlb_ids_from_text(url)

        for item_id in ids:
            mapping[item_id] = url

    return mapping


def fetch_vitrine_document(vitrine_url):
    """
    Tentativa de obter o documento da vitrine.

    IMPORTANTE:
    O Render pode receber HTTP 403 do meli.la.
    Não fazemos bypass de proteção anti-bot.
    """

    logger.info(
        "🔎 Acessando vitrine: %s",
        vitrine_url
    )

    response = requests.get(
        vitrine_url,
        timeout=HTTP_TIMEOUT,
        allow_redirects=True,
        headers={
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9",
        }
    )

    logger.info(
        "📊 Vitrine HTTP: %s",
        response.status_code
    )

    logger.info(
        "🔗 URL final: %s",
        response.url
    )

    logger.info(
        "📄 Documento: %s bytes",
        len(response.content)
    )

    return response


def extract_products_from_vitrine(vitrine_url):
    """
    Retorna:

        [
            {
                "item_id": "MLB...",
                "affiliate_url": "...",
            }
        ]

    Neste primeiro estágio, os IDs são extraídos
    do documento da vitrine.

    Se o servidor receber 403, não tenta contornar
    o bloqueio.
    """

    response = fetch_vitrine_document(
        vitrine_url
    )

    if response.status_code == 403:
        logger.error(
            "❌ Vitrine retornou 403. "
            "Não será feito bypass."
        )

        return []

    if response.status_code != 200:
        logger.error(
            "❌ Vitrine retornou HTTP %s.",
            response.status_code
        )

        return []

    try:
        html = response.text
    except Exception:
        logger.exception(
            "Erro lendo HTML da vitrine."
        )
        return []

    item_ids = extract_mlb_ids_from_text(
        html
    )

    affiliate_links = (
        extract_possible_affiliate_links(
            html
        )
    )

    logger.info(
        "📦 IDs MLB encontrados: %s",
        len(item_ids)
    )

    for item_id in item_ids:
        logger.info(
            "🛒 Produto detectado: %s",
            item_id
        )

    products = []

    for item_id in item_ids:
        products.append({
            "item_id": item_id,
            "affiliate_url": affiliate_links.get(
                item_id
            ),
        })

    return products


# ============================================================
# NORMALIZAÇÃO DO PRODUTO
# ============================================================


def normalize_item(item, affiliate_url=None):
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
            first_picture.get("secure_url")
            or first_picture.get("url")
        )

    original_price = item.get(
        "original_price"
    )

    current_price = item.get(
        "price"
    )

    return {
        "id": item.get("id"),
        "title": item.get(
            "title",
            "Produto Mercado Livre"
        ),
        "image_url": image_url,
        "price": current_price,
        "original_price": original_price,
        "currency": item.get(
            "currency_id",
            "BRL"
        ),
        "permalink": item.get(
            "permalink"
        ),
        "affiliate_url": (
            affiliate_url
            or item.get("permalink")
        ),
    }


# ============================================================
# CUPOM
# ============================================================


def get_coupon_for_item(item_id):
    """
    Não inventa endpoint de cupom de afiliado.

    Por enquanto retorna None.

    Cupons específicos do programa de afiliados
    precisam ser obtidos através de um recurso oficial
    de afiliados, caso disponível para a conta/API.
    """

    return None


# ============================================================
# FORMATAÇÃO
# ============================================================


def format_brl(value):
    if value is None:
        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    formatted = (
        f"{value:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    return f"R$ {formatted}"


def format_offer(product):
    title = product.get(
        "title",
        "Produto Mercado Livre"
    )

    current_price = format_brl(
        product.get("price")
    )

    original_price = format_brl(
        product.get("original_price")
    )

    coupon = product.get("coupon")

    lines = [
        "🚨 OFERTA RELÂMPAGO DO DIA 🚨",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📦 {title}",
        "",
    ]

    if original_price:
        lines.append(
            f"❌ De: {original_price}"
        )

    if current_price:
        lines.append(
            f"🔥 POR APENAS: {current_price}"
        )

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

    return "\n".join(lines)


# ============================================================
# TELEGRAM
# ============================================================


def telegram_url(method):
    return (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/{method}"
    )


def send_telegram_request(method, payload):
    response = requests.post(
        telegram_url(method),
        json=payload,
        timeout=HTTP_TIMEOUT
    )

    if response.status_code != 200:
        logger.error(
            "Telegram HTTP %s: %s",
            response.status_code,
            response.text[:1000]
        )

        return None

    try:
        data = response.json()
    except Exception:
        return None

    if not data.get("ok"):
        logger.error(
            "Telegram erro: %s",
            data
        )
        return None

    return data


def send_offer_to_telegram(product):
    affiliate_url = product.get(
        "affiliate_url"
    )

    if not affiliate_url:
        affiliate_url = product.get(
            "permalink"
        )

    text = format_offer(product)

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
        result = send_telegram_request(
            "sendPhoto",
            {
                "chat_id": CHAT_ID,
                "photo": image_url,
                "caption": text,
                "reply_markup": reply_markup,
            }
        )
    else:
        result = send_telegram_request(
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
# PROCESSAMENTO
# ============================================================


def processar_vitrine(
    vitrine_url,
    quantidade,
    intervalo
):
    logger.info("")
    logger.info("🦊 RAPOSA CAÇADORA")
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
        intervalo
    )

    try:
        # 1. Descobrir os anúncios.
        candidates = (
            extract_products_from_vitrine(
                vitrine_url
            )
        )

        if not candidates:
            logger.warning(
                "❌ Nenhum produto encontrado "
                "na vitrine."
            )
            return

        # 2. Histórico.
        history = load_history()

        new_candidates = [
            candidate
            for candidate in candidates
            if candidate["item_id"] not in history
        ]

        if not new_candidates:
            logger.info(
                "ℹ️ Todos os produtos encontrados "
                "já foram publicados."
            )
            return

        # 3. Limita quantidade.
        selected = new_candidates[
            :max(1, int(quantidade))
        ]

        item_ids = [
            item["item_id"]
            for item in selected
        ]

        affiliate_map = {
            item["item_id"]: item.get(
                "affiliate_url"
            )
            for item in selected
        }

        # 4. Busca dados pela API oficial.
        logger.info(
            "🔎 Consultando %s item(s) "
            "na API oficial do Mercado Livre.",
            len(item_ids)
        )

        ml_items = get_items_bulk(
            item_ids
        )

        if not ml_items:
            logger.warning(
                "❌ API Mercado Livre não "
                "retornou produtos."
            )
            return

        # 5. Publicação.
        for index, item in enumerate(
            ml_items,
            start=1
        ):
            item_id = item.get("id")

            if not item_id:
                continue

            if item_id in history:
                continue

            product = normalize_item(
                item,
                affiliate_url=affiliate_map.get(
                    item_id
                )
            )

            if not product:
                continue

            coupon = get_coupon_for_item(
                item_id
            )

            product["coupon"] = coupon

            logger.info(
                "📤 Publicando %s/%s: %s",
                index,
                len(ml_items),
                product["title"]
            )

            success = send_offer_to_telegram(
                product
            )

            if success:
                save_history(item_id)

                logger.info(
                    "✅ Publicado: %s",
                    item_id
                )
            else:
                logger.error(
                    "❌ Falha ao publicar: %s",
                    item_id
                )

            if (
                index < len(ml_items)
                and intervalo > 0
            ):
                logger.info(
                    "⏳ Aguardando %s segundos...",
                    intervalo
                )

                time.sleep(intervalo)

    except Exception:
        logger.exception(
            "🔥 Erro geral no processamento."
        )


# ============================================================
# API CONFIGURAR
# ============================================================


@app.route("/api/configurar", methods=["OPTIONS"])
def configurar_options():
    return (
        "",
        200,
        {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": (
                "Content-Type, "
                "X-Telegram-Init-Data"
            ),
            "Access-Control-Allow-Methods": (
                "POST, OPTIONS"
            ),
        }
    )


@app.route("/api/configurar", methods=["POST"])
def configurar():
    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        ""
    )

    if not validate_telegram_init_data(
        init_data
    ):
        return jsonify({
            "ok": False,
            "error": "Telegram initData inválido."
        }), 401

    data = request.get_json(
        silent=True
    ) or {}

    vitrine_url = str(
        data.get("link")
        or data.get("vitrine")
        or data.get("url")
        or ""
    ).strip()

    try:
        quantidade = int(
            data.get(
                "quantidade",
                data.get("quantity", 5)
            )
        )
    except Exception:
        quantidade = 5

    try:
        intervalo_minutos = float(
            data.get(
                "intervalo",
                data.get("interval", 1)
            )
        )
    except Exception:
        intervalo_minutos = 1

    if not vitrine_url:
        return jsonify({
            "ok": False,
            "error": "Link da vitrine não informado."
        }), 400

    if not (
        vitrine_url.startswith(
            "https://meli.la/"
        )
        or
        vitrine_url.startswith(
            "https://www.mercadolivre.com.br/"
        )
        or
        vitrine_url.startswith(
            "https://mercadolivre.com.br/"
        )
    ):
        return jsonify({
            "ok": False,
            "error": "Link Mercado Livre inválido."
        }), 400

    quantidade = max(
        1,
        min(quantidade, 100)
    )

    intervalo_segundos = max(
        0,
        int(intervalo_minutos * 60)
    )

    logger.info("")
    logger.info("📥 NOVA CONFIGURAÇÃO")
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

    # NÃO espera o processamento terminar.
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

    return jsonify({
        "ok": True,
        "message": (
            "Automação iniciada em segundo plano."
        ),
        "quantidade": quantidade,
        "intervalo_segundos": intervalo_segundos,
    }), 200, {
        "Access-Control-Allow-Origin": "*"
    }


# ============================================================
# HEALTH
# ============================================================


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "bot-raposa-cacadora",
        "mercado_livre_configurado": (
            mercado_livre_configurado()
        ),
        "mercado_livre_autorizado": bool(
            runtime_token.get("access_token")
            or runtime_token.get("refresh_token")
        ),
        "telegram_configurado": bool(
            TELEGRAM_TOKEN
        ),
        "chat_id": CHAT_ID,
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
    })


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "Bot Raposa Caçadora",
        "status": "online",
        "health": "/health",
        "oauth": "/oauth/mercadolivre",
    })


# ============================================================
# EXECUÇÃO LOCAL
# ============================================================

if __name__ == "__main__":
    port = int(
        os.getenv("PORT", "5000")
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
