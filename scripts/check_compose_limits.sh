#!/usr/bin/env bash
# scripts/check_compose_limits.sh - fail unless every service in the base compose
# file has a memory limit and a restart policy ("unless-stopped"; one-shot
# migration jobs must be "no"), and anomaly-service is pinned to one worker.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "python not found" >&2; exit 2; }

# The base file requires its secrets (${VAR:?}); this check only inspects limits,
# so supply throwaway placeholders for anything not already in the environment.
required_vars=(
  POSTGRES_PASSWORD REDIS_PASSWORD REDIS_PASSWORD_URLENCODED
  PG_OWNER_PASSWORD PG_INGEST_PASSWORD PG_FORENSICS_PASSWORD PG_GATEWAY_PASSWORD
  PG_ANOMALY_PASSWORD PG_DJANGO_PASSWORD PG_KEYCLOAK_PASSWORD
  AZTDP_INTERNAL_TOKEN AZTDP_SECRET_KEY AZTDP_STEPUP_SIGNING_KEY AZTDP_TOTP_MASTER_SECRET
  DASHBOARD_HTPASSWD KEYCLOAK_ADMIN_PASSWORD KEYCLOAK_CLIENT_SECRET GRAFANA_ADMIN_PASSWORD
  AZTDP_ALLOWED_HOSTS ALERT_WEBHOOK_URL AZTDP_MODEL_HMAC_KEY
)
for v in "${required_vars[@]}"; do
  [ -n "${!v:-}" ] || export "$v=placeholder-for-limits-check"
done

cfg=$(docker compose -f docker-compose.yml config --format json 2>/dev/null)
bad=$(printf '%s' "$cfg" | "$PY" -c "
import json,sys
cfg=json.load(sys.stdin); bad=[]
ONESHOT={'db-migrate','django-migrate'}
for name,svc in cfg['services'].items():
    lim=((svc.get('deploy') or {}).get('resources') or {}).get('limits') or {}
    if not (svc.get('mem_limit') or lim.get('memory')):
        bad.append(f'{name}: no memory limit')
    want='no' if name in ONESHOT else 'unless-stopped'
    if svc.get('restart')!=want:
        bad.append(f\"{name}: restart={svc.get('restart')!r}, want {want!r}\")
a=cfg['services'].get('anomaly-service',{}).get('environment',{})
if str(a.get('UVICORN_WORKERS'))!='1':
    bad.append('anomaly-service: UVICORN_WORKERS must be pinned to 1 (in-process model + scheduler)')
print('\n'.join(bad))" | tr -d '\r')
[ -z "$bad" ] || { echo "Compose limit violations:"; echo "$bad"; exit 1; }
echo "compose limits OK"
