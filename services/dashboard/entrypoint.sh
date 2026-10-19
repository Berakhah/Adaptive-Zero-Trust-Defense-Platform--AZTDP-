#!/bin/sh
# Render nginx config and the basic-auth htpasswd from environment secrets.
# Fail closed: refuse to start without the token or the htpasswd entry.
set -eu
: "${AZTDP_INTERNAL_TOKEN:?AZTDP_INTERNAL_TOKEN not set}"
: "${DASHBOARD_HTPASSWD:?DASHBOARD_HTPASSWD not set (full htpasswd line, e.g. from: openssl passwd -apr1)}"
umask 077
printf '%s\n' "$DASHBOARD_HTPASSWD" > /etc/nginx/htpasswd
chmod 644 /etc/nginx/htpasswd
envsubst '${AZTDP_INTERNAL_TOKEN}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf
exec nginx -g 'daemon off;'
