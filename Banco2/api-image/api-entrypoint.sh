#!/bin/sh
set -e

cd /opt/api
python3 app.py > /var/log/api.log 2>&1 &

echo "API interna escuchando en :5000 (WEB-PUB)"
echo "API interbancaria escuchando en :5001 (otros bancos)"
echo "Logs en /var/log/api.log"

# Importante: ceder el control a la shell interactiva para que GNS3
# pueda seguir usando la consola normalmente, igual que en DB-CORE.
exec /bin/sh
