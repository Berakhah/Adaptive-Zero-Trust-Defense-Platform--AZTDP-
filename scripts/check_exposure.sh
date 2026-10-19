#!/usr/bin/env bash
# scripts/check_exposure.sh - fail if the base compose file publishes anything except ingress.
# Allowed host ports: nginx 80/443/8443/3443 and 9443 (SOC dashboard behind nginx TLS).
set -euo pipefail
cd "$(dirname "$0")/.."

PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "python not found" >&2; exit 2; }

# The base file requires its secrets (${VAR:?}); this check only inspects ports,
# so supply throwaway placeholders for anything not already in the environment.
required_vars=(
  POSTGRES_PASSWORD POSTGRES_PASSWORD_URLENCODED REDIS_PASSWORD REDIS_PASSWORD_URLENCODED
  AZTDP_INTERNAL_TOKEN AZTDP_SECRET_KEY AZTDP_STEPUP_SIGNING_KEY AZTDP_TOTP_MASTER_SECRET
  DASHBOARD_HTPASSWD KEYCLOAK_ADMIN_PASSWORD KEYCLOAK_CLIENT_SECRET GRAFANA_ADMIN_PASSWORD
  AZTDP_ALLOWED_HOSTS
)
for v in "${required_vars[@]}"; do
  [ -n "${!v:-}" ] || export "$v=placeholder-for-exposure-check"
done

cfg=$(docker compose -f docker-compose.yml config --format json 2>/dev/null)
bad=$(printf '%s' "$cfg" | "$PY" -c "
import json,sys,re
cfg=json.load(sys.stdin); bad=[]
for name,svc in cfg['services'].items():
    for p in svc.get('ports',[]) or []:
        pub=str(p.get('published',''))
        if not re.match(r'^(80|443|8443|3443|9443)$',pub): bad.append(f'{name}:{pub}')
print('\n'.join(bad))" | tr -d '\r')
[ -z "$bad" ] || { echo "Unexpected published ports:"; echo "$bad"; exit 1; }
echo "exposure OK"
