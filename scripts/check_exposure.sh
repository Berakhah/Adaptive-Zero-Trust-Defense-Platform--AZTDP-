#!/usr/bin/env bash
# scripts/check_exposure.sh - fail if the base compose file publishes anything except ingress.
# Allowed host ports: nginx 80/443/8443/3443 and 9443 (SOC dashboard behind nginx TLS).
set -euo pipefail
cd "$(dirname "$0")/.."

PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "python not found" >&2; exit 2; }

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
