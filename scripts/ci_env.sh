#!/usr/bin/env bash
# scripts/ci_env.sh - write a throwaway .env with random values for every blank key
# in .env.example, so CI (and anyone) can start the production-profile compose file
# without a committed secrets file.
#
#   bash scripts/ci_env.sh [OUTPUT]     # default OUTPUT: .env
#
# Refuses to overwrite an existing file: a real .env must never be clobbered.
# Keys that .env.example already gives a value (e.g. KEYCLOAK_ADMIN=admin) keep it.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-.env}"
if [ -e "$OUT" ]; then
  echo "refusing to overwrite existing $OUT" >&2
  exit 1
fi

PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "python not found" >&2; exit 2; }
command -v openssl >/dev/null 2>&1 || { echo "openssl not found" >&2; exit 2; }

rand() { openssl rand -hex 32; }
urlenc() { "$PY" -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }

REDIS_PASSWORD_VALUE="$(rand)"
HTPASSWD_HASH="$(openssl passwd -apr1 "$(rand)")"

: > "$OUT"
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    ''|'#'*) continue ;;
  esac
  key="${line%%=*}"
  val="${line#*=}"
  if [ -n "$val" ]; then
    printf '%s=%s\n' "$key" "$val" >> "$OUT"
    continue
  fi
  case "$key" in
    AZTDP_ALLOWED_HOSTS)        printf '%s=localhost,127.0.0.1\n' "$key" >> "$OUT" ;;
    REDIS_PASSWORD)             printf '%s=%s\n' "$key" "$REDIS_PASSWORD_VALUE" >> "$OUT" ;;
    REDIS_PASSWORD_URLENCODED)  printf '%s=%s\n' "$key" "$(urlenc "$REDIS_PASSWORD_VALUE")" >> "$OUT" ;;
    DASHBOARD_HTPASSWD)         printf "%s='soc:%s'\n" "$key" "$HTPASSWD_HASH" >> "$OUT" ;;
    ALERT_WEBHOOK_URL)          printf '%s=http://127.0.0.1:9/ci-null\n' "$key" >> "$OUT" ;;
    *)                          printf '%s=%s\n' "$key" "$(rand)" >> "$OUT" ;;
  esac
done < .env.example

echo "wrote $OUT ($(wc -l < "$OUT") keys)"
