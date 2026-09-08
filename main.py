import os
import logging

from flask import Flask, request, jsonify

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("raposa")


# ============================================================
# CORS — TESTE
# ============================================================

@app.after_request
def cors(response):

    response.headers["Access-Control-Allow-Origin"] = "*"

    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, X-Telegram-Init-Data"
    )

    response.headers["Access-Control-Allow-Methods"] = (
        "GET, POST, OPTIONS"
    )

    response.headers["Access-Control-Max-Age"] = "600"

    return response


# ============================================================
# HOME
# ============================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "ok": True,
        "service": "Bot Raposa Caçadora",
        "message": "Servidor funcionando"
    })


# ============================================================
# HEALTH
# ============================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "ok": True,
        "status": "online"
    })


# ============================================================
# OPTIONS
# ============================================================

@app.route("/api/configurar", methods=["OPTIONS"])
def configurar_options():

    logger.info("🌐 OPTIONS /api/configurar")

    return "", 204


# ============================================================
# POST
# ============================================================

@app.route("/api/configurar", methods=["POST"])
def configurar():

    logger.info("📥 POST /api/configurar")

    logger.info(
        "Origin: %s",
        request.headers.get("Origin")
    )

    logger.info(
        "Content-Type: %s",
        request.headers.get("Content-Type")
    )

    dados = request.get_json(
        silent=True
    )

    logger.info(
        "JSON recebido: %s",
        dados
    )

    return jsonify({
        "ok": True,
        "message": "POST chegou ao Render!",
        "dados": dados
    }), 200


# ============================================================
# ERRO
# ============================================================

@app.errorhandler(404)
def erro_404(error):

    return jsonify({
        "ok": False,
        "error": "Rota não encontrada"
    }), 404


@app.errorhandler(405)
def erro_405(error):

    return jsonify({
        "ok": False,
        "error": "Método não permitido"
    }), 405


# ============================================================
# START LOCAL
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv("PORT", "10000")
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
