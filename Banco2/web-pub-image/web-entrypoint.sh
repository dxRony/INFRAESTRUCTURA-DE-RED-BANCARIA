#!/bin/sh
set -e

cd /opt/web
python3 webpub_app.py > /var/log/webpub.log 2>&1 &

echo "WEB-PUB escuchando en :80"
echo "Logs en /var/log/webpub.log"

# Importante: ceder el control a la shell interactiva para que GNS3
# pueda seguir usando la consola normalmente, igual que en DB-CORE y API.
exec /bin/sh
