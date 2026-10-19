#!/usr/bin/env bash
# scripts/backup/pg_restore_test.sh - end-to-end proof that a backup can be restored.
#
# Brings up an isolated compose project (postgres + db-migrate + pg-backup), seeds
# data, takes an on-demand backup, restores the newest backup set from the
# pg_backups volume into a throwaway postgres container (no network, tmpfs data),
# and compares source vs restored: row counts (token_revocations, audit_events),
# triggers, table ownership, roles, and that the audit_events immutability
# trigger is still ENFORCED after the restore. Exits non-zero on any mismatch.
# Everything it creates (containers, volumes, network) is removed on exit.
#
#   bash scripts/backup/pg_restore_test.sh
#   COMPOSE_PROJECT_NAME=other COMPOSE_ENV_FILES=.env.dev bash scripts/backup/pg_restore_test.sh
#
# Never publishes host ports (base compose file only; no dev port override).
set -euo pipefail
cd "$(dirname "$0")/../.."

export MSYS_NO_PATHCONV=1   # git-bash on Windows: do not rewrite /backups style args
: "${COMPOSE_PROJECT_NAME:=aztdp_restore_test}"
: "${COMPOSE_ENV_FILES:=.env.dev}"
export COMPOSE_PROJECT_NAME COMPOSE_ENV_FILES
DC=(docker compose)

SCRATCH="${COMPOSE_PROJECT_NAME}_restore_$$"
IMAGE=$(sed -n 's/^FROM[[:space:]]\{1,\}\(postgres:[^[:space:]]*\).*/\1/p' infra/pg-backup/Dockerfile 2>/dev/null | head -1 || true)
IMAGE=${IMAGE:-postgres:16-alpine}

fails=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; fails=$((fails + 1)); }

cleanup() {
  docker rm -f "$SCRATCH" >/dev/null 2>&1 || true
  "${DC[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

src() { "${DC[@]}" exec -T postgres psql -X -q -t -A -v ON_ERROR_STOP=1 -U "$1" -d "$2" -c "$3" 2>&1 | tr -d '\r'; }
dst() { docker exec "$SCRATCH" psql -X -q -t -A -v ON_ERROR_STOP=1 -U "$1" -d "$2" -c "$3" 2>&1 | tr -d '\r'; }

echo "== bring up isolated project $COMPOSE_PROJECT_NAME"
"${DC[@]}" up -d --build --wait postgres pg-backup >/dev/null || { fail "could not start postgres + pg-backup"; exit 1; }
"${DC[@]}" up --no-deps db-migrate >/dev/null 2>&1 || { fail "db-migrate failed"; exit 1; }

echo "== seed source data"
src aztdp_ingest aztdp "INSERT INTO audit_events(event_id,event_type,service) SELECT gen_random_uuid(),'risk_eval','restore-test' FROM generate_series(1,25)" >/dev/null
src aztdp_gateway aztdp "INSERT INTO token_revocations(token_jti_hash,reason,source) SELECT 'restore-test-'||g,'admin','admin' FROM generate_series(1,10) g ON CONFLICT DO NOTHING" >/dev/null

echo "== on-demand backup"
"${DC[@]}" exec -T pg-backup /backup.sh

SRC_AUDIT=$(src aztdp aztdp "SELECT count(*) FROM audit_events")
SRC_TOK=$(src aztdp aztdp "SELECT count(*) FROM token_revocations")
fp_trg="SELECT md5(string_agg(tgrelid::regclass||':'||tgname, ',' ORDER BY tgrelid::regclass::text, tgname)) FROM pg_trigger WHERE NOT tgisinternal"
fp_own="SELECT md5(string_agg(c.relname||':'||pg_get_userbyid(c.relowner), ',' ORDER BY c.relname)) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','S')"
fp_role="SELECT string_agg(rolname, ',' ORDER BY rolname) FROM pg_roles WHERE rolname LIKE 'aztdp%' OR rolname='keycloak'"
fp_ntrg="SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'audit_events_immutable%'"
SRC_TRG=$(src aztdp aztdp "$fp_trg"); SRC_OWN=$(src aztdp aztdp "$fp_own"); SRC_ROLE=$(src aztdp aztdp "$fp_role")
SRC_NTRG=$(src aztdp aztdp "$fp_ntrg")
echo "source: audit_events=$SRC_AUDIT token_revocations=$SRC_TOK immutability_triggers=$SRC_NTRG"
if ! { [ "${SRC_AUDIT:-0}" -gt 0 ] && [ "${SRC_TOK:-0}" -gt 0 ] && [ "${SRC_NTRG:-0}" -gt 0 ]; } 2>/dev/null; then
  fail "source tables empty or triggers missing - test would be vacuous"; exit 1
fi

echo "== restore newest backup set into throwaway container $SCRATCH"
VOL="${COMPOSE_PROJECT_NAME}_pg_backups"
docker run -d --name "$SCRATCH" --network none --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_USER=aztdp -e POSTGRES_DB=postgres -e POSTGRES_PASSWORD="throwaway-$RANDOM$RANDOM" \
  -v "$VOL:/backups:ro" "$IMAGE" >/dev/null
for _ in $(seq 1 60); do
  if docker logs "$SCRATCH" 2>&1 | grep -q 'PostgreSQL init process complete' \
     && docker exec "$SCRATCH" pg_isready -q -U aztdp; then break; fi
  sleep 1
done
docker exec "$SCRATCH" pg_isready -q -U aztdp || { fail "throwaway postgres did not start"; exit 1; }

T0=$(date +%s%N)
docker exec -u postgres "$SCRATCH" sh -eu -c '
  set=$(ls -1d /backups/daily/*/ 2>/dev/null | sort | tail -1)
  [ -n "$set" ] || { echo "no backup set in /backups/daily" >&2; exit 3; }
  echo "restoring $set"
  (cd "$set" && sha256sum -c SHA256SUMS)
  # globals: the bootstrap role already exists in the throwaway cluster, so only
  # "already exists" errors are tolerated.
  psql -X -q -U aztdp -d postgres -f "$set/globals.sql" 2>/tmp/globals.err || true
  if grep ERROR /tmp/globals.err | grep -qv "already exists"; then cat /tmp/globals.err >&2; exit 4; fi
  for db in aztdp keycloak aztdp_django; do
    pg_restore --create --exit-on-error -U aztdp -d postgres "$set/$db.dump"
  done
' || { fail "restore command failed"; exit 1; }
T1=$(date +%s%N)
RESTORE_SECS=$(awk -v a="$T0" -v b="$T1" 'BEGIN{printf "%.1f",(b-a)/1e9}')
echo "RESTORE_TIME_SECONDS=$RESTORE_SECS"

echo "== compare source vs restored"
chk() { if [ "$2" = "$3" ]; then pass "$1 match ($2)"; else fail "$1 mismatch: source=[$2] restored=[$3]"; fi; }
chk "audit_events row count"        "$SRC_AUDIT" "$(dst aztdp aztdp 'SELECT count(*) FROM audit_events')"
chk "token_revocations row count"   "$SRC_TOK"   "$(dst aztdp aztdp 'SELECT count(*) FROM token_revocations')"
chk "trigger set (md5 of rel:name)" "$SRC_TRG"   "$(dst aztdp aztdp "$fp_trg")"
chk "table ownership (md5)"         "$SRC_OWN"   "$(dst aztdp aztdp "$fp_own")"
chk "service roles restored"        "$SRC_ROLE"  "$(dst aztdp postgres "$fp_role")"
chk "immutability trigger count"    "$SRC_NTRG"  "$(dst aztdp aztdp "$fp_ntrg")"
kcq="SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='keycloak'"
chk "keycloak db owner" "$(src aztdp postgres "$kcq")" "$(dst aztdp postgres "$kcq")"

echo "== immutability still enforced after restore"
expect_trigger() {   # DESC SQL
  local out; out=$(dst aztdp aztdp "$2" || true)
  if printf '%s' "$out" | grep -qi 'append-only'; then pass "restored: $1 refused by trigger"; else fail "restored: $1 not refused: $out"; fi
}
expect_trigger "superuser UPDATE audit_events"   "UPDATE audit_events SET service='x'"
expect_trigger "superuser DELETE audit_events"   "DELETE FROM audit_events"
expect_trigger "superuser TRUNCATE audit_events" "TRUNCATE audit_events"
out=$(dst aztdp_ingest aztdp "UPDATE audit_events SET service='x'" || true)
if printf '%s' "$out" | grep -qi 'permission denied'; then pass "restored: aztdp_ingest UPDATE denied (grants preserved)"; else fail "restored ingest UPDATE not denied: $out"; fi
c=$(dst aztdp aztdp "SELECT count(*) FROM audit_events WHERE service='x'")
if [ "$c" = "0" ]; then pass "restored: no audit row was modified"; else fail "audit rows modified: $c"; fi

if [ "$fails" -ne 0 ]; then echo "$fails check(s) FAILED"; exit 1; fi
echo "restore verified in ${RESTORE_SECS}s"
