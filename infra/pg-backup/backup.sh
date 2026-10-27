#!/bin/sh
# One backup set: /backups/daily/<UTC timestamp>/{globals.sql,<db>.dump,SHA256SUMS}.
#   * pg_dumpall --globals-only  - roles (with password hashes), so a restore
#                                  recreates aztdp_owner, aztdp_ingest, ... and
#                                  database/role settings
#   * pg_dump -Fc per database   - schema, data, ownership, ACLs, triggers
# Written to a .tmp dir, every dump validated with pg_restore --list, checksummed,
# then renamed into place: a half-written set is never visible as a backup.
# Sundays also keep a copy under weekly/. Retention: 7 daily, 4 weekly.
# Needs PGHOST PGUSER PGPASSWORD (bootstrap superuser: pg_dumpall needs it to
# read role password hashes). Redis is deliberately not backed up (see runbook).
set -eu
umask 077

: "${PGHOST:?}" "${PGUSER:?}" "${PGPASSWORD:?}"
BACKUP_DIR=${BACKUP_DIR:-/backups}
DATABASES=${BACKUP_DATABASES:-"aztdp keycloak aztdp_django"}
KEEP_DAILY=${BACKUP_KEEP_DAILY:-7}
KEEP_WEEKLY=${BACKUP_KEEP_WEEKLY:-4}

ts=$(date -u +%Y%m%dT%H%M%SZ)
tmp="$BACKUP_DIR/daily/.tmp-$ts"
final="$BACKUP_DIR/daily/$ts"
mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp"

echo "backup: $ts start"
pg_dumpall --globals-only > "$tmp/globals.sql"
for db in $DATABASES; do
  pg_dump -Fc --dbname="$db" -f "$tmp/$db.dump"
  pg_restore --list "$tmp/$db.dump" >/dev/null   # catalog readable => dump not truncated
done
[ -s "$tmp/globals.sql" ] || { echo "backup: empty globals dump" >&2; exit 1; }
(cd "$tmp" && sha256sum globals.sql ./*.dump > SHA256SUMS)

mv "$tmp" "$final"
if [ "$(date -u +%u)" = 7 ]; then cp -a "$final" "$BACKUP_DIR/weekly/$ts"; fi
touch "$BACKUP_DIR/.last_success"

# retention: names sort chronologically; keep the newest N
prune() { ls -1d "$1"/2* 2>/dev/null | sort -r | tail -n +"$(($2 + 1))" | while read -r d; do rm -rf "$d"; done; }
prune "$BACKUP_DIR/daily" "$KEEP_DAILY"
prune "$BACKUP_DIR/weekly" "$KEEP_WEEKLY"
echo "backup: $ts done ($(du -sh "$final" | cut -f1))"
