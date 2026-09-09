import os
import hmac
import hashlib
import json
import threading
import time
from urllib.parse import parse_qsl

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

MAX_LINKS = 20

tarefas = {}
tarefas_lock = threading.Lock()


# ============================================================
# TELEGRAM INIT DATA
# ============================================================

def validar_init_data(init_data: str) -> bool:
    """
    Valida o initData enviado pelo Telegram Mini App.
    """

    if not BOT_TOKEN:
        # Durante desenvolvimento, permite funcionar
        # sem BOT_TOKEN configurado.
        return True

    if not init_data:
        return False

    try:
        dados = dict(parse_qsl(init_data, keep_blank_values=True))

        hash_recebido = dados.pop("hash", None)

        if not hash_recebido:
            return False

        data_check_string = "\n".join(
            f"{chave}={valor}"
            for chave, valor in sorted(dados.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        hash_calculado = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(
            hash_calculado,
            hash_recebido
        )

    except Exception:
        return False


def obter_usuario(init_data: str):
    """
    Extrai os dados básicos do usuário Telegram.
    """

    try:
        dados = dict(parse_qsl(
            init_data,
            keep_blank_values=True
        ))

        usuario = dados.get("user")

        if not usuario:
            return None

        return json.loads(usuario)

    except Exception:
        return None


# ============================================================
# VALIDAÇÃO
# ============================================================

def link_shopee_valido(link: str) -> bool:
    """
    Validação básica do endereço.
    """

    if not isinstance(link, str):
        return False

    link = link.strip().lower()

    if not (
        link.startswith("http://")
        or link.startswith("https://")
    ):
        return False

    return "shopee" in link


# ============================================================
# WORKER
# ============================================================

def executar_tarefa(task_id: str):
    """
    Worker de demonstração.

    Aqui posteriormente entra a automação real.
    """

    while True:

        with tarefas_lock:
            tarefa = tarefas.get(task_id)

            if not tarefa:
                return

            if tarefa["cancelada"]:
                tarefa["status"] = "cancelada"
                return

            produtos = tarefa["links"]

            index = tarefa["produto_atual"]

        if index >= len(produtos):

            with tarefas_lock:
                tarefa = tarefas.get(task_id)

                if tarefa:
                    tarefa["status"] = "concluida"
                    tarefa["progresso"] = 100
                    tarefa["produto_atual"] = len(produtos)

            return

        link = produtos[index]

        with tarefas_lock:
            tarefa = tarefas.get(task_id)

            if not tarefa:
                return

            tarefa["status"] = "processando"
            tarefa["produto_link"] = link
            tarefa["progresso"] = round(
                (index / len(produtos)) * 100
            )

        # ------------------------------------------------------
        # AQUI ENTRARÁ A PUBLICAÇÃO REAL
        # ------------------------------------------------------

        print(
            f"[AUTOMAÇÃO] Processando produto "
            f"{index + 1}: {link}"
        )

        # Simulação temporária.
        # Depois substituiremos pela automação real.
        time.sleep(3)

        with tarefas_lock:
            tarefa = tarefas.get(task_id)

            if not tarefa:
                return

            if tarefa["cancelada"]:
                tarefa["status"] = "cancelada"
                return

            tarefa["resultados"].append({
                "produto": index + 1,
                "link": link,
                "status": "postado"
            })

            tarefa["produto_atual"] = index + 1

            tarefa["progresso"] = round(
                (
                    (index + 1)
                    / len(produtos)
                ) * 100
            )

            tarefa["status"] = "aguardando"

        # Intervalo entre postagens
        intervalo = tarefa["intervalo"]

        for _ in range(intervalo):

            with tarefas_lock:
                tarefa = tarefas.get(task_id)

                if not tarefa:
                    return

                if tarefa["cancelada"]:
                    tarefa["status"] = "cancelada"
                    return

            time.sleep(1)


# ============================================================
# PÁGINA
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok"
    })


# ============================================================
# CONFIGURAR AUTOMAÇÃO
# ============================================================

@app.route(
    "/api/configurar",
    methods=["POST"]
)
def configurar():

    dados = request.get_json(
        silent=True
    )

    if not dados:
        return jsonify({
            "erro": "JSON inválido."
        }), 400

    init_data = dados.get(
        "initData",
        ""
    )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    if BOT_TOKEN:

        if not validar_init_data(
            init_data
        ):
            return jsonify({
                "erro":
                    "initData do Telegram inválido."
            }), 401

    usuario = obter_usuario(
        init_data
    )

    # --------------------------------------------------------
    # LINKS
    # --------------------------------------------------------

    links = dados.get(
        "links",
        []
    )

    intervalo = dados.get(
        "intervalo",
        10
    )

    quantidade = dados.get(
        "quantidade",
        1
    )

    if not isinstance(
        links,
        list
    ):
        return jsonify({
            "erro":
                "A lista de links é inválida."
        }), 400

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

    # --------------------------------------------------------
    # VALIDAÇÃO DOS LINKS
    # --------------------------------------------------------

    links = [
        str(link).strip()
        for link in links
        if str(link).strip()
    ]

    invalidos = [
        link
        for link in links
        if not link_shopee_valido(link)
    ]

    if invalidos:

        return jsonify({
            "erro":
                "Existem links inválidos da Shopee."
        }), 400

    # --------------------------------------------------------
    # QUANTIDADE
    # --------------------------------------------------------

    try:
        quantidade = int(
            quantidade
        )
    except Exception:
        quantidade = 1

    if quantidade < 1:
        return jsonify({
            "erro":
                "Quantidade inválida."
        }), 400

    if quantidade > len(links):
        return jsonify({
            "erro":
                "A quantidade não pode ser maior que os produtos."
        }), 400

    # --------------------------------------------------------
    # INTERVALO
    # --------------------------------------------------------

    try:
        intervalo = int(
            intervalo
        )
    except Exception:
        intervalo = 10

    intervalos_permitidos = {
        10,
        60,
        300,
        600
    }

    if intervalo not in intervalos_permitidos:
        return jsonify({
            "erro":
                "Intervalo inválido."
        }), 400

    links = links[:quantidade]

    # --------------------------------------------------------
    # ID DA TAREFA
    # --------------------------------------------------------

    import uuid

    task_id = str(
        uuid.uuid4()
    )

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
        "resultados": []
    }

    with tarefas_lock:
        tarefas[task_id] = tarefa

    # --------------------------------------------------------
    # INICIA WORKER
    # --------------------------------------------------------

    thread = threading.Thread(
        target=executar_tarefa,
        args=(task_id,),
        daemon=True
    )

    thread.start()

    return jsonify({
        "sucesso": True,
        "mensagem":
            "Automação iniciada com sucesso.",
        "task_id": task_id
    })


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
# START
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
