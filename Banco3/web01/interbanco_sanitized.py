# ==========================================================
# BANCO 3 - SERVICIO BACKEND FLASK (INTERBANCO)
# Ubicacion en nodo WEB01: /opt/interbanco.py
# Servicio OpenRC: /etc/init.d/interbanco
# Estado: Verificado en vivo y operativo
# Sanitizacion: Credenciales de base de datos protegidas (<PASSWORD_SANITIZED>)
# Arquitectura: Supresion de reintento ante timeout ambiguo para reducir el riesgo de acreditacion duplicada
# ==========================================================
import json
import urllib.request
import urllib.error
import socket
from flask import Flask, request, jsonify
import psycopg2

app = Flask(__name__)

DB_CONFIG = {
    "host": "172.16.3.2",
    "dbname": "banca_digital",
    "user": "bancaweb",
    "password": "<PASSWORD_SANITIZED>",
}

BANCO1_ENDPOINTS = [
    {
        "url": "http://10.0.0.18:80/interbancaria",
        "nombre": "cara_este_10.0.0.18",
    },
    {
        "url": "http://10.0.0.1:80/interbancaria",
        "nombre": "cara_oeste_10.0.0.1",
    },
]


@app.post("/interbancaria")
def interbancaria():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify(ok=False, error="JSON invalido"), 400

    cuenta_origen = data.get("cuenta_origen")
    cuenta_destino = data.get("cuenta_destino")
    monto = data.get("monto")

    if cuenta_destino is None or monto is None:
        return jsonify(ok=False, error="Datos incompletos"), 400

    try:
        monto = float(monto)
        if monto <= 0:
            return jsonify(ok=False, error="El monto debe ser mayor a 0"), 400
    except (ValueError, TypeError):
        return jsonify(ok=False, error="Monto invalido"), 400

    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE cuentas
            SET saldo = saldo + %s
            WHERE id = %s
            RETURNING saldo
            """,
            (monto, cuenta_destino),
        )
        resultado = cur.fetchone()
        if resultado is None:
            conn.rollback()
            return jsonify(ok=False, error="Cuenta destino no encontrada"), 404

        nuevo_saldo = float(resultado[0])
        origen_info = str(data.get("banco_origen") or f"cta_{cuenta_origen}")[:20]

        cur.execute(
            """
            INSERT INTO transacciones
                (cuenta_id, tipo, monto, banco_origen)
            VALUES (%s, %s, %s, %s)
            """,
            (cuenta_destino, "interbanco", monto, origen_info),
        )
        conn.commit()
        return jsonify(
            ok=True,
            mensaje="Deposito interbancario recibido con exito",
            saldo=nuevo_saldo,
        ), 200
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify(ok=False, error=str(e)), 500
    finally:
        if conn:
            conn.close()


@app.post("/transferencia/interna")
def transferencia_interna():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify(ok=False, error="JSON invalido"), 400

    cuenta_origen = data.get("cuenta_origen")
    cuenta_destino = data.get("cuenta_destino")
    monto = data.get("monto")

    if cuenta_origen is None or cuenta_destino is None or monto is None:
        return jsonify(ok=False, error="Datos incompletos"), 400

    if cuenta_origen == cuenta_destino:
        return jsonify(ok=False, error="La cuenta origen y la cuenta destino no pueden ser iguales"), 400

    try:
        monto = float(monto)
        if monto <= 0:
            return jsonify(ok=False, error="El monto debe ser mayor a 0"), 400
    except (ValueError, TypeError):
        return jsonify(ok=False, error="Monto invalido"), 400

    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        ids = sorted([cuenta_origen, cuenta_destino])
        cur.execute(
            """
            SELECT id, saldo, titular
            FROM cuentas
            WHERE id IN (%s, %s)
            ORDER BY id
            FOR UPDATE
            """,
            (ids[0], ids[1]),
        )
        cuentas_db = {row[0]: row for row in cur.fetchall()}

        if cuenta_origen not in cuentas_db:
            conn.rollback()
            return jsonify(ok=False, error="Cuenta origen no encontrada"), 404
        if cuenta_destino not in cuentas_db:
            conn.rollback()
            return jsonify(ok=False, error="Cuenta destino no encontrada"), 404

        saldo_origen = float(cuentas_db[cuenta_origen][1])
        if saldo_origen < monto:
            conn.rollback()
            return jsonify(ok=False, error="Saldo insuficiente"), 400

        cur.execute(
            """
            UPDATE cuentas
            SET saldo = saldo - %s
            WHERE id = %s
            RETURNING saldo
            """,
            (monto, cuenta_origen),
        )
        nuevo_saldo_origen = float(cur.fetchone()[0])

        cur.execute(
            """
            UPDATE cuentas
            SET saldo = saldo + %s
            WHERE id = %s
            RETURNING saldo
            """,
            (monto, cuenta_destino),
        )
        nuevo_saldo_destino = float(cur.fetchone()[0])

        cur.execute(
            """
            INSERT INTO transacciones
                (cuenta_id, tipo, monto, banco_origen)
            VALUES (%s, %s, %s, %s)
            """,
            (cuenta_origen, "transf_interna", monto, "Banco3"),
        )
        cur.execute(
            """
            INSERT INTO transacciones
                (cuenta_id, tipo, monto, banco_origen)
            VALUES (%s, %s, %s, %s)
            """,
            (cuenta_destino, "transf_interna", monto, "Banco3"),
        )
        conn.commit()
        return jsonify(
            ok=True,
            mensaje="Transferencia interna exitosa",
            saldo_origen=nuevo_saldo_origen,
            saldo_destino=nuevo_saldo_destino,
        ), 200
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify(ok=False, error=str(e)), 500
    finally:
        if conn:
            conn.close()


@app.post("/transferencia/banco1")
def transferencia_banco1():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify(ok=False, error="JSON invalido"), 400

    cuenta_origen = data.get("cuenta_origen")
    cuenta_destino = data.get("cuenta_destino")
    monto = data.get("monto")

    if cuenta_origen is None or cuenta_destino is None or monto is None:
        return jsonify(ok=False, error="Datos incompletos"), 400

    try:
        monto = float(monto)
        if monto <= 0:
            return jsonify(ok=False, error="El monto debe ser mayor a 0"), 400
    except (ValueError, TypeError):
        return jsonify(ok=False, error="Monto invalido"), 400

    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute(
            """
            SELECT saldo, titular
            FROM cuentas
            WHERE id = %s
            FOR UPDATE
            """,
            (cuenta_origen,),
        )
        cuenta = cur.fetchone()

        if cuenta is None:
            conn.rollback()
            return jsonify(ok=False, error="Cuenta origen no encontrada"), 404

        saldo_actual = float(cuenta[0])
        if saldo_actual < monto:
            conn.rollback()
            return jsonify(ok=False, error="Saldo insuficiente"), 400

        cur.execute(
            """
            UPDATE cuentas
            SET saldo = saldo - %s
            WHERE id = %s
            RETURNING saldo
            """,
            (monto, cuenta_origen),
        )
        nuevo_saldo = float(cur.fetchone()[0])

        payload = {
            "cuenta_origen": int(cuenta_origen),
            "cuenta_destino": int(cuenta_destino),
            "monto": float(monto),
            "banco_origen": "Banco3",
        }
        req_body = json.dumps(payload).encode("utf-8")

        transaccion_exitosa = False
        resp_data = {}
        ruta_usada = None
        ultimo_error_transporte = None

        for ep in BANCO1_ENDPOINTS:
            url = ep["url"]
            nombre_ruta = ep["nombre"]
            req = urllib.request.Request(
                url,
                data=req_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    status_code = response.getcode()
                    resp_text = response.read().decode("utf-8")
                    resp_data = json.loads(resp_text) if resp_text else {}

                    if status_code not in (200, 201):
                        conn.rollback()
                        return jsonify(
                            ok=False,
                            error=f"Banco 1 rechazo la transferencia ({nombre_ruta}, HTTP {status_code}): {resp_text}",
                        ), 502

                    if isinstance(resp_data, dict) and "ok" in resp_data and not resp_data["ok"]:
                        conn.rollback()
                        return jsonify(
                            ok=False,
                            error=f"Banco 1 rechazo la transferencia ({nombre_ruta}): {resp_data.get('error', 'Rechazada')}",
                        ), 502

                    transaccion_exitosa = True
                    ruta_usada = nombre_ruta
                    break
            except urllib.error.HTTPError as http_err:
                conn.rollback()
                err_body = http_err.read().decode("utf-8", errors="replace")
                try:
                    err_json = json.loads(err_body)
                    b1_msg = err_json.get("mensaje") or err_json.get("codigo") or err_body
                except Exception:
                    b1_msg = err_body
                return jsonify(
                    ok=False,
                    error=f"Banco 1 rechazo la transferencia ({nombre_ruta}, HTTP {http_err.code}): {b1_msg}",
                    detalle_banco1=err_body,
                ), 502
            except (urllib.error.URLError, socket.timeout, TimeoutError) as net_err:
                motivo = net_err.reason if hasattr(net_err, "reason") else str(net_err)
                ultimo_error_transporte = f"{nombre_ruta} ({url}): {motivo}"
                motivo_str = str(motivo).lower()
                es_fallo_previo_envio = any(s in motivo_str for s in ["connection refused", "network is unreachable", "no route to host"])
                if not es_fallo_previo_envio:
                    conn.rollback()
                    return jsonify(
                        ok=False,
                        error=f"Timeout de comunicacion con Banco 1 en {nombre_ruta}. No se reintento para evitar transferencias duplicadas.",
                        detalle=ultimo_error_transporte,
                    ), 504
                continue
            except Exception as other_err:
                conn.rollback()
                return jsonify(
                    ok=False,
                    error=f"Error inesperado en comunicacion con Banco 1: {str(other_err)}",
                ), 502

        if not transaccion_exitosa:
            conn.rollback()
            return jsonify(
                ok=False,
                error=f"Fallo de conexion en endpoints de Banco 1: {ultimo_error_transporte}",
            ), 504

        cur.execute(
            """
            INSERT INTO transacciones
                (cuenta_id, tipo, monto, banco_origen)
            VALUES (%s, %s, %s, %s)
            """,
            (cuenta_origen, "salida_interbanco", monto, "Banco3"),
        )
        conn.commit()
        return jsonify(
            ok=True,
            mensaje="Transferencia exitosa hacia Banco 1",
            saldo=nuevo_saldo,
            respuesta_banco1=resp_data,
            ruta=ruta_usada,
        ), 200
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify(ok=False, error=str(e)), 500
    finally:
        if conn:
            conn.close()


@app.get("/cuenta/<int:cuenta_id>")
def obtener_cuenta(cuenta_id):
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, titular, saldo
            FROM cuentas
            WHERE id = %s
            """,
            (cuenta_id,),
        )
        cuenta = cur.fetchone()

        if cuenta is None:
            return jsonify(ok=False, error="Cuenta no encontrada"), 404

        return jsonify(
            ok=True,
            cuenta={
                "id": cuenta[0],
                "titular": cuenta[1],
                "saldo": float(cuenta[2]),
            },
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500
    finally:
        if conn:
            conn.close()


app.run(host="0.0.0.0", port=5001)
