from functools import wraps

import requests
from flask import Flask, request, session, redirect, url_for, render_template_string

app = Flask(__name__)
app.secret_key = "clave-demo-banco2"  # solo para firmar la cookie de sesion, no protege datos sensibles

API_INTERNA = "http://10.20.1.34:5000"  # IP del nodo API, VLAN 40


# ---------------------------------------------------------------------------
# Layout comun
# ---------------------------------------------------------------------------
LAYOUT = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Banco 2 - WEB-PUB</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; background:#f4f4f4; }
    .caja { background:#fff; border:1px solid #ccc; border-radius:6px; padding:1.2rem; max-width:600px; margin-bottom:1rem; }
    input, select { display:block; margin:.4rem 0 1rem; padding:.4rem; width:100%; max-width:300px; }
    button { padding:.5rem 1rem; cursor:pointer; }
    table { border-collapse: collapse; width:100%; max-width:700px; }
    td, th { border:1px solid #ccc; padding:.4rem .6rem; text-align:left; }
    nav a { margin-right:1rem; }
    .msg-ok { color: green; }
    .msg-error { color: red; }
  </style>
</head>
<body>
  <h2>Banco 2 &mdash; Banca de Inversion</h2>
  {% if session.get('usuario') %}
    <nav>
      <span>{{ session['usuario']['nombre_completo'] }} ({{ session['usuario']['rol'] }})</span>
      &nbsp;|&nbsp; <a href="{{ url_for('logout') }}">Cerrar sesion</a>
    </nav>
    <hr>
  {% endif %}
  {% if msg %}
    <p class="{{ 'msg-ok' if ok else 'msg-error' }}">{{ msg }}</p>
  {% endif %}
  {{ contenido | safe }}
</body>
</html>
"""


def render(contenido_html, **kw):
    msg = request.args.get("msg")
    ok = request.args.get("ok") == "1"
    return render_template_string(
        LAYOUT, contenido=render_template_string(contenido_html, **kw), msg=msg, ok=ok
    )


def requiere_rol(rol_esperado):
    def decorador(f):
        @wraps(f)
        def envoltura(*args, **kwargs):
            usuario = session.get("usuario")
            if not usuario:
                return redirect(url_for("login"))
            if usuario["rol"] != rol_esperado:
                return redirect(url_for("index"))
            return f(*args, **kwargs)

        return envoltura

    return decorador


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    usuario = session.get("usuario")
    if not usuario:
        return redirect(url_for("login"))
    return redirect(url_for(usuario["rol"]))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        try:
            resp = requests.post(
                f"{API_INTERNA}/login",
                json={"username": username, "password": password},
                timeout=5,
            )
            data = resp.json()
        except requests.RequestException:
            return redirect(
                url_for("login", msg="No se pudo contactar la API interna", ok="0")
            )

        if not data.get("ok"):
            return redirect(
                url_for(
                    "login", msg=data.get("error", "credenciales invalidas"), ok="0"
                )
            )

        session["usuario"] = data["usuario"]
        return redirect(url_for(data["usuario"]["rol"]))

    return render("""
    <div class="caja">
      <h3>Iniciar sesion</h3>
      <form method="post">
        <label>Usuario</label>
        <input name="username" required>
        <label>Contrasena</label>
        <input name="password" type="password" required>
        <button type="submit">Entrar</button>
      </form>
    </div>
    """)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Rol: cliente
# ---------------------------------------------------------------------------
@app.route("/cliente")
@requiere_rol("cliente")
def cliente():
    usuario_id = session["usuario"]["id"]
    resp = requests.get(f"{API_INTERNA}/cuentas/{usuario_id}", timeout=5).json()
    return render(
        """
    <div class="caja">
      <h3>Mis cuentas</h3>
      <table>
        <tr><th>Numero</th><th>Saldo</th><th></th></tr>
        {% for c in cuentas %}
        <tr>
          <td>{{ c['numero_cuenta'] }}</td>
          <td>Q {{ '%.2f'|format(c['saldo']) }}</td>
          <td><a href="{{ url_for('cliente_movimientos', cuenta_id=c['id']) }}">Ver movimientos</a></td>
        </tr>
        {% endfor %}
      </table>
    </div>
    """,
        cuentas=resp.get("cuentas", []),
    )


@app.route("/cliente/movimientos/<int:cuenta_id>")
@requiere_rol("cliente")
def cliente_movimientos(cuenta_id):
    resp = requests.get(
        f"{API_INTERNA}/cuentas/{cuenta_id}/movimientos", timeout=5
    ).json()
    return render(
        """
    <div class="caja">
      <h3>Movimientos de la cuenta {{ cuenta_id }}</h3>
      <table>
        <tr><th>Tipo</th><th>Origen</th><th>Destino</th><th>Banco contraparte</th><th>Monto</th><th>Fecha</th></tr>
        {% for m in movimientos %}
        <tr>
          <td>{{ m['tipo'] }}</td>
          <td>{{ m['cuenta_origen_id'] or '-' }}</td>
          <td>{{ m['cuenta_destino_id'] or '-' }}</td>
          <td>{{ m['banco_contraparte'] or '-' }}</td>
          <td>Q {{ '%.2f'|format(m['monto']) }}</td>
          <td>{{ m['fecha'] }}</td>
        </tr>
        {% endfor %}
      </table>
      <p><a href="{{ url_for('cliente') }}">Volver</a></p>
    </div>
    """,
        cuenta_id=cuenta_id,
        movimientos=resp.get("movimientos", []),
    )


# ---------------------------------------------------------------------------
# Rol: cajero
# ---------------------------------------------------------------------------
@app.route("/cajero")
@requiere_rol("cajero")
def cajero():
    return render("""
    <div class="caja">
      <h3>Deposito</h3>
      <form method="post" action="{{ url_for('cajero_deposito') }}">
        <label>Cuenta ID</label><input name="cuenta_id" required>
        <label>Monto</label><input name="monto" required>
        <button type="submit">Depositar</button>
      </form>
    </div>
    <div class="caja">
      <h3>Retiro</h3>
      <form method="post" action="{{ url_for('cajero_retiro') }}">
        <label>Cuenta ID</label><input name="cuenta_id" required>
        <label>Monto</label><input name="monto" required>
        <button type="submit">Retirar</button>
      </form>
    </div>
    <div class="caja">
      <h3>Transferencia interna (dentro de Banco 2)</h3>
      <form method="post" action="{{ url_for('cajero_transferencia') }}">
        <label>Cuenta origen</label><input name="cuenta_origen" required>
        <label>Cuenta destino</label><input name="cuenta_destino" required>
        <label>Monto</label><input name="monto" required>
        <button type="submit">Transferir</button>
      </form>
    </div>
    <div class="caja">
      <h3>Transferencia interbancaria (a otro banco)</h3>
      <form method="post" action="{{ url_for('cajero_interbancaria') }}">
        <label>Cuenta origen (propia)</label><input name="cuenta_origen" required>
        <label>Banco destino</label>
        <select name="banco_destino">
          <option value="Banco1">Banco1</option>
          <option value="Banco3">Banco3</option>
        </select>
        <label>Cuenta destino remota (ID en el otro banco)</label><input name="cuenta_destino_remota" required>
        <label>Monto</label><input name="monto" required>
        <button type="submit">Enviar</button>
      </form>
    </div>
    """)


@app.route("/cajero/deposito", methods=["POST"])
@requiere_rol("cajero")
def cajero_deposito():
    body = {
        "cuenta_id": int(request.form["cuenta_id"]),
        "monto": float(request.form["monto"]),
    }
    data = requests.post(
        f"{API_INTERNA}/transacciones/deposito", json=body, timeout=5
    ).json()
    if data.get("ok"):
        return redirect(
            url_for(
                "cajero",
                msg=f"Deposito realizado. Nuevo saldo: Q{data['saldo']:.2f}",
                ok="1",
            )
        )
    return redirect(
        url_for("cajero", msg=data.get("error", "error desconocido"), ok="0")
    )


@app.route("/cajero/retiro", methods=["POST"])
@requiere_rol("cajero")
def cajero_retiro():
    body = {
        "cuenta_id": int(request.form["cuenta_id"]),
        "monto": float(request.form["monto"]),
    }
    data = requests.post(
        f"{API_INTERNA}/transacciones/retiro", json=body, timeout=5
    ).json()
    if data.get("ok"):
        return redirect(
            url_for(
                "cajero",
                msg=f"Retiro realizado. Nuevo saldo: Q{data['saldo']:.2f}",
                ok="1",
            )
        )
    return redirect(
        url_for("cajero", msg=data.get("error", "error desconocido"), ok="0")
    )


@app.route("/cajero/transferencia", methods=["POST"])
@requiere_rol("cajero")
def cajero_transferencia():
    body = {
        "cuenta_origen": int(request.form["cuenta_origen"]),
        "cuenta_destino": int(request.form["cuenta_destino"]),
        "monto": float(request.form["monto"]),
    }
    data = requests.post(
        f"{API_INTERNA}/transacciones/transferencia", json=body, timeout=5
    ).json()
    if data.get("ok"):
        return redirect(
            url_for("cajero", msg="Transferencia interna realizada", ok="1")
        )
    return redirect(
        url_for("cajero", msg=data.get("error", "error desconocido"), ok="0")
    )


@app.route("/cajero/interbancaria", methods=["POST"])
@requiere_rol("cajero")
def cajero_interbancaria():
    body = {
        "cuenta_origen": int(request.form["cuenta_origen"]),
        "banco_destino": request.form["banco_destino"],
        "cuenta_destino_remota": int(request.form["cuenta_destino_remota"]),
        "monto": float(request.form["monto"]),
    }
    data = requests.post(
        f"{API_INTERNA}/transacciones/interbancaria", json=body, timeout=8
    ).json()
    if data.get("ok"):
        return redirect(
            url_for("cajero", msg="Transferencia interbancaria enviada", ok="1")
        )
    return redirect(
        url_for("cajero", msg=data.get("error", "error desconocido"), ok="0")
    )


# ---------------------------------------------------------------------------
# Rol: analista
# ---------------------------------------------------------------------------
@app.route("/analista")
@requiere_rol("analista")
def analista():
    data = requests.get(f"{API_INTERNA}/dashboard/mercado", timeout=5).json()
    metricas = data.get("metricas", {})
    return render(
        """
    <div class="caja">
      <h3>Dashboard de mercado (simulado)</h3>
      <table>
        <tr><th>USD/GTQ</th><td>{{ metricas.get('usd_gtq') }}</td></tr>
        <tr><th>Tasa de interes referencia</th><td>{{ metricas.get('tasa_interes_referencia') }}%</td></tr>
        <tr><th>Indice de actividad</th><td>{{ metricas.get('indice_actividad') }}</td></tr>
        <tr><th>Actualizado</th><td>{{ metricas.get('actualizado') }}</td></tr>
      </table>
      <p><a href="{{ url_for('analista') }}">Refrescar</a></p>
    </div>
    """,
        metricas=metricas,
    )


# ---------------------------------------------------------------------------
# Rol: admin
# ---------------------------------------------------------------------------
@app.route("/admin")
@requiere_rol("admin")
def admin():
    usuarios = (
        requests.get(f"{API_INTERNA}/admin/usuarios", timeout=5)
        .json()
        .get("usuarios", [])
    )
    cuentas = (
        requests.get(f"{API_INTERNA}/admin/cuentas", timeout=5)
        .json()
        .get("cuentas", [])
    )
    blacklist_resp = requests.get(f"{API_INTERNA}/blacklist", timeout=5).json()
    blacklist_data = blacklist_resp.get("blacklist", {}) if blacklist_resp.get("ok") else {}

    blacklist_b4_resp = requests.get(
        f"{API_INTERNA}/blacklist/banco4", timeout=5
    ).json()
    blacklist_b4_data = (
        blacklist_b4_resp.get("blacklist", {})
        if blacklist_b4_resp.get("ok")
        else {}
    )
    return render(
        """
    <div class="caja">
      <h3>Usuarios</h3>
      <table>
        <tr><th>ID</th><th>Username</th><th>Nombre</th><th>Rol</th></tr>
        {% for u in usuarios %}
        <tr><td>{{ u['id'] }}</td><td>{{ u['username'] }}</td><td>{{ u['nombre_completo'] }}</td><td>{{ u['rol'] }}</td></tr>
        {% endfor %}
      </table>
    </div>
    <div class="caja">
      <h3>Cuentas</h3>
      <table>
        <tr><th>ID</th><th>Numero</th><th>Saldo</th><th>Titular</th></tr>
        {% for c in cuentas %}
        <tr><td>{{ c['id'] }}</td><td>{{ c['numero_cuenta'] }}</td><td>Q {{ '%.2f'|format(c['saldo']) }}</td><td>{{ c['nombre_completo'] or '-' }}</td></tr>
        {% endfor %}
      </table>
    </div>
    <div class="caja">
      <h3>Blacklist Banco 1</h3>
      {% if blacklist_data %}
        <p><strong>Total:</strong> {{ blacklist_data.total }}</p>
        <table>
          <tr><th>Nombre</th></tr>
          {% for nombre in blacklist_data.lista_negra_clientes %}
          <tr><td>{{ nombre }}</td></tr>
          {% endfor %}
        </table>
      {% else %}
        <p class="msg-error">No se pudo obtener la blacklist: {{ blacklist_resp.get('error', 'error desconocido') }}</p>
      {% endif %}
    </div>
    <div class="caja">
      <h3>Blacklist Banco 4</h3>
      {% if blacklist_b4_data %}
        <p><strong>Total:</strong> {{ blacklist_b4_data.total }}</p>
        <table>
          <tr><th>Nombre</th></tr>
          {% for nombre in blacklist_b4_data.lista_negra_clientes %}
          <tr><td>{{ nombre }}</td></tr>
          {% endfor %}
        </table>
      {% else %}
        <p class="msg-error">No se pudo obtener la blacklist: {{ blacklist_b4_resp.get('error', 'error desconocido') }}</p>
      {% endif %}
    </div>
    """,
        usuarios=usuarios,
        cuentas=cuentas,
        blacklist_data=blacklist_data,
        blacklist_resp=blacklist_resp,
        blacklist_b4_data=blacklist_b4_data,
        blacklist_b4_resp=blacklist_b4_resp,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, threaded=True, use_reloader=False)
