# Anexos Técnicos — Banco 3 (Banca Digital / Fintech)

Índice de configuraciones, scripts y parámetros técnicos verificados en producción para el nodo Banco 3.

---

## 1. Enrutamiento y Conmutación (Cisco IOS)
- [`r1/running-config.txt`](r1/running-config.txt): Configuración activa del router R1 (Cisco 3745). Incluye direccionamiento IP, enrutamiento estático con IP SLA y tracking de interfaces, Local PBR para sondas, NAT dinámico con sobrecarga hacia Internet y enlaces interbancarios, y NAT estático de publicación.
- [`sw1/running-config.txt`](sw1/running-config.txt): Configuración activa del switch SW1 (Cisco IOSvL2). Incluye enlace troncal 802.1Q hacia FW1, segmentación en VLANs (10, 20, 30) y seguridad de capa 2 con Port Security sticky en puerto de usuario.

---

## 2. Cortafuegos Perimetral (Alpine Linux - FW1)
- [`fw1/interfaces`](fw1/interfaces): Configuración de red (/etc/network/interfaces) con subinterfaces 802.1Q para VLAN 10, 20 y 30, y enlace de tránsito hacia R1.
- [`fw1/nftables.nft`](fw1/nftables.nft): Conjunto de reglas de filtrado con políticas base DROP en INPUT y FORWARD, inspección de estado (conntrack), mínimo privilegio entre zonas y registro selectivo de descartes.
- [`fw1/blocked.txt`](fw1/blocked.txt): Listado de dominios sujetos a restricción perimetral de acceso.
- [`fw1/update-domains.sh`](fw1/update-domains.sh): Script de resolución y actualización dinámica de IPs de dominios bloqueados en el set de nftables.

---

## 3. Servidor Web y API (Alpine Linux - WEB01)
- [`web01/interfaces`](web01/interfaces): Configuración de red de WEB01 en la DMZ (VLAN 20, IP 172.16.2.2/29).
- [`web01/default.conf`](web01/default.conf): Configuración del servidor Nginx (puerto 80) que sirve el portal estático y actúa como proxy inverso hacia el backend Flask (puerto 5001).
- [`web01/index.html`](web01/index.html): Portal web de Banca Digital de Banco 3 con interfaz de usuario para consultas de saldo, transferencias locales e interbancarias.
- [`web01/interbanco_sanitized.py`](web01/interbanco_sanitized.py): Backend de transferencias y depósitos en Flask/Python. Implementa integración con Banco 1 mediante endpoints ordenados por prioridad de tránsito, validación de tipos y supresión de reintento ante timeout ambiguo para reducir el riesgo de acreditación duplicada. Credenciales de base de datos sanitizadas.

---

## 4. Servidor de Base de Datos (Alpine Linux - DB01)
- [`db01/interfaces`](db01/interfaces): Configuración de red de DB01 en segmento seguro (VLAN 30, IP 172.16.3.2/29).
- [`db01/postgresql.conf`](db01/postgresql.conf): Extracto de parámetros activos del motor PostgreSQL (listen_addresses, memoria y sockets).
- [`db01/pg_hba-sanitized.conf`](db01/pg_hba-sanitized.conf): Archivo de control de acceso de clientes (pg_hba.conf). Restringe conexiones remotas exclusivamente al servidor web WEB01 (172.16.2.2/32) mediante autenticación scram-sha-256.

---

## 5. Estaciones de Usuario (PC-USR)
- [`clientes/pc-usr.interfaces`](clientes/pc-usr.interfaces): Configuración de red de la estación de trabajo en VLAN 10 (IP 172.16.1.2/24).

---

## 6. Documentación Formal
- [`documentacion/Banco3.pdf`](documentacion/Banco3.pdf): Informe formal individual completo de Banco 3 (Banca Digital / Fintech). Incluye diseño de arquitectura, direccionamiento, VLANs, routing estático, NAT/PAT, políticas de firewall nftables, control de dominios, port security, pruebas de conectividad y análisis protocolar.
- [`documentacion/Infraestructura de red-Banco 3.drawio.png`](documentacion/Infraestructura%20de%20red-Banco%203.drawio.png): Diagrama esquemático oficial de la topología de red individual e interbancaria.

