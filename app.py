@app.route("/debug-env", methods=["GET"])
def debug_env():
    token = os.environ.get("BOT_TOKEN", "")
    channel = os.environ.get("CHANNEL_USERNAME", "")

    return jsonify({
        "BOT_TOKEN_existe": bool(token),
        "BOT_TOKEN_tamanho": len(token),
        "CHANNEL_USERNAME_existe": bool(channel),
        "CHANNEL_USERNAME": channel,
        "PORT": os.environ.get("PORT", ""),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )
