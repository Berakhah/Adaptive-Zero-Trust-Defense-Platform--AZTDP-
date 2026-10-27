#!/usr/bin/env bash
# scripts/run_tests.sh — run pytest once per service (the `tests` package name
# collides across services, so a single root invocation cannot collect them).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICES=("$@")
[ ${#SERVICES[@]} -eq 0 ] && SERVICES=(gateway risk-engine anomaly-service telemetry-ingest forensics django-app)
rc=0
for s in "${SERVICES[@]}"; do
  dir="$ROOT/services/$s"
  [ -d "$dir/tests" ] || { echo "!! $s has no tests/"; rc=1; continue; }
  echo "=== $s"
  (cd "$dir" && AZTDP_INTERNAL_TOKEN=test AZTDP_SECRET_KEY=test \
     python -m pytest -q --rootdir=. -p no:cacheprovider) || rc=1
done
exit $rc
