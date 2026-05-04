FROM nginx:1.27-alpine
RUN apk add --no-cache bash
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY static/ /usr/share/nginx/html/
EXPOSE 8099
CMD ["/bin/sh", "-c", "envsubst '${AZTDP_INTERNAL_TOKEN}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && nginx -g 'daemon off;'"]
