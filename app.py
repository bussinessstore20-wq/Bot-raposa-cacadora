@app.route("/debug-env")
def debug_env():
    token = os.environ.get("BOT_TOKEN")

    return jsonify({
        "BOT_TOKEN_existe": bool(token),
        "BOT_TOKEN_tamanho": len(token) if token else 0,
        "CHANNEL_USERNAME_existe": bool(
            os.environ.get("CHANNEL_USERNAME")
        ),
        "telegram_required": os.environ.get(
            "TELEGRAM_INIT_DATA_REQUIRED"
        )
    })
