#!/usr/bin/env bash
# scripts/db/tests/test_roles.sh - least-privilege DB roles + append-only audit_events.
#
# Runs against a compose project whose postgres + db-migrate have completed:
#   export COMPOSE_PROJECT_NAME=aztdp_test
#   docker compose --env-file .env.dev -f docker-compose.yml up -d postgres db-migrate
#   bash scripts/db/tests/test_roles.sh
#
# Compose honours COMPOSE_PROJECT_NAME / COMPOSE_FILE / COMPOSE_ENV_FILES from the
# environment, so the same script works against any isolated project. psql runs
# inside the postgres container over the local socket: this tests privileges and
# the immutability trigger, not password authentication.
set -euo pipefail
cd "$(dirname "$0")/../../.."

: "${COMPOSE_ENV_FILES:=.env.dev}"
export COMPOSE_ENV_FILES
DC=(docker compose)

fails=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; fails=$((fails + 1)); }

# psql ROLE DB SQL -> runs as ROLE, prints combined output, returns psql's status.
psql_as() {
  "${DC[@]}" exec -T postgres psql -X -q -t -A -v ON_ERROR_STOP=1 -U "$1" -d "$2" -c "$3" 2>&1
}

# q ROLE DB SQL -> scalar result, never aborts the script (failures show up as
# a wrong value in the following assertion).
q() { psql_as "$@" | tr -d '\r' || true; }

# expect_ok DESC ROLE SQL [DB]
expect_ok() {
  local out
  if out=$(psql_as "$2" "${4:-aztdp}" "$3"); then pass "$1"; else fail "$1 :: $out"; fi
}

# expect_denied DESC ROLE SQL PATTERN [DB] - must fail AND the error must match
# PATTERN, so a typo or missing table can never masquerade as "denied".
expect_denied() {
  local out
  if out=$(psql_as "$2" "${5:-aztdp}" "$3"); then
    fail "$1 :: statement succeeded"
  elif printf '%s' "$out" | grep -qiE "$4"; then
    pass "$1"
  else
    fail "$1 :: wrong error: $out"
  fi
}

PERM='permission denied'
IMMUTABLE='append-only'
NEWEVENT="INSERT INTO audit_events(event_id,event_type,service) VALUES (gen_random_uuid(),'risk_eval','t')"

# ── aztdp_ingest: append-only on audit_events ────────────────────────────────
expect_ok     "ingest can INSERT audit_events" aztdp_ingest "$NEWEVENT"
expect_denied "ingest UPDATE audit_events correctly denied" aztdp_ingest "UPDATE audit_events SET service='x'" "$PERM"
expect_denied "ingest DELETE audit_events correctly denied" aztdp_ingest "DELETE FROM audit_events" "$PERM"
expect_denied "ingest TRUNCATE audit_events correctly denied" aztdp_ingest "TRUNCATE audit_events" "$PERM"
expect_denied "ingest cannot SELECT audit_events" aztdp_ingest "SELECT count(*) FROM audit_events" "$PERM"

# The exact statements telemetry-ingest issues (services/telemetry-ingest/app.py).
expect_ok "ingest INSERT risk_evaluations" aztdp_ingest \
  "INSERT INTO risk_evaluations (request_id,session_id,user_id,token_jti_hash,risk_score,trust_score,anomaly_score,reasons,service,endpoint_path,endpoint_method,sensitivity) VALUES ('r1','s1','u1',NULL,0.5,0.5,0.1,'[]'::jsonb,'t',NULL,NULL,NULL)"
expect_ok "ingest INSERT policy_decisions" aztdp_ingest \
  "INSERT INTO policy_decisions (request_id,session_id,user_id,token_jti_hash,decision,rule,policy,risk_score,anomaly_score,service,endpoint_path) VALUES ('r1','s1','u1',NULL,'deny',NULL,'aztdp.authz',0.5,0.1,'t',NULL)"
TOKREV="INSERT INTO token_revocations (token_jti_hash,reason,source,expires_at,user_id,session_id) VALUES ('h-ingest','policy','policy',NULL::timestamptz,'u1','s1') ON CONFLICT (token_jti_hash) DO NOTHING"
expect_ok "ingest INSERT token_revocations ON CONFLICT DO NOTHING" aztdp_ingest "$TOKREV"
expect_ok "ingest token_revocations conflict path" aztdp_ingest "$TOKREV"
SESSION_UPSERT="INSERT INTO sessions (session_id,user_id,ip_first,geo_first,ip_last,geo_last,risk_max,risk_avg,anomaly_max,request_count,decision_counts,is_suspicious,last_seen_at)
 VALUES ('s1','u1','1.1.1.1','US','1.1.1.1','US',0.5,0.5,0.1,1,'{\"allow\":0,\"deny\":1,\"stepup\":0,\"revoke\":0}'::jsonb,true,now())
 ON CONFLICT (session_id) DO UPDATE SET ip_last=EXCLUDED.ip_last, geo_last=EXCLUDED.geo_last,
   risk_max=GREATEST(sessions.risk_max,EXCLUDED.risk_max), anomaly_max=GREATEST(sessions.anomaly_max,EXCLUDED.anomaly_max),
   request_count=sessions.request_count+1,
   risk_avg=(sessions.risk_avg*sessions.request_count+EXCLUDED.risk_max)/(sessions.request_count+1),
   decision_counts=jsonb_set(sessions.decision_counts,ARRAY['deny'],to_jsonb(COALESCE((sessions.decision_counts->>'deny')::int,0)+1)),
   is_suspicious=sessions.is_suspicious OR EXCLUDED.is_suspicious, last_seen_at=now()"
expect_ok "ingest sessions upsert (insert path)" aztdp_ingest "$SESSION_UPSERT"
expect_ok "ingest sessions upsert (update path)" aztdp_ingest "$SESSION_UPSERT"
expect_denied "ingest cannot touch anomaly_baselines" aztdp_ingest "SELECT 1 FROM anomaly_baselines" "$PERM"

# ── aztdp_forensics: read-only ───────────────────────────────────────────────
expect_denied "forensics read-only (INSERT audit_events denied)" aztdp_forensics \
  "INSERT INTO audit_events(event_id,event_type,service) VALUES (gen_random_uuid(),'risk_eval','x')" "$PERM"
for t in audit_events policy_decisions risk_evaluations sessions; do
  expect_ok "forensics can SELECT $t" aztdp_forensics "SELECT count(*) FROM $t"
done
expect_denied "forensics UPDATE sessions denied" aztdp_forensics "UPDATE sessions SET user_id='x'" "$PERM"

# ── aztdp_gateway: token_revocations only ────────────────────────────────────
expect_ok "gateway cold-start SELECT token_revocations" aztdp_gateway \
  "SELECT token_jti_hash, expires_at FROM token_revocations WHERE expires_at IS NULL OR expires_at > now()"
expect_ok "gateway INSERT token_revocations" aztdp_gateway \
  "INSERT INTO token_revocations (token_jti_hash,reason,source) VALUES ('h-gw','admin','admin') ON CONFLICT (token_jti_hash) DO NOTHING"
expect_denied "gateway DELETE token_revocations denied" aztdp_gateway "DELETE FROM token_revocations" "$PERM"
expect_denied "gateway cannot read audit_events" aztdp_gateway "SELECT 1 FROM audit_events" "$PERM"

# ── aztdp_anomaly: anomaly_baselines only ────────────────────────────────────
BASELINE="INSERT INTO anomaly_baselines (entity_type,entity_id,feature_vector,model_version,sample_count) VALUES ('user','u1','[0.1]'::jsonb,'v1',1)
 ON CONFLICT (entity_type,entity_id,model_version) DO UPDATE SET feature_vector='[0.2]'::jsonb, sample_count=anomaly_baselines.sample_count+1, updated_at=now()"
expect_ok "anomaly baseline upsert (insert path)" aztdp_anomaly "$BASELINE"
expect_ok "anomaly baseline upsert (update path)" aztdp_anomaly "$BASELINE"
expect_ok "anomaly retrain SELECT" aztdp_anomaly "SELECT feature_vector FROM anomaly_baselines ORDER BY updated_at DESC LIMIT 50000"
expect_denied "anomaly cannot read audit_events" aztdp_anomaly "SELECT 1 FROM audit_events" "$PERM"

# ── isolation: Django and Keycloak have their own databases ──────────────────
expect_denied "django cannot connect to aztdp" aztdp_django "SELECT 1" "$PERM|not have CONNECT"
expect_denied "keycloak cannot connect to aztdp" keycloak "SELECT 1" "$PERM|not have CONNECT"
expect_denied "ingest cannot connect to keycloak db" aztdp_ingest "SELECT 1" "$PERM|not have CONNECT" keycloak
expect_ok "django can create tables in its own db" aztdp_django \
  "CREATE TABLE IF NOT EXISTS t_probe(id int); DROP TABLE t_probe" aztdp_django
expect_ok "keycloak can create tables in its own db" keycloak \
  "CREATE TABLE IF NOT EXISTS t_probe(id int); DROP TABLE t_probe" keycloak
expect_denied "service roles cannot create objects in aztdp" aztdp_ingest "CREATE TABLE t_probe(id int)" "$PERM"

# ── immutability trigger ─────────────────────────────────────────────────────
# The trigger fires for every role except aztdp_owner, so plain UPDATE/DELETE/
# TRUNCATE from the bootstrap superuser is refused too. It is NOT a control
# against the owner or a superuser: both can DISABLE TRIGGER or set
# session_replication_role=replica (documented limitation; needs external
# tamper-evidence). Service roles are covered by grants AND the trigger.
SU=$("${DC[@]}" exec -T postgres sh -c 'printf %s "$POSTGRES_USER"')
expect_denied "trigger blocks superuser UPDATE" "$SU" "UPDATE audit_events SET service='x'" "$IMMUTABLE"
expect_denied "trigger blocks superuser DELETE" "$SU" "DELETE FROM audit_events" "$IMMUTABLE"
expect_denied "trigger blocks superuser TRUNCATE" "$SU" "TRUNCATE audit_events" "$IMMUTABLE"
# Row triggers only fire on rows, so seed the (normally empty) cold archive first.
expect_ok "owner can append to audit_events_cold" aztdp_owner "INSERT INTO audit_events_cold(event_type,service) VALUES ('risk_eval','t')"
expect_denied "trigger blocks superuser UPDATE audit_events_cold" "$SU" "UPDATE audit_events_cold SET service='x'" "$IMMUTABLE"
# Owner exemption on a real row (rolled back), not a vacuous WHERE false.
n=$(q aztdp_owner aztdp "BEGIN; WITH u AS (UPDATE audit_events SET service=service WHERE id=(SELECT max(id) FROM audit_events) RETURNING 1) SELECT count(*) FROM u; ROLLBACK")
[ "$n" = "1" ] && pass "owner is exempt (retention maintenance): updated 1 real row" || fail "owner UPDATE on a real row: $n"

# ── partitioning + partitions created after migration ────────────────────────
if "${DC[@]}" exec -T postgres psql -X -U aztdp_owner -d aztdp -c '\d+ audit_events' | grep -qi 'Partition key: RANGE (occurred_at)'; then
  pass "audit_events is PARTITION BY RANGE (occurred_at)"
else
  fail "audit_events is not range-partitioned on occurred_at"
fi
expect_ok "out-of-range occurred_at lands in default partition (no audit loss)" aztdp_ingest \
  "INSERT INTO audit_events(event_type,service,occurred_at) VALUES ('risk_eval','t','2001-01-01')"
FUTURE=$(q aztdp_owner aztdp "SELECT to_char(date_trunc('month', now() + interval '8 months'),'YYYY_MM')")
RUN="probe-$$-$RANDOM"   # marks this run's rows, so the test can be re-run on the same DB
existed=$(q aztdp_owner aztdp "SELECT to_regclass('audit_events_$FUTURE') IS NOT NULL")
expect_ok "ingest can insert a row for a not-yet-created month" aztdp_ingest \
  "INSERT INTO audit_events(event_type,service,occurred_at) VALUES ('risk_eval','$RUN',date_trunc('month', now() + interval '8 months') + interval '1 day')"
if [ "$existed" = "f" ]; then
  n=$(q aztdp_owner aztdp "SELECT count(*) FROM audit_events_default WHERE service='$RUN'")
  [ "$n" = "1" ] && pass "row for a missing month went to audit_events_default" || fail "expected row in default partition, got: $n"
fi
expect_ok "owner creates partition audit_events_$FUTURE (moves rows out of default)" aztdp_owner \
  "CALL aztdp_audit_ensure_partition(date_trunc('month', now() + interval '8 months')::date)"
expect_ok "maintenance procedure runs as owner" aztdp_owner "CALL aztdp_audit_maintenance()"
n=$(q aztdp_owner aztdp "SELECT count(*) FROM audit_events_$FUTURE WHERE service='$RUN'")
[ "$n" = "1" ] && pass "row moved from default into audit_events_$FUTURE" || fail "expected 1 row in audit_events_$FUTURE, got: $n"
n=$(q aztdp_owner aztdp "SELECT count(*) FROM pg_trigger WHERE tgrelid='audit_events_$FUTURE'::regclass AND tgname='audit_events_immutable'")
[ "$n" = "1" ] && pass "new partition inherits audit_events_immutable trigger" || fail "trigger missing on new partition ($n)"
expect_denied "new partition: superuser UPDATE blocked" "$SU" "UPDATE audit_events_$FUTURE SET service='x'" "$IMMUTABLE"
expect_denied "new partition: ingest has no direct access" aztdp_ingest \
  "INSERT INTO audit_events_$FUTURE(event_type,service,occurred_at) VALUES ('risk_eval','t',date_trunc('month', now() + interval '8 months'))" "$PERM"
expect_denied "new partition: forensics has no direct access" aztdp_forensics "SELECT 1 FROM audit_events_$FUTURE" "$PERM"
# TRUNCATE on individual partitions: statement triggers are not cloned from
# the parent, so each partition needs its own (V4 + aztdp_audit_ensure_partition).
CUR=$(q aztdp_owner aztdp "SELECT 'audit_events_' || to_char(now() AT TIME ZONE 'UTC', 'YYYY_MM')")
expect_denied "superuser TRUNCATE monthly partition $CUR blocked" "$SU" "TRUNCATE $CUR" "$IMMUTABLE"
expect_denied "superuser TRUNCATE audit_events_default blocked" "$SU" "TRUNCATE audit_events_default" "$IMMUTABLE"
expect_denied "superuser TRUNCATE post-migration partition audit_events_$FUTURE blocked" "$SU" "TRUNCATE audit_events_$FUTURE" "$IMMUTABLE"
expect_denied "superuser TRUNCATE audit_events_cold blocked" "$SU" "TRUNCATE audit_events_cold" "$IMMUTABLE"
expect_denied "ingest TRUNCATE partition $CUR denied" aztdp_ingest "TRUNCATE $CUR" "$PERM"
expect_denied "procedures not executable by service roles" aztdp_ingest "CALL aztdp_audit_maintenance()" "$PERM"

# ── migrations: recorded once, re-run is a no-op ─────────────────────────────
before=$(q aztdp_owner aztdp "SELECT string_agg(version||'@'||applied_at, ',' ORDER BY version) FROM schema_migrations")
missing=""
for v in V1 V2 V3 V4; do echo "$before" | grep -q "$v@" || missing="$missing $v"; done
[ -z "$missing" ] && pass "schema_migrations records V1..V4" || fail "schema_migrations missing:$missing ($before)"
if out=$("${DC[@]}" run --rm --no-deps db-migrate 2>&1); then
  after=$(q aztdp_owner aztdp "SELECT string_agg(version||'@'||applied_at, ',' ORDER BY version) FROM schema_migrations")
  [ "$before" = "$after" ] && pass "db-migrate re-run is idempotent" || fail "re-run changed schema_migrations: $before -> $after"
else
  fail "db-migrate re-run failed: $out"
fi

if [ "$fails" -ne 0 ]; then echo "$fails check(s) FAILED"; exit 1; fi
echo "all role checks passed"
