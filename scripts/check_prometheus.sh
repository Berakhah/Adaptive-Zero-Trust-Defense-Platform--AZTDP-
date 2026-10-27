#!/usr/bin/env bash
# scripts/check_prometheus.sh - validate Prometheus config/rules, run the rule unit
# tests, and validate the Alertmanager config. Requires Docker only.
set -euo pipefail
cd "$(dirname "$0")/.."

PROM_IMAGE=prom/prometheus:v2.53.0
AM_IMAGE=prom/alertmanager:v0.28.1

# Git Bash on Windows rewrites "/p"-style container paths and "$PWD" mounts; turn
# that off. Use a native-style host path when cygpath exists (Git Bash), else $PWD.
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
if command -v cygpath >/dev/null 2>&1; then ROOT=$(cygpath -m "$PWD"); else ROOT=$PWD; fi

promtool() {
  docker run --rm -v "$ROOT/infra/prometheus:/p:ro" --entrypoint promtool "$PROM_IMAGE" "$@"
}

promtool check config /p/prometheus.yml
promtool check rules /p/rules/aztdp.rules.yml
promtool test rules /p/rules/aztdp.rules.test.yml

# The webhook URL is read from a file at runtime (url_file), so the config itself
# is checkable as-is; the file only has to exist, so give amtool a dummy one.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
printf 'http://alert-sink.invalid/hook' > "$tmp/webhook_url"
if command -v cygpath >/dev/null 2>&1; then TMPM=$(cygpath -m "$tmp"); else TMPM=$tmp; fi
docker run --rm \
  -v "$ROOT/infra/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro" \
  -v "$TMPM/webhook_url:/run/secrets/alert_webhook_url:ro" \
  --entrypoint amtool "$AM_IMAGE" check-config /etc/alertmanager/alertmanager.yml
