import json
import os
import threading
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask

# ==========================================
# SERVIDOR WEB PARA O RENDER (PORT BINDING)
# ==========================================
app = Flask(__name__)


@app.route("/")
def home():
    return "Bot Raposa Caçadora está Online 24/7!"


def iniciar_servidor_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ==========================================
# CONFIGURAÇÕES DO BOT VIA NUVEM
# ==========================================
TELEGRAM_TOKEN = os.getenv("8986739105:AAHNelnHiR6iOmNp-9x6Bf3P9ciKoou7jy0")
CHAT_ID = "@raposacacadora"
ARQUIVO_HISTORICO = "produtos_postados.txt"

# ------------------------------------------
# FUNÇÕES DE POSTAGEM E SCRAPING
# ------------------------------------------


def carregar_historico():
    if not os.path.exists(ARQUIVO_HISTORICO):
        return set()
    with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
        return set(linha.strip() for linha in f if linha.strip())


def salvar_historico(link):
    with open(ARQUIVO_HISTORICO, "a", encoding="utf-8") as f:
        f.write(f"{link}\n")


def enviar_oferta(foto_url, legenda, link_afiliado):
    url_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"

    teclado = {
        "inline_keyboard": [
            [{"text": "🛒 COMPRAR NO MERCADO LIVRE", "url": link_afiliado}]
        ]
    }

    payload = {
        "chat_id": CHAT_ID,
        "photo": foto_url,
        "caption": legenda,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(teclado),
    }

    response = requests.post(url_api, data=payload)
    return response.json().get("ok", False)


def processar_e_postar_vitrine(url_vitrine, quantidade_maxima, intervalo_seg):
    print(f"\n🦊 Lendo vitrine do Mercado Livre: {url_vitrine}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        res = requests.get(url_vitrine, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        print(f"❌ Erro ao acessar a vitrine: {e}")
        return

    links_encontrados = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "produto.mercadolivre.com.br" in href or "/p/MLB" in href:
            links_encontrados.append(href.split("#")[0])

    links_unicos = list(dict.fromkeys(links_encontrados))
    historico = carregar_historico()

    postados_nesta_rodada = 0

    for link in links_unicos:
        if postados_nesta_rodada >= quantidade_maxima:
            break

        if link in historico:
            continue

        print(f"🔍 Extraindo item: {link}")

        try:
            prod_res = requests.get(link, headers=headers, timeout=10)
            prod_soup = BeautifulSoup(prod_res.text, "html.parser")

            titulo_elem = prod_soup.find("h1", {"class": "ui-pdp-title"})
            titulo = (
                titulo_elem.text.strip()
                if titulo_elem
                else "Oferta Imperdível Mercado Livre!"
            )

            foto_elem = prod_soup.find("img", {"class": "ui-pdp-image"})
            foto_url = (
                foto_elem["src"]
                if foto_elem and "src" in foto_elem.attrs
                else ""
            )

            if not foto_url:
                continue

            legenda = (
                f"🔥 <b>{titulo}</b>\n\n"
                f"⚡ <i>Aproveite esta promoção por tempo limitado!</i>\n\n"
                f"👉 <b>Clique abaixo para ver a oferta:</b>"
            )

            if enviar_oferta(foto_url, legenda, link):
                salvar_historico(link)
                postados_nesta_rodada += 1
                print(
                    f"✅ [POSTADO {postados_nesta_rodada}/{quantidade_maxima}] {titulo[:30]}..."
                )

                if postados_nesta_rodada < quantidade_maxima:
                    print(f"⏳ Aguardando {intervalo_seg}s para o próximo...")
                    time.sleep(intervalo_seg)

        except Exception as err:
            print(f"⚠️ Falha ao processar produto: {err}")

    print(
        f"\n🎯 Concluído! Total de {postados_nesta_rodada} ofertas enviadas para o canal."
    )


# ------------------------------------------
# ESCUTADOR DE COMANDOS DO TELEGRAM
# ------------------------------------------


def escutar_mini_app():
    print("🚀 Bot Raposa Caçadora Iniciado e Aguardando Ordens do Mini App...")
    offset = 0

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=30"
            res = requests.get(url, timeout=35).json()

            if "result" in res:
                for update in res["result"]:
                    offset = update["update_id"] + 1

                    if (
                        "message" in update
                        and "web_app_data" in update["message"]
                    ):
                        dados_raw = update["message"]["web_app_data"]["data"]
                        config = json.loads(dados_raw)

                        link = config.get("link")
                        intervalo = config.get("intervalo", 300)
                        quantidade = config.get("quantidade", 5)

                        print("\n📩 ORDEM RECEBIDA DO MINI APP!")
                        print(f"🔗 Link: {link}")
                        print(f"⏱️ Intervalo: {intervalo} segundos")
                        print(f"📦 Quantidade: {quantidade} itens")

                        processar_e_postar_vitrine(link, quantidade, intervalo)

        except Exception as e:
            print(f"⚠️ Conexão oscilou, reconectando... ({e})")
            time.sleep(5)


if __name__ == "__main__":
    t = threading.Thread(target=iniciar_servidor_web)
    t.daemon = True
    t.start()

    escutar_mini_app()
