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
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Banco 2 - WEB-PUB</title>
  <style>
    * { box-sizing:border-box; margin:0; padding:0; }
    body {
      font-family:"DejaVu Sans", "Liberation Sans", Arial, sans-serif;
      background:#eef1f5; color:#22303c; line-height:1.5; padding:1rem;
    }
    .wrap { max-width:1000px; margin:0 auto; }
    .header {
      background:linear-gradient(100deg, #0d3b5f 0%, #1c6ea4 100%);
      color:#fff; border-radius:10px 10px 0 0;
      padding:1rem 1.4rem;
      display:flex; flex-wrap:wrap; align-items:center;
      justify-content:space-between;
    }
    .header h2 { font-size:1.25rem; font-weight:600; }
    .header .tagline { font-size:.8rem; opacity:.85; }
    .userbar { font-size:.9rem; }
    .userbar a { color:#cfe6f5; margin-left:1rem; }
    .userbar a:hover { color:#fff; text-decoration:underline; }
    .content {
      background:#fff;
      border:1px solid #e1e6ec; border-top:0;
      border-radius:0 0 10px 10px;
      padding:1.5rem;
      box-shadow:0 2px 6px rgba(0,0,0,.06);
    }
    .caja {
      background:#fbfcfe; border:1px solid #e4e9ef; border-radius:8px;
      padding:1.1rem 1.3rem; margin-bottom:1.2rem;
    }
    .caja h3 {
      color:#0d3b5f; font-size:1.02rem; margin-bottom:.7rem;
      padding-bottom:.45rem; border-bottom:1px solid #eef1f5;
    }
    label { display:block; font-size:.83rem; color:#4a5a6a; margin:.75rem 0 .25rem; }
    input, select {
      display:block; width:100%; max-width:340px;
      padding:.5rem .6rem; font-size:.93rem;
      border:1px solid #c9d3dd; border-radius:6px; background:#fff;
    }
    input:focus, select:focus { border-color:#1c6ea4; outline:1px solid #9fc7e0; }
    button {
      margin-top:1rem; padding:.55rem 1.4rem; cursor:pointer;
      background:#1c6ea4; color:#fff; border:0; border-radius:6px; font-size:.93rem;
    }
    button:hover { background:#0d3b5f; }
    button.danger { background:#b03a3a; }
    button.danger:hover { background:#8a2b2b; }
    button.secundario { background:#8a97a5; }
    button.secundario:hover { background:#6f7d8c; }
    table { border-collapse:collapse; width:100%; margin-top:.4rem; background:#fff; }
    th {
      background:#0d3b5f; color:#fff; text-align:left;
      padding:.5rem .7rem; font-size:.83rem; font-weight:600;
    }
    td { padding:.5rem .7rem; border-bottom:1px solid #eef1f5; font-size:.9rem; }
    tr:nth-child(even) td { background:#f7f9fb; }
    td.der, th.der { text-align:right; }
    a { color:#1c6ea4; text-decoration:none; }
    a:hover { text-decoration:underline; }
    .volver { display:inline-block; margin-top:1rem; font-size:.9rem; }
    .msg-ok, .msg-error {
      padding:.7rem 1rem; border-radius:6px; margin-bottom:1rem; font-size:.9rem;
    }
    .msg-ok { background:#e8f6ec; color:#1e6a35; border:1px solid #bfe6c9; }
    .msg-error { background:#fdecea; color:#a12c2c; border:1px solid #f3c6c2; }
    .centrado { max-width:440px; margin:2rem auto; }
    .grid-2 { display:flex; flex-wrap:wrap; margin:-.6rem; }
    .grid-2 > * { flex:1 1 280px; margin:.6rem; min-width:0; }
    .vacio { color:#8a97a5; font-style:italic; padding:.4rem 0; }
    @media (max-width:640px) {
      .header { flex-direction:column; text-align:center; }
      .userbar { margin-top:.5rem; }
      .userbar a { margin:0 .5rem; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <div>
        <h2>Banco 2 &mdash; Banca de Inversion</h2>
        <span class="tagline">Portal WEB-PUB</span>
      </div>
      {% if session.get('usuario') %}
        <nav class="userbar">
          <span>{{ session['usuario']['nombre_completo'] }} ({{ session['usuario']['rol'] }})</span>
          <a href="{{ url_for('logout') }}">Cerrar sesion</a>
        </nav>
      {% endif %}
    </div>
    <div class="content">
      {% if msg %}
        <p class="{{ 'msg-ok' if ok else 'msg-error' }}">{{ msg }}</p>
      {% endif %}
      {{ contenido | safe }}
    </div>
  </div>
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
    <div class="caja centrado">
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
    <div class="grid-2">
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
          <button type="submit" class="danger">Retirar</button>
        </form>
      </div>
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
    <div class="grid-2">
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
          <tr><th>ID</th><th>Numero</th><th class="der">Saldo</th><th>Titular</th></tr>
          {% for c in cuentas %}
          <tr><td>{{ c['id'] }}</td><td>{{ c['numero_cuenta'] }}</td><td class="der">Q {{ '%.2f'|format(c['saldo']) }}</td><td>{{ c['nombre_completo'] or '-' }}</td></tr>
          {% endfor %}
        </table>
      </div>
    </div>
    <div class="grid-2">
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
