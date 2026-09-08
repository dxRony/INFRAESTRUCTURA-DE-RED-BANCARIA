import threading
import random
from datetime import datetime
from decimal import Decimal

import pymysql
import requests
from flask import Flask, request, jsonify

# ---------------------------------------------------------------------------
# Configuracion - ajustar segun la topologia real
# ---------------------------------------------------------------------------
DB_HOST = "10.20.1.26"  # IP de DB-CORE (VLAN 30 - Servidores internos)
DB_USER = "api_banco"
DB_PASSWORD = "api"
DB_NAME = "banco2_core"

NOMBRE_BANCO = "Banco2"  # como se identifica este banco ante los demas

PUERTO_INTERNO = 5000  # habla con WEB-PUB (solo alcanzable desde la LAN interna)
PUERTO_INTERBANCO = 5001  # habla con otros bancos (expuesto hacia redes de transito)


# ---------------------------------------------------------------------------
# Adaptadores por banco vecino.
#
# El contrato ideal era uno solo para los 5 bancos (spec-comunicacion-
# interbancaria.md), pero en la practica cada quien implemento su endpoint
# receptor distinto. Cada funcion de aqui abajo sabe como hablarle a UN banco
# especifico: arma el request como ese banco lo espera, e interpreta su
# respuesta. Devuelve siempre (exito: bool, detalle: str).
# ---------------------------------------------------------------------------
def _enviar_a_banco1(cuenta_origen, cuenta_destino_remota, monto):
    """Contrato real de Banco 1 (confirmado por su equipo, no del spec grupal)."""
    url = "http://10.0.0.1:80/interbancaria"
    payload = {
        "cuenta_origen": str(cuenta_origen),
        "cuenta_destino": str(cuenta_destino_remota),
        "monto": monto,
    }
    resp = requests.post(url, json=payload, timeout=5)
    data = resp.json()
    codigo = data.get("codigo", "SIN_CODIGO")
    exito = resp.status_code == 200 and codigo == "TRANSFERENCIA_ACEPTADA"
    return exito, codigo


def _consultar_con_failover(banco, urls, parseador=None):
    """GET con failover sobre una lista de URLs (principal y respaldo/s).

    Prueba cada URL en orden; usa la primera que responda 2xx. Si todas
    fallan, lanza ConnectionError con el detalle de por que fallo cada una
    (timeout / sin conexion / codigo HTTP), para poder diagnosticar si el
    problema es de red, de ruta o del endpoint del banco.

    `parseador` (opcional) recibe (resp, contenido) y devuelve el dict que
    se expondra al front. Por defecto parsea JSON.
    """
    if parseador is None:
        parseador = lambda resp, contenido: resp.json()
    errores = []
    for url in urls:
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            return parseador(resp, resp.text)
        except requests.Timeout:
            errores.append(f"{url} (timeout)")
        except requests.ConnectionError as e:
            errores.append(f"{url} (sin conexion: {e})")
        except requests.HTTPError as e:
            errores.append(f"{url} (HTTP {e.response.status_code})")
        except ValueError as e:
            errores.append(f"{url} (contenido no valido: {e})")
        except requests.RequestException as e:
            errores.append(f"{url} (error: {e})")
    raise ConnectionError(" ---------------- ".join(
        f"blacklist {banco} no disponible en {len(urls)} intentos: {errores}"
    ))


def _obtener_blacklist_banco1():
    """Consulta la blacklist de Banco 1 con failover.

    Primero intenta la URL principal (cara oeste de B1, enlace B1-B2 directo).
    Si el enlace principal esta caido (failover de red), intenta la URL de
    respaldo (cara este de B1, 10.0.0.18, alcanzable dando la vuelta por el
    anillo). Solo si ambas fallan se reporta el error con detalle de cual
    fallo y por que.
    """
    return _consultar_con_failover("Banco 1", [
        "http://10.0.0.1:8080/api/blacklist",
        "http://10.0.0.18:8080/api/blacklist",
    ])


def _normalizar_blacklist_b4(resp, contenido):
    """Normaliza la respuesta de la blacklist de Banco 4 al formato estandar
    usado por la web: {'total': N, 'lista_negra_clientes': [nombres]}.

    Banco 4 devuelve la blacklist como texto plano (no JSON). Se parsea de
    forma tolerante: una lista (JSON), texto con un nombre por linea, o
    nombres separados por comas/saltos. La web solo necesita esa estructura.
    """
    nombres = []

    # 1. Si viene JSON (lista o dict con claves conocidas), tomarlo
    try:
        data = resp.json()
        if isinstance(data, list):
            nombres = [str(x).strip() for x in data]
        elif isinstance(data, dict):
            if isinstance(data.get("lista_negra_clientes"), list):
                nombres = [str(x).strip() for x in data["lista_negra_clientes"]]
            elif isinstance(data.get("blacklist"), list):
                nombres = [str(x).strip() for x in data["blacklist"]]
            elif isinstance(data.get("nombres"), list):
                nombres = [str(x).strip() for x in data["nombres"]]
    except ValueError:
        pass

    # 2. Si no se obtuvo nada, tratar el contenido como texto plano
    if not nombres and contenido:
        for linea in contenido.splitlines():
            for token in linea.replace("\t", ",").split(","):
                token = token.strip()
                if token:
                    nombres.append(token)

    # 3. Quitar duplicados conservando el orden
    vistos, unicos = set(), []
    for n in nombres:
        if n not in vistos:
            vistos.add(n)
            unicos.append(n)
            nombres = unicos

    return {"total": len(nombres), "lista_negra_clientes": nombres}


def _obtener_blacklist_banco4():
    """Consulta la blacklist de Banco 4 con failover.

    Primero intenta la URL principal (cara oeste de B4, 10.0.0.10, por la
    ruta E2E via B3). Si falla, intenta la URL de respaldo (cara este de B4,
    10.0.0.13, alcanzable dando la vuelta por el anillo). Solo si ambas
    fallan se reporta el error con detalle.
    """
    return _consultar_con_failover(
        "Banco 4",
        [
            "http://10.0.0.10:8080/blacklist",
            "http://10.0.0.13:8080/blacklist",
        ],
        parseador=_normalizar_blacklist_b4,
    )


# Banco 3 aun no ha compartido su contrato real - usamos el del spec grupal
# como placeholder hasta que confirmen. AJUSTAR cuando lo definan.
def _enviar_a_banco3(cuenta_origen, cuenta_destino_remota, monto):
    url = (
        "http://10.0.0.6:5001/interbanco/deposito"  # PENDIENTE confirmar IP/puerto real
    )
    payload = {
        "cuenta_destino": cuenta_destino_remota,
        "monto": monto,
        "banco_origen": NOMBRE_BANCO,
    }
    resp = requests.post(url, json=payload, timeout=5)
    data = resp.json()
    exito = data.get("ok") is True
    return exito, data.get("error", "ok") if not exito else "ok"


BANCOS_VECINOS = {
    "Banco1": _enviar_a_banco1,
    "Banco3": _enviar_a_banco3,
}


def get_conn():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def sin_decimales(filas):
    """MariaDB devuelve DECIMAL como Decimal, y el JSONEncoder de Flask lo
    serializa como string en vez de numero. Convertimos a float antes de
    responder para que el lado que consume la API (WEB-PUB) reciba numeros
    reales, no texto."""
    for fila in filas:
        for clave, valor in fila.items():
            if isinstance(valor, Decimal):
                fila[clave] = float(valor)
    return filas


# ---------------------------------------------------------------------------
# API interna - consumida por WEB-PUB
# ---------------------------------------------------------------------------
app_interno = Flask("api_interna")


@app_interno.post("/login")
def login():
    data = request.get_json(force=True)
    username = data.get("username")
    password = data.get("password")
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, nombre_completo, rol FROM usuarios WHERE username=%s AND password=%s",
            (username, password),
        )
        usuario = cur.fetchone()
    conn.close()
    if not usuario:
        return jsonify(ok=False, error="credenciales invalidas"), 401
    return jsonify(ok=True, usuario=usuario)


@app_interno.get("/cuentas/<int:usuario_id>")
def cuentas_de_usuario(usuario_id):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, numero_cuenta, saldo FROM cuentas WHERE usuario_id=%s",
            (usuario_id,),
        )
        cuentas = sin_decimales(cur.fetchall())
    conn.close()
    return jsonify(ok=True, cuentas=cuentas)


@app_interno.get("/cuentas/<int:cuenta_id>/movimientos")
def movimientos(cuenta_id):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, tipo, cuenta_origen_id, cuenta_destino_id, banco_contraparte, monto, fecha
               FROM transacciones
               WHERE cuenta_origen_id=%s OR cuenta_destino_id=%s
               ORDER BY fecha DESC""",
            (cuenta_id, cuenta_id),
        )
        movimientos = sin_decimales(cur.fetchall())
    conn.close()
    return jsonify(ok=True, movimientos=movimientos)


@app_interno.post("/transacciones/deposito")
def deposito():
    data = request.get_json(force=True)
    cuenta_id = data.get("cuenta_id")
    monto = data.get("monto")
    if not cuenta_id or not monto or monto <= 0:
        return jsonify(ok=False, error="datos invalidos"), 400

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE cuentas SET saldo = saldo + %s WHERE id=%s", (monto, cuenta_id)
        )
        if cur.rowcount == 0:
            conn.close()
            return jsonify(ok=False, error="cuenta no encontrada"), 404
        cur.execute(
            "INSERT INTO transacciones (tipo, cuenta_destino_id, monto) VALUES ('deposito', %s, %s)",
            (cuenta_id, monto),
        )
        cur.execute("SELECT saldo FROM cuentas WHERE id=%s", (cuenta_id,))
        saldo = cur.fetchone()["saldo"]
    conn.close()
    return jsonify(ok=True, saldo=float(saldo))


@app_interno.post("/transacciones/retiro")
def retiro():
    data = request.get_json(force=True)
    cuenta_id = data.get("cuenta_id")
    monto = data.get("monto")
    if not cuenta_id or not monto or monto <= 0:
        return jsonify(ok=False, error="datos invalidos"), 400

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT saldo FROM cuentas WHERE id=%s FOR UPDATE", (cuenta_id,))
        cuenta = cur.fetchone()
        if not cuenta:
            conn.close()
            return jsonify(ok=False, error="cuenta no encontrada"), 404
        if cuenta["saldo"] < monto:
            conn.close()
            return jsonify(ok=False, error="fondos insuficientes"), 400

        cur.execute(
            "UPDATE cuentas SET saldo = saldo - %s WHERE id=%s", (monto, cuenta_id)
        )
        cur.execute(
            "INSERT INTO transacciones (tipo, cuenta_origen_id, monto) VALUES ('retiro', %s, %s)",
            (cuenta_id, monto),
        )
        cur.execute("SELECT saldo FROM cuentas WHERE id=%s", (cuenta_id,))
        saldo = cur.fetchone()["saldo"]
    conn.close()
    return jsonify(ok=True, saldo=float(saldo))


@app_interno.post("/transacciones/transferencia")
def transferencia_interna():
    data = request.get_json(force=True)
    origen = data.get("cuenta_origen")
    destino = data.get("cuenta_destino")
    monto = data.get("monto")
    if not origen or not destino or not monto or monto <= 0:
        return jsonify(ok=False, error="datos invalidos"), 400

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT saldo FROM cuentas WHERE id=%s FOR UPDATE", (origen,))
        cuenta_origen = cur.fetchone()
        if not cuenta_origen:
            conn.close()
            return jsonify(ok=False, error="cuenta origen no encontrada"), 404
        if cuenta_origen["saldo"] < monto:
            conn.close()
            return jsonify(ok=False, error="fondos insuficientes"), 400

        cur.execute("SELECT id FROM cuentas WHERE id=%s", (destino,))
        if not cur.fetchone():
            conn.close()
            return jsonify(ok=False, error="cuenta destino no encontrada"), 404

        cur.execute(
            "UPDATE cuentas SET saldo = saldo - %s WHERE id=%s", (monto, origen)
        )
        cur.execute(
            "UPDATE cuentas SET saldo = saldo + %s WHERE id=%s", (monto, destino)
        )
        cur.execute(
            """INSERT INTO transacciones (tipo, cuenta_origen_id, cuenta_destino_id, monto)
               VALUES ('transferencia_interna', %s, %s, %s)""",
            (origen, destino, monto),
        )
    conn.close()
    return jsonify(ok=True)


@app_interno.post("/transacciones/interbancaria")
def transferencia_interbancaria():
    """El cajero envia dinero desde una cuenta propia hacia otro banco."""
    data = request.get_json(force=True)
    cuenta_origen = data.get("cuenta_origen")
    banco_destino = data.get("banco_destino")  # ej. "Banco1"
    cuenta_destino_remota = data.get(
        "cuenta_destino_remota"
    )  # id local en el OTRO banco
    monto = data.get("monto")

    if banco_destino not in BANCOS_VECINOS:
        return jsonify(ok=False, error="banco destino desconocido"), 400
    if not cuenta_origen or not cuenta_destino_remota or not monto or monto <= 0:
        return jsonify(ok=False, error="datos invalidos"), 400

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT saldo FROM cuentas WHERE id=%s FOR UPDATE", (cuenta_origen,)
        )
        cuenta = cur.fetchone()
        if not cuenta:
            conn.close()
            return jsonify(ok=False, error="cuenta origen no encontrada"), 404
        if cuenta["saldo"] < monto:
            conn.close()
            return jsonify(ok=False, error="fondos insuficientes"), 400

        # 1. Debitar primero, localmente (regla del contrato del grupo)
        cur.execute(
            "UPDATE cuentas SET saldo = saldo - %s WHERE id=%s", (monto, cuenta_origen)
        )
    conn.close()

    # 2. Avisar al banco destino, usando el adaptador de ESE banco especifico
    #    (cada banco puede tener un contrato distinto de recepcion)
    try:
        exito, detalle = BANCOS_VECINOS[banco_destino](
            cuenta_origen, cuenta_destino_remota, monto
        )
    except requests.RequestException:
        exito, detalle = False, "banco destino no responde"

    conn = get_conn()
    with conn.cursor() as cur:
        if exito:
            cur.execute(
                """INSERT INTO transacciones (tipo, cuenta_origen_id, banco_contraparte, monto)
                   VALUES ('interbancaria_enviada', %s, %s, %s)""",
                (cuenta_origen, banco_destino, monto),
            )
            conn.close()
            return jsonify(ok=True)

        # 3. Revertir el debito si el banco destino rechazo o no respondio
        cur.execute(
            "UPDATE cuentas SET saldo = saldo + %s WHERE id=%s", (monto, cuenta_origen)
        )
    conn.close()
    return jsonify(ok=False, error=detalle), 400


@app_interno.get("/dashboard/mercado")
def dashboard_mercado():
    # Metricas simuladas para el rol analista - no hay feed de mercado real
    metricas = {
        "usd_gtq": round(random.uniform(7.6, 7.9), 4),
        "tasa_interes_referencia": round(random.uniform(4.5, 6.0), 2),
        "indice_actividad": round(random.uniform(90, 110), 1),
        "actualizado": datetime.now().isoformat(),
    }
    return jsonify(ok=True, metricas=metricas)


@app_interno.get("/blacklist")
def blacklist():
    """Devuelve la blacklist de Banco 1 (consultada via IP de transito)."""
    try:
        data = _obtener_blacklist_banco1()
        return jsonify(ok=True, blacklist=data)
    except ConnectionError as e:
        return jsonify(ok=False, error=str(e)), 502
    except requests.RequestException as e:
        return jsonify(ok=False, error=f"banco 1 no responde: {e}"), 502


@app_interno.get("/blacklist/banco4")
def blacklist_banco4():
    """Devuelve la blacklist de Banco 4 (consultada via IP de transito)."""
    try:
        data = _obtener_blacklist_banco4()
        return jsonify(ok=True, blacklist=data)
    except ConnectionError as e:
        return jsonify(ok=False, error=str(e)), 502
    except requests.RequestException as e:
        return jsonify(ok=False, error=f"banco 4 no responde: {e}"), 502


@app_interno.get("/admin/usuarios")
def admin_usuarios():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, username, nombre_completo, rol FROM usuarios")
        usuarios = cur.fetchall()
    conn.close()
    return jsonify(ok=True, usuarios=usuarios)


@app_interno.get("/admin/cuentas")
def admin_cuentas():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.id, c.numero_cuenta, c.saldo, u.username, u.nombre_completo
               FROM cuentas c LEFT JOIN usuarios u ON u.id = c.usuario_id"""
        )
        cuentas = sin_decimales(cur.fetchall())
    conn.close()
    return jsonify(ok=True, cuentas=cuentas)


@app_interno.get("/health")
def health_interno():
    return jsonify(ok=True, servicio="api-interna")


# ---------------------------------------------------------------------------
# API interbancaria - contrato fijo definido por el grupo (spec-comunicacion)
# ---------------------------------------------------------------------------
app_interbanco = Flask("api_interbanco")


@app_interbanco.post("/interbanco/deposito")
def recibir_deposito():
    data = request.get_json(force=True)
    cuenta_destino = data.get("cuenta_destino")
    monto = data.get("monto")
    banco_origen = data.get("banco_origen", "desconocido")

    if not monto or monto <= 0:
        return jsonify(ok=False, error="monto invalido"), 400

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM cuentas WHERE id=%s", (cuenta_destino,))
        if not cur.fetchone():
            conn.close()
            return jsonify(ok=False, error="cuenta no encontrada"), 404

        cur.execute(
            "UPDATE cuentas SET saldo = saldo + %s WHERE id=%s", (monto, cuenta_destino)
        )
        cur.execute(
            """INSERT INTO transacciones (tipo, cuenta_destino_id, banco_contraparte, monto)
               VALUES ('interbancaria_recibida', %s, %s, %s)""",
            (cuenta_destino, banco_origen, monto),
        )
        cur.execute("SELECT saldo FROM cuentas WHERE id=%s", (cuenta_destino,))
        saldo = cur.fetchone()["saldo"]
    conn.close()
    return jsonify(ok=True, saldo=float(saldo))


@app_interbanco.get("/health")
def health_interbanco():
    return jsonify(ok=True, servicio="api-interbancaria")


# ---------------------------------------------------------------------------
# Arranque: cada Flask app en su propio hilo/puerto
# ---------------------------------------------------------------------------
def correr(app, puerto):
    app.run(host="0.0.0.0", port=puerto, threaded=True, use_reloader=False)


if __name__ == "__main__":
    hilo_interno = threading.Thread(
        target=correr, args=(app_interno, PUERTO_INTERNO), daemon=True
    )
    hilo_interbanco = threading.Thread(
        target=correr, args=(app_interbanco, PUERTO_INTERBANCO), daemon=True
    )
    hilo_interno.start()
    hilo_interbanco.start()
    hilo_interno.join()
    hilo_interbanco.join()
