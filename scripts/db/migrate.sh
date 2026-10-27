#!/bin/sh
# scripts/db/migrate.sh - the single schema path for the aztdp database.
#
#   1. infra/postgres/04_roles.sql    as the bootstrap superuser: roles, passwords,
#                                     database ownership, keycloak/django databases
#   2. scripts/db/migrations/V*.sql   as aztdp_owner, in numeric order, each in one
#                                     transaction together with its schema_migrations
#                                     row; versions already recorded are skipped
#   3. infra/postgres/05_grants.sql   as aztdp_owner: exact per-service privileges
#
# Every step is idempotent, so this runs on every deploy (compose service
# db-migrate) and is safe to re-run by hand. POSIX sh: it runs in postgres:16-alpine.
#
# Environment (all required, no defaults - fail closed):
#   PGHOST, PGUSER, PGPASSWORD    bootstrap superuser connection (PGPORT optional)
#   PG_OWNER_PASSWORD PG_INGEST_PASSWORD PG_FORENSICS_PASSWORD PG_GATEWAY_PASSWORD
#   PG_ANOMALY_PASSWORD PG_DJANGO_PASSWORD PG_KEYCLOAK_PASSWORD
set -eu

here=$(cd "$(dirname "$0")" && pwd)
MIGRATIONS_DIR=${MIGRATIONS_DIR:-$here/migrations}
PG_SQL_DIR=${PG_SQL_DIR:-$here/../../infra/postgres}
DB=aztdp

for v in PGHOST PGUSER PGPASSWORD PG_OWNER_PASSWORD PG_INGEST_PASSWORD PG_FORENSICS_PASSWORD \
         PG_GATEWAY_PASSWORD PG_ANOMALY_PASSWORD PG_DJANGO_PASSWORD PG_KEYCLOAK_PASSWORD; do
  eval "val=\${$v:-}"
  [ -n "$val" ] || { echo "migrate: $v is required" >&2; exit 1; }
done
unset val

PSQL="psql -X -q -v ON_ERROR_STOP=1 -d $DB"

echo "migrate: [1/3] roles and databases"
$PSQL \
  -v owner_pw="$PG_OWNER_PASSWORD" -v ingest_pw="$PG_INGEST_PASSWORD" \
  -v forensics_pw="$PG_FORENSICS_PASSWORD" -v gateway_pw="$PG_GATEWAY_PASSWORD" \
  -v anomaly_pw="$PG_ANOMALY_PASSWORD" -v django_pw="$PG_DJANGO_PASSWORD" \
  -v keycloak_pw="$PG_KEYCLOAK_PASSWORD" \
  -f "$PG_SQL_DIR/04_roles.sql"

# From here on act as the owner (over the network, so this also proves the
# owner password just set actually authenticates).
PGUSER=aztdp_owner
PGPASSWORD=$PG_OWNER_PASSWORD
export PGUSER PGPASSWORD

echo "migrate: [2/3] migrations"
$PSQL -c "CREATE TABLE IF NOT EXISTS schema_migrations (
            version     TEXT        PRIMARY KEY,
            description TEXT        NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT now())"

# V<n>__<description>.sql, sorted numerically on <n> (V10 after V9).
ls "$MIGRATIONS_DIR" | grep -E '^V[0-9]+__[A-Za-z0-9_]+\.sql$' \
  | awk '{ n = substr($0, 2); sub(/__.*/, "", n); printf "%010d %s\n", n, $0 }' \
  | sort | cut -d' ' -f2- > /tmp/aztdp_migrations.$$
[ -s /tmp/aztdp_migrations.$$ ] || { echo "migrate: no migrations in $MIGRATIONS_DIR" >&2; exit 1; }

while IFS= read -r file; do
  ver=${file%%__*}
  desc=$(printf '%s' "${file#*__}" | sed 's/\.sql$//; s/_/ /g')
  # The advisory lock serialises concurrent runners; the applied-check happens
  # after it, inside the same transaction as the migration and its record.
  # (\i takes the path unquoted, hence the no-whitespace filename pattern above.)
  $PSQL -1 -v ver="$ver" -v desc="$desc" -v file="$MIGRATIONS_DIR/$file" -f - <<'EOF'
SELECT pg_advisory_xact_lock(hashtext('aztdp_schema_migrations')) \gset lock_
SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = :'ver') AS already_applied \gset
\if :already_applied
\echo migrate:   :ver already applied
\else
\echo migrate:   applying :ver
\i :file
INSERT INTO schema_migrations (version, description) VALUES (:'ver', :'desc');
\endif
EOF
done < /tmp/aztdp_migrations.$$
rm -f /tmp/aztdp_migrations.$$

echo "migrate: [3/3] grants"
$PSQL -f "$PG_SQL_DIR/05_grants.sql"

echo "migrate: done"
