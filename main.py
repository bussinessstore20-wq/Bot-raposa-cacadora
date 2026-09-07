import os
import re
import json
import time
import html
import threading
import hashlib
import hmac
from urllib.parse import parse_qsl, urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_from_directory

# ============================================================
# RAPOSA CAÇADORA - main.py
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE_DIR, "index.html")
ARQUIVO_HISTORICO = os.path.join(BASE_DIR, "produtos_postados.txt")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "@raposacacadora").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
PORT = int(os.getenv("PORT", "10000"))

MAX_QUANTIDADE = 50
MIN_INTERVALO = 10
HTTP_TIMEOUT = 30

app = Flask(__name__, static_folder=BASE_DIR)

automacoes_lock = threading.Lock()
automacoes_ativas = 0
historico_lock = threading.Lock()
session = requests.Session()

def obter_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }

@app.route("/", methods=["GET"])
def home():
    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Raposa Caçadora</title>
        <style>
            body { background: #05070a; color: white; font-family: sans-serif; text-align: center; padding-top: 50px; }
            h1 { color: #f97316; }
            a { color: #fb923c; text-decoration: none; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>🦊 Raposa Caçadora VIP</h1>
        <p>● SERVIDOR ONLINE E OPERACIONAL</p>
        <p><a href="/app">Abrir Painel Mini App</a> | <a href="/health">Health Check</a></p>
    </body>
    </html>
    """

@app.route("/app", methods=["GET"])
def mini_app():
    if not os.path.isfile(INDEX_FILE):
        return "❌ Arquivo index.html não encontrado no servidor.", 404
    return send_from_directory(BASE_DIR, "index.html")

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

def validar_init_data(init_data):
    if not init_data or not TELEGRAM_TOKEN:
        return False
    try:
        dados = dict(parse_qsl(init_data, keep_blank_values=True))
        hash_recebido = dados.pop("hash", None)
        if not hash_recebido:
            return False

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(dados.items()))
        secret_key = hmac.new(b"WebAppData", TELEGRAM_TOKEN.encode("utf-8"), hashlib.sha256).digest()
        calculado = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        return hmac.compare_digest(calculado, hash_recebido)
    except Exception as e:
        print(f"⚠️ Erro ao validar initData: {e}")
        return False

def carregar_historico():
    if not os.path.exists(ARQUIVO_HISTORICO):
        return set()
    try:
        with historico_lock:
            with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
                return {linha.strip() for linha in f if linha.strip()}
    except Exception:
        return set()

def salvar_historico(link):
    if not link:
        return False
    try:
        with historico_lock:
            with open(ARQUIVO_HISTORICO, "a", encoding="utf-8") as f:
                f.write(link.strip() + "\n")
        return True
    except Exception:
        return False

def enviar_oferta(foto_url, legenda, link_produto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    keyboard = {
        "inline_keyboard": [[
            {"text": "🛒 COMPRAR AGORA", "url": link_produto}
        ]]
    }
    payload = {
        "chat_id": CHAT_ID,
        "photo": foto_url,
        "caption": legenda,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(keyboard)
    }
    try:
        res = session.post(url, data=payload, timeout=HTTP_TIMEOUT)
        return res.json().get("ok", False)
    except Exception as e:
        print(f"❌ Erro ao enviar para o Telegram: {e}")
        return False

def extrair_dados_natura(url_produto):
    headers = obter_headers()
    try:
        res = session.get(url_produto, headers=headers, timeout=HTTP_TIMEOUT)
        soup = BeautifulSoup(res.text, 'html.parser')

        og_title = soup.find("meta", property="og:title")
        og_image = soup.find("meta", property="og:image")

        titulo = og_title["content"].strip() if og_title else ""
        foto_url = og_image["content"].strip() if og_image else ""

        if not titulo:
            h1 = soup.find("h1")
            titulo = h1.text.strip() if h1 else "Oferta Exclusiva Natura!"

        if not foto_url:
            img = soup.find("img", src=re.compile(r'natura|product', re.IGNORECASE))
            foto_url = img["src"] if img and "src" in img.attrs else ""

        return titulo, foto_url
    except Exception as e:
        print(f"⚠️ Erro ao extrair dados da Natura: {e}")
        return None, None

def processar_e_postar_vitrine(url_vitrine, quantidade_maxima, intervalo_seg):
    global automacoes_ativas
    headers = obter_headers()

    with automacoes_lock:
        automacoes_ativas += 1

    try:
        print(f"\n🦊 Processando URL: {url_vitrine}")
        res_redir = session.get(url_vitrine, headers=headers, allow_redirects=True, timeout=HTTP_TIMEOUT)
        url_final = res_redir.url
        print(f"🔗 Link Expandido: {url_final}")

        # 1. PROCESSAMENTO NATURA
        if "natura.com.br" in url_final:
            print("🌿 Processando Natura...")
            titulo, foto_url = extrair_dados_natura(url_final)
            if foto_url:
                legenda = f"🌿 <b>{titulo}</b>\n\n✨ <i>Aproveite esta oferta no meu Espaço Natura!</i>\n\n👉 <b>Clique abaixo para ver a oferta:</b>"
                if enviar_oferta(foto_url, legenda, url_vitrine):
                    salvar_historico(url_vitrine)
                    print("✅ Oferta da Natura postada com sucesso!")
            return

        # 2. PROCESSAMENTO MERCADO LIVRE
        res = session.get(url_final, headers=headers, timeout=HTTP_TIMEOUT)
        soup = BeautifulSoup(res.text, 'html.parser')

        links_encontrados = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if any(p in href for p in ["produto.mercadolivre.com.br", "/p/MLB", "MLB-", "/sec/"]):
                links_encontrados.append(href.split('#')[0])

        if not links_encontrados and any(p in url_final for p in ["produto.mercadolivre.com.br", "/p/MLB", "MLB-"]):
            links_encontrados.append(url_final)

        links_unicos = list(dict.fromkeys(links_encontrados))
        historico = carregar_historico()
        postados = 0

        for link in links_unicos:
            if postados >= quantidade_maxima:
                break
            if link in historico:
                continue

            try:
                prod_res = session.get(link, headers=headers, allow_redirects=True, timeout=HTTP_TIMEOUT)
                prod_soup = BeautifulSoup(prod_res.text, 'html.parser')

                titulo_elem = prod_soup.find("h1", {"class": "ui-pdp-title"})
                titulo = titulo_elem.text.strip() if titulo_elem else "Oferta Imperdível Mercado Livre!"

                foto_elem = prod_soup.find("img", {"class": "ui-pdp-image"})
                foto_url = foto_elem.get("src") or foto_elem.get("data-src") or "" if foto_elem else ""

                if not foto_url:
                    continue

                legenda = f"🔥 <b>{titulo}</b>\n\n⚡ <i>Aproveite esta promoção no Mercado Livre!</i>\n\n👉 <b>Clique abaixo para ver a oferta:</b>"

                if enviar_oferta(foto_url, legenda, link):
                    salvar_historico(link)
                    postados += 1
                    print(f"✅ [POSTADO {postados}/{quantidade_maxima}] {titulo[:30]}...")

                    if postados < quantidade_maxima:
                        time.sleep(intervalo_seg)
            except Exception as e:
                print(f"⚠️ Falha ao extrair produto do ML: {e}")

    finally:
        with automacoes_lock:
            automacoes_ativas -= 1

@app.route("/api/configurar", methods=["POST"])
@app.route("/configurar", methods=["POST"])
def api_configurar():
    try:
        dados = request.get_json(silent=True) or {}
        link = str(dados.get("link", "")).strip()
        intervalo = int(dados.get("intervalo", 300))
        quantidade = int(dados.get("quantidade", 5))
        init_data = str(dados.get("initData", "")).strip()

        if not link:
            return jsonify({"erro": "O link da vitrine é obrigatório."}), 400

        if not validar_init_data(init_data):
            return jsonify({"erro": "Autenticação do Telegram inválida ou expirada."}), 403

        threading.Thread(
            target=processar_e_postar_vitrine,
            args=(link, quantidade, intervalo),
            daemon=True
        ).start()

        return jsonify({"sucesso": True, "mensagem": "Automação iniciada com sucesso!"}), 200

    except Exception as e:
        return jsonify({"erro": f"Erro interno no servidor: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
    
