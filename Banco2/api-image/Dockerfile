FROM alpine:latest

RUN apk add --no-cache \
    python3 \
    py3-pip \
    iproute2 \
    curl \
    mariadb-client

RUN pip install --no-cache-dir --break-system-packages flask pymysql requests

WORKDIR /opt/api
COPY app.py /opt/api/app.py
COPY api-entrypoint.sh /usr/local/bin/api-entrypoint.sh
RUN chmod +x /usr/local/bin/api-entrypoint.sh

CMD ["/usr/local/bin/api-entrypoint.sh"]
