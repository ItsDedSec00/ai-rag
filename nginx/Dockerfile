# RAG-Chat — © 2026 David Dülle
# https://duelle.org
FROM nginx:alpine
RUN apk add --no-cache apache2-utils
COPY nginx.conf /etc/nginx/nginx.conf
COPY 99-htpasswd-init.sh /docker-entrypoint.d/99-htpasswd-init.sh
RUN sed -i 's/\r//' /docker-entrypoint.d/99-htpasswd-init.sh \
 && chmod +x /docker-entrypoint.d/99-htpasswd-init.sh
