import os
import hmac
import hashlib
import json
import threading
import time
import uuid

from urllib.parse import parse_qsl

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

============================================================
APP
============================================================
app = Flask(name)

CORS(
app,
resources={
r"/api/": {
"origins": ""
}
}
)

============================================================
CONFIGURAÇÃO
============================================================
def carregar_env(nome):
"""
Lê uma variável de ambiente do Render.
Remove espaços e aspas acidentais.
"""

valor = os.environ.get(nome)

if valor is None:
    return ""

valor = str(valor).strip()

# Remove aspas caso alguém tenha colocado:

# "valor"

# 'valor'

if len(valor) >= 2:
    if (
        valor.startswith('"')
        and valor.endswith('"')
    ):
        valor = valor[1:-1].strip()

    elif (
        valor.startswith("'")
        and valor.endswith("'")
    ):
        valor = valor[1:-1].strip()

return valor

BOT_TOKEN = carregar_env("BOT_TOKEN")

CHANNEL_USERNAME = carregar_env(
"CHANNEL_USERNAME"
)

SHOPEE_API_URL = carregar_env(
"SHOPEE_API_URL"
)

SHOPEE_APP_ID = carregar_env(
"SHOPEE_APP_ID"
)

SHOPEE_APP_SECRET = carregar_env(
"SHOPEE_APP_SECRET"
)

TELEGRAM_INIT_DATA_REQUIRED = (
carregar_env(
"TELEGRAM_INIT_DATA_REQUIRED"
).lower()
in (
"1",
"true",
"yes",
"sim"
)
)

MAX_LINKS = 20

INTERVALOS_PERMITIDOS = {
10,
60,
300,
600
}

============================================================
DIAGNÓSTICO SEGURO
============================================================
def telegram_configurado():
"""
Nunca mostra o BOT_TOKEN.
Apenas informa se ele existe no processo atual.
"""

return bool(
    BOT_TOKEN
    and len(BOT_TOKEN) > 10
)

print(
"[CONFIG] BOT_TOKEN disponível:",
telegram_configurado()
)

print(
"[CONFIG] CHANNEL_USERNAME:",
CHANNEL_USERNAME
if CHANNEL_USERNAME
else "(não configurado)"
)

print(
"[CONFIG] TELEGRAM_INIT_DATA_REQUIRED:",
TELEGRAM_INIT_DATA_REQUIRED
)

============================================================
ARMAZENAMENTO
============================================================
tarefas = {}

tarefas_lock = threading.Lock()

============================================================
TELEGRAM INIT DATA
============================================================
def validar_init_data(init_data):

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

except Exception as erro:

    print(
        "[TELEGRAM] Erro validando initData:",
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

============================================================
SHOPEE
============================================================
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

============================================================
TAREFAS
============================================================
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

============================================================
PUBLICAÇÃO
============================================================
def publicar_produto(
link,
usuario
):

print(
    "[PUBLICAÇÃO] Produto:",
    link
)

print(
    "[PUBLICAÇÃO] Canal:",
    CHANNEL_USERNAME
    if CHANNEL_USERNAME
    else "(não configurado)"
)

# --------------------------------------------------------

# SIMULAÇÃO ATUAL

# --------------------------------------------------------

#
# Aqui entra a publicação REAL no Telegram.
#
# --------------------------------------------------------

time.sleep(3)

return {
    "sucesso": True,
    "mensagem": "Produto processado."
}

============================================================
WORKER
============================================================
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

    if indice >= quantidade:

        with tarefas_lock:

            tarefa = tarefas.get(task_id)

            if tarefa:

                tarefa["status"] = "concluida"

                tarefa["progresso"] = 100

                tarefa["produto_atual"] = quantidade

                tarefa["produto_link"] = ""

        return

    link = links[indice]

    numero_produto = indice + 1

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
                    "postado"
            })

            tarefa["produto_atual"] = numero_produto

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

            tarefa["produto_atual"] = numero_produto

            tarefa["progresso"] = round(
                (
                    numero_produto
                    /
                    quantidade
                ) * 100
            )

            tarefa["status"] = "erro"

    if not sucesso:

        time.sleep(1)

        continue

    if numero_produto >= quantidade:

        with tarefas_lock:

            tarefa = tarefas.get(task_id)

            if tarefa:

                tarefa["status"] = "concluida"

                tarefa["progresso"] = 100

        return

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

============================================================
PÁGINA
============================================================
@app.route("/")
def index():

return render_template(
    "index.html"
)

============================================================
HEALTH
============================================================
@app.route(
"/health",
methods=["GET"]
)
def health():

return jsonify({

    "status": "ok",

    "service":
        "raposa-cacadora",

    "telegram_configurado":
        telegram_configurado(),

    "canal_configurado":
        bool(CHANNEL_USERNAME),

    "init_data_obrigatorio":
        TELEGRAM_INIT_DATA_REQUIRED,

    "timestamp":
        int(time.time())
})

============================================================
CONFIGURAR
============================================================
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

    # TELEGRAM

    # ----------------------------------------------------

    init_data = dados.get(
        "initData",
        ""
    )

    if TELEGRAM_INIT_DATA_REQUIRED:

        if not BOT_TOKEN:

            return jsonify({

                "erro":
                    "BOT_TOKEN não está disponível para o processo do Render."
            }), 500

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

    links = links[:quantidade]

    # ----------------------------------------------------

    # CRIA TAREFA

    # ----------------------------------------------------

    task_id = criar_tarefa(
        links=links,
        intervalo=intervalo,
        quantidade=quantidade,
        usuario=usuario
    )

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

        "task_id":
            task_id,

        "quantidade":
            quantidade,

        "intervalo":
            intervalo
    })

except Exception as erro:

    print(
        "[API] Erro /api/configurar:",
        erro
    )

    return jsonify({

        "erro":
            "Erro interno do servidor.",

        "detalhes":
            str(erro)
    }), 500

============================================================
STATUS
============================================================
@app.route(
"/api/status/<task_id>",
methods=["GET"]
)
def status(task_id):

with tarefas_lock:

    tarefa = tarefas.get(task_id)

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

============================================================
PARAR
============================================================
@app.route(
"/api/parar/<task_id>",
methods=["POST"]
)
def parar(task_id):

with tarefas_lock:

    tarefa = tarefas.get(task_id)

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

============================================================
EXECUÇÃO
============================================================
if name == "main":

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
