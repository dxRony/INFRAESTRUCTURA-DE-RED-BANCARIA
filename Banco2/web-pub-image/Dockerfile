FROM alpine:latest

RUN apk add --no-cache \
    python3 \
    py3-pip \
    iproute2 \
    curl

RUN pip install --no-cache-dir --break-system-packages flask requests

WORKDIR /opt/web
COPY webpub_app.py /opt/web/webpub_app.py
COPY web-entrypoint.sh /usr/local/bin/web-entrypoint.sh
RUN chmod +x /usr/local/bin/web-entrypoint.sh

CMD ["/usr/local/bin/web-entrypoint.sh"]
