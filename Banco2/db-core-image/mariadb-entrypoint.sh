#!/bin/sh
set -e

mkdir -p /run/mysqld
chown mysql:mysql /run/mysqld

if [ ! -d /var/lib/mysql/mysql ]; then
    mariadb-install-db --user=mysql --datadir=/var/lib/mysql
fi

sed -i 's/^skip-networking/#skip-networking/' /etc/my.cnf.d/mariadb-server.cnf

/usr/bin/mysqld_safe --user=mysql &

for i in $(seq 1 15); do
    mysqladmin ping >/dev/null 2>&1 && break
    sleep 1
done

# ---------------------------------------------------------------------------
# Esquema banco2_core (version simple, pensada para demo de redes)
# ---------------------------------------------------------------------------
mysql -u root <<'SQL'
CREATE DATABASE IF NOT EXISTS banco2_core;
USE banco2_core;

-- usuarios: login de WEB-PUB. El rol define que puede hacer cada quien.
CREATE TABLE IF NOT EXISTS usuarios (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE,
    password        VARCHAR(100) NOT NULL,
    nombre_completo VARCHAR(100) NOT NULL,
    rol             ENUM('admin', 'cajero', 'analista', 'cliente') NOT NULL
);

-- cuentas: cada cuenta pertenece a un usuario con rol 'cliente'.
-- usuario_id puede ser NULL si quieren simular una cuenta sin dueno asignado aun.
CREATE TABLE IF NOT EXISTS cuentas (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id    INT NULL,
    numero_cuenta VARCHAR(20) NOT NULL UNIQUE,
    saldo         DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- transacciones: cubre uso interno (deposito/retiro/transferencia_interna)
-- e interbancario (interbancaria_enviada / interbancaria_recibida).
-- banco_contraparte guarda el nombre del otro banco (ej. 'Banco1'), tal
-- como llega en el campo "banco_origen" del contrato interbancario.
CREATE TABLE IF NOT EXISTS transacciones (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    tipo               ENUM(
                           'deposito',
                           'retiro',
                           'transferencia_interna',
                           'interbancaria_enviada',
                           'interbancaria_recibida'
                       ) NOT NULL,
    cuenta_origen_id   INT NULL,
    cuenta_destino_id  INT NULL,
    banco_contraparte  VARCHAR(30) NULL,
    monto              DECIMAL(12,2) NOT NULL,
    fecha              DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cuenta_origen_id)  REFERENCES cuentas(id),
    FOREIGN KEY (cuenta_destino_id) REFERENCES cuentas(id)
);

-- Usuario de administracion: se conecta desde PC-ADMIN (VLAN 10 - 10.20.1.16/29).
-- Privilegios completos, pensado para gestion manual de la BD (mysql client, backups, etc).
CREATE USER IF NOT EXISTS 'admin_banco'@'10.20.1.16/255.255.255.248' IDENTIFIED BY 'admin';
GRANT ALL PRIVILEGES ON banco2_core.* TO 'admin_banco'@'10.20.1.16/255.255.255.248';

-- Usuario de aplicacion: es el que usa la API (VLAN 40 - 10.20.1.32/29) para
-- leer/escribir datos. Sin privilegios administrativos (no puede crear
-- usuarios, tablas nuevas, etc), solo operar sobre los datos.
CREATE USER IF NOT EXISTS 'api_banco'@'10.20.1.32/255.255.255.248' IDENTIFIED BY 'api';
GRANT SELECT, INSERT, UPDATE, DELETE ON banco2_core.* TO 'api_banco'@'10.20.1.32/255.255.255.248';

FLUSH PRIVILEGES;
SQL

# ---------------------------------------------------------------------------
# Datos semilla (solo en el primer arranque)
# ---------------------------------------------------------------------------
COUNT=$(mysql -u root -N -B -e "SELECT COUNT(*) FROM banco2_core.usuarios;")
if [ "$COUNT" = "0" ]; then
mysql -u root banco2_core <<'SQL'
INSERT INTO usuarios (username, password, nombre_completo, rol) VALUES
    ('admin1',    'admin123',    'Admin Demo',    'admin'),
    ('cajero1',   'cajero123',   'Cajero Demo',   'cajero'),
    ('analista1', 'analista123', 'Analista Demo', 'analista'),
    ('cliente1',  'cliente123',  'Cliente Demo 1', 'cliente'),
    ('cliente2',  'cliente123',  'Cliente Demo 2', 'cliente');

INSERT INTO cuentas (usuario_id, numero_cuenta, saldo) VALUES
    ((SELECT id FROM usuarios WHERE username='cliente1'), '2001-0001-01', 15000.00),
    ((SELECT id FROM usuarios WHERE username='cliente2'), '2001-0002-01', 8500.50);
SQL
fi

# Importante: al terminar el setup, ceder el control a la shell interactiva
# para que GNS3 pueda seguir usando la consola normalmente
exec /bin/sh
