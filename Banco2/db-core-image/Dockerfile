FROM alpine:latest

RUN apk add --no-cache mariadb mariadb-client iproute2

COPY mariadb-entrypoint.sh /usr/local/bin/mariadb-entrypoint.sh

RUN chmod +x /usr/local/bin/mariadb-entrypoint.sh

CMD ["/usr/local/bin/mariadb-entrypoint.sh"]
