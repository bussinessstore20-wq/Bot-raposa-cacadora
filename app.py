import os
import hmac
import hashlib
import json
import threading
import time
import uuid

from urllib.parse import parse_qsl

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

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

CHANNEL_USERNAME = os.environ.get(
    "CHANNEL_USERNAME",
    "@raposacacadora"
).strip()

TELEGRAM_INIT_DATA_REQUIRED = (
    os.environ.get(
        "TELEGRAM_INIT_DATA_REQUIRED",
        "false"
    ).strip().lower()
    in ("1", "true", "yes", "sim")
)

MAX_LINKS = 20

INTERVALOS_PERMITIDOS = {
    10,
    60,
    300,
    600
}


# ============================================================
# ARMAZENAMENTO TEMPORÁRIO
# ============================================================

tarefas = {}

tarefas_lock = threading.Lock()


# ============================================================
# TELEGRAM - VALIDAR INIT DATA
# ============================================================

def validar_init_data(init_data):
    """
    Valida o initData recebido do Telegram.

    Quando BOT_TOKEN não existe:
    - retorna False

    Quando BOT_TOKEN existe:
    - valida assinatura do Telegram.
    """

    if not BOT_TOKEN:
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
            BOT_TOKEN.encode("utf-8"),
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
            "[TELEGRAM] Erro validando initData:",
            erro
        )

        return False


# ============================================================
# TELEGRAM - OBTER USUÁRIO
# ============================================================

def obter_usuario(init_data):
    """
    Obtém os dados do usuário do Telegram.
    """

    if not init_data:
        return None

    try:
        dados = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        usuario = dados.get("user")

        if not usuario:
            return None

        return json.loads(usuario)

    except Exception as erro:
        print(
            "[TELEGRAM] Erro obtendo usuário:",
            erro
        )

        return None


# ============================================================
# TELEGRAM - ENVIAR MENSAGEM
# ============================================================

def enviar_mensagem_telegram(texto):
    """
    Envia uma mensagem para o canal configurado.

    O bot precisa ser administrador do canal.
    """

    if not BOT_TOKEN:
        return {
            "sucesso": False,
            "mensagem": "BOT_TOKEN não configurado no Render."
        }

    if not CHANNEL_USERNAME:
        return {
            "sucesso": False,
            "mensagem": "CHANNEL_USERNAME não configurado."
        }

    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHANNEL_USERNAME,
        "text": texto,
        "disable_web_page_preview": False
    }

    try:
        resposta = requests.post(
            url,
            json=payload,
            timeout=20
        )

        dados = resposta.json()

        if not resposta.ok or not dados.get("ok"):
            print(
                "[TELEGRAM] Erro:",
                dados
            )

            return {
                "sucesso": False,
                "mensagem": (
                    dados.get(
                        "description",
                        "Erro ao enviar mensagem para o Telegram."
                    )
                )
            }

        return {
            "sucesso": True,
            "mensagem": "Mensagem enviada para o canal."
        }

    except Exception as erro:
        print(
            "[TELEGRAM] Falha de conexão:",
            erro
        )

        return {
            "sucesso": False,
            "mensagem": str(erro)
        }


# ============================================================
# SHOPEE
# ============================================================

def link_shopee_valido(link):
    """
    Validação básica do link Shopee.
    """

    if not isinstance(link, str):
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

    return "shopee" in link_lower


# ============================================================
# CRIAR TAREFA
# ============================================================

def criar_tarefa(
    links,
    intervalo,
    quantidade,
    usuario
):
    task_id = str(uuid.uuid4())

    tarefa = {
        "id": task_id,
        "usuario": usuario,
        "links": links,
        "intervalo": intervalo,
        "quantidade": quantidade,
        "produto_atual": 0,
        "produto_link": "",
        "progresso": 0,
        "status": "iniciando",
        "cancelada": False,
        "resultados": [],
        "criada_em": time.time()
    }

    with tarefas_lock:
        tarefas[task_id] = tarefa

    return task_id


# ============================================================
# PUBLICAR PRODUTO
# ============================================================

def publicar_produto(link, usuario):
    """
    Publica o produto no canal do Telegram.

    Neste momento usamos o próprio link como mensagem.

    Depois podemos substituir esta função pela integração
    completa da Shopee/API.
    """

    nome_usuario = ""

    if isinstance(usuario, dict):
        nome_usuario = (
            usuario.get("first_name")
            or
            usuario.get("username")
            or
            ""
        )

    texto = (
        "🦊 RAPOSA CAÇADORA\n\n"
        "🛍️ Nova oferta Shopee!\n\n"
        f"🔗 {link}"
    )

    if nome_usuario:
        texto += (
            f"\n\n👤 Enviado por: {nome_usuario}"
        )

    resultado = enviar_mensagem_telegram(
        texto
    )

    if not resultado["sucesso"]:
        return {
            "sucesso": False,
            "mensagem": resultado["mensagem"]
        }

    return {
        "sucesso": True,
        "mensagem": "Produto publicado no canal."
    }


# ============================================================
# WORKER
# ============================================================

def executar_tarefa(task_id):

    print(
        f"[TASK] Iniciando {task_id}"
    )

    while True:

        with tarefas_lock:

            tarefa = tarefas.get(task_id)

            if not tarefa:
                return

            if tarefa["cancelada"]:
                tarefa["status"] = "cancelada"
                return

            indice = tarefa["produto_atual"]

            links = list(
                tarefa["links"]
            )

            quantidade = tarefa["quantidade"]

            usuario = tarefa["usuario"]

            intervalo = tarefa["intervalo"]

        # ----------------------------------------------------
        # FINALIZAÇÃO
        # ----------------------------------------------------

        if indice >= quantidade:

            with tarefas_lock:

                tarefa = tarefas.get(task_id)

                if tarefa:

                    tarefa["status"] = "concluida"

                    tarefa["progresso"] = 100

                    tarefa["produto_atual"] = quantidade

                    tarefa["produto_link"] = ""

            print(
                f"[TASK] Concluída {task_id}"
            )

            return

        # ----------------------------------------------------
        # PRODUTO
        # ----------------------------------------------------

        link = links[indice]

        numero_produto = indice + 1

        # ----------------------------------------------------
        # STATUS PROCESSANDO
        # ----------------------------------------------------

        with tarefas_lock:

            tarefa = tarefas.get(task_id)

            if not tarefa:
                return

            tarefa["status"] = "processando"

            tarefa["produto_link"] = link

            tarefa["progresso"] = round(
                (
                    indice
                    /
                    quantidade
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
                "mensagem": str(erro)
            }

        # ----------------------------------------------------
        # RESULTADO
        # ----------------------------------------------------

        with tarefas_lock:

            tarefa = tarefas.get(task_id)

            if not tarefa:
                return

            if tarefa["cancelada"]:

                tarefa["status"] = "cancelada"

                return

            if sucesso:

                tarefa["resultados"].append({

                    "produto":
                        numero_produto,

                    "link":
                        link,

                    "status":
                        "postado",

                    "mensagem":
                        resultado.get(
                            "mensagem",
                            "Publicado."
                        )
                })

                tarefa["produto_atual"] = (
                    numero_produto
                )

                tarefa["progresso"] = round(
                    (
                        numero_produto
                        /
                        quantidade
                    ) * 100
                )

                tarefa["status"] = "aguardando"

            else:

                tarefa["resultados"].append({

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

                tarefa["produto_atual"] = (
                    numero_produto
                )

                tarefa["progresso"] = round(
                    (
                        numero_produto
                        /
                        quantidade
                    ) * 100
                )

                tarefa["status"] = "erro"

        # ----------------------------------------------------
        # ERRO
        # ----------------------------------------------------

        if not sucesso:

            print(
                f"[TASK] Produto "
                f"{numero_produto} falhou."
            )

            time.sleep(1)

            continue

        # ----------------------------------------------------
        # ÚLTIMO PRODUTO
        # ----------------------------------------------------

        if numero_produto >= quantidade:

            with tarefas_lock:

                tarefa = tarefas.get(task_id)

                if tarefa:

                    tarefa["status"] = "concluida"

                    tarefa["progresso"] = 100

                    tarefa["produto_link"] = ""

            print(
                f"[TASK] Finalizada {task_id}"
            )

            return

        # ----------------------------------------------------
        # INTERVALO
        # ----------------------------------------------------

        with tarefas_lock:

            tarefa = tarefas.get(task_id)

            if tarefa:
                tarefa["status"] = "aguardando"

        segundos_restantes = intervalo

        while segundos_restantes > 0:

            with tarefas_lock:

                tarefa = tarefas.get(task_id)

                if not tarefa:
                    return

                if tarefa["cancelada"]:

                    tarefa["status"] = "cancelada"

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
# HEALTH CHECK
# ============================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "status": "ok",

        "service": "raposa-cacadora",

        "telegram_configurado":
            bool(BOT_TOKEN),

        "channel":
            CHANNEL_USERNAME,

        "timestamp":
            int(time.time())
    })


# ============================================================
# TESTE DO TELEGRAM
# ============================================================

@app.route(
    "/api/testar-telegram",
    methods=["GET"]
)
def testar_telegram():

    if not BOT_TOKEN:

        return jsonify({

            "sucesso": False,

            "erro":
                "BOT_TOKEN não está disponível para o processo do Render."
        }), 500

    if not CHANNEL_USERNAME:

        return jsonify({

            "sucesso": False,

            "erro":
                "CHANNEL_USERNAME não está configurado."
        }), 500

    resultado = enviar_mensagem_telegram(
        "🦊 Teste da Raposa Caçadora.\n\n"
        "Telegram conectado com sucesso!"
    )

    if not resultado["sucesso"]:

        return jsonify(
            resultado
        ), 500

    return jsonify(
        resultado
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
        # INIT DATA
        # ----------------------------------------------------

        init_data = dados.get(
            "initData",
            ""
        )

        if TELEGRAM_INIT_DATA_REQUIRED:

            if not validar_init_data(
                init_data
            ):

                return jsonify({
                    "erro":
                        "Sessão do Telegram inválida."
                }), 401

        elif BOT_TOKEN and init_data:

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

        if len(links) == 0:

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
        # VALIDAR LINKS
        # ----------------------------------------------------

        invalidos = [
            link
            for link in links
            if not link_shopee_valido(link)
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
        # LIMITAR LINKS
        # ----------------------------------------------------

        links = links[
            :quantidade
        ]

        # ----------------------------------------------------
        # VERIFICAR BOT ANTES DE CRIAR TAREFA
        # ----------------------------------------------------

        if not BOT_TOKEN:

            return jsonify({

                "erro":
                    "BOT_TOKEN não está disponível para o processo do Render."
            }), 500

        if not CHANNEL_USERNAME:

            return jsonify({

                "erro":
                    "CHANNEL_USERNAME não está configurado no Render."
            }), 500

        # ----------------------------------------------------
        # CRIAR TAREFA
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

            "sucesso": True,

            "mensagem":
                "Automação iniciada com sucesso.",

            "task_id":
                task_id,

            "quantidade":
                quantidade,

            "intervalo":
                intervalo,

            "canal":
                CHANNEL_USERNAME
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

        tarefa["cancelada"] = True

        tarefa["status"] = "cancelada"

    return jsonify({

        "sucesso": True,

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
