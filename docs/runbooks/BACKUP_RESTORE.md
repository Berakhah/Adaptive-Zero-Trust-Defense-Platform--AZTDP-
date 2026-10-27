# Backup and Restore Runbook

Targets: **RPO 24 h**, **RTO 1 h**.

## What is backed up

The `pg-backup` compose service (`infra/pg-backup/`) writes one backup set per
day to the `pg_backups` volume (`/backups` in the container):

```
/backups/daily/<UTC timestamp>/globals.sql   pg_dumpall --globals-only (roles + password hashes)
                               aztdp.dump    pg_dump -Fc  (audit_events, token_revocations, ...)
                               keycloak.dump
                               aztdp_django.dump
                               SHA256SUMS
/backups/weekly/<timestamp>/                 copy of the Sunday set
```

- Retention: **7 daily, 4 weekly** (`BACKUP_KEEP_DAILY` / `BACKUP_KEEP_WEEKLY`).
- Schedule: a backup is taken whenever the newest successful one is older than
  24 h (`BACKUP_INTERVAL_SECONDS`), including right after first deploy. A failed
  run is retried every 15 min; the container healthcheck goes unhealthy when the
  last success is older than 26 h (alert on it).
- Sets are written to a temp directory, validated with `pg_restore --list`,
  checksummed, then renamed into place, so a half-written set never looks valid.
- Globals are required: they recreate `aztdp_owner`, `aztdp_ingest`, ... so that
  restored table ownership and grants (and therefore the `audit_events`
  immutability triggers' exemption for the owner) are intact.
- The service runs as the unprivileged `postgres` user, read-only root
  filesystem, all capabilities dropped, no published ports, on the `aztdp`
  network. It connects as the bootstrap superuser (`POSTGRES_PASSWORD`, guarded
  by `${VAR:?}`) because `pg_dumpall` must read role password hashes; no other
  credential is introduced.

### Image choice

`prodrigestivill/postgres-backup-local` was considered but not used: it is a third-party image (a second supply-chain dependency) and could not be verified end-to-end here with the globals dump, per-set checksums and validate-then-rename layout required for the restore test. The custom service is ~60 lines of
POSIX sh on the same `postgres:16-alpine` image (pinned by digest in
`infra/pg-backup/Dockerfile`; refresh with
`docker buildx imagetools inspect postgres:16-alpine`) so dump tools always
match the server version.

## Redis is not backed up

Redis holds only rebuildable state. Token revocations are durable in Postgres
(`token_revocations`) and the gateway re-syncs them into Redis on start. After
a restore, restart the gateway so it resyncs; Redis may start empty.

## Take a backup on demand

```
docker compose exec pg-backup /backup.sh
```

## Verify backups

Automated and throwaway (own compose project, no
host ports, removes everything on exit):

```
bash scripts/backup/pg_restore_test.sh
```

It seeds rows, takes a backup, restores the newest set into a throwaway
postgres (no network, tmpfs data), and fails non-zero unless `audit_events` and
`token_revocations` row counts, trigger set, table ownership and roles match the
source and the `audit_events` immutability triggers still refuse UPDATE / DELETE
/ TRUNCATE (and `aztdp_ingest` UPDATE is still denied). Run it after any change
to the schema, roles or the backup service, and periodically (restore tests,
not backups, are what prove recoverability).

Quick manual check of the live volume:

```
docker compose exec pg-backup sh -c 'cd /backups/daily/$(ls /backups/daily | sort | tail -1) && sha256sum -c SHA256SUMS'
```

## Restore (production)

Run from the repo root with the same env file / `COMPOSE_PROJECT_NAME` as the
deployment (`P` below is the compose project name, `docker compose config | head -1`
shows it). **This destroys the current `postgres_data` volume**: only do it when
the live database is lost or unusable, and only after a final look at what is on
the `pg_backups` volume. `pg_backups` is never touched by `down` (no `-v`).

1. Stop everything, including `pg-backup` (so retention cannot prune while you
   work) and all Postgres clients. Volumes are kept:
   ```
   docker compose down
   ```
2. Wipe the Postgres data volume and start an empty cluster. Compose creates
   the empty `aztdp` database (`POSTGRES_DB`) and the bootstrap role:
   ```
   docker volume rm "${P}_postgres_data"
   docker compose up -d --wait postgres
   ```
3. List the available sets (a one-off `pg-backup` container: it has the
   `pg_backups` volume, the pg_* tools and the superuser `PGPASSWORD`;
   `--entrypoint` bypasses the backup loop, which would otherwise take a backup):
   ```
   docker compose run --rm --no-deps --entrypoint ls pg-backup /backups/daily
   ```
4. Restore the newest set (set `SET=/backups/daily/<timestamp>` instead of the
   `ls | tail` line to pick another). Globals first (roles), then the empty
   `aztdp` database is dropped so `pg_restore --create` can recreate it with its
   original owner and ACLs, then the three databases:
   ```
   docker compose run --rm --no-deps --entrypoint sh pg-backup -eu -c '
     SET=$(ls -1d /backups/daily/*/ | sort | tail -1)
     echo "restoring $SET"
     (cd "$SET" && sha256sum -c SHA256SUMS)
     # "role aztdp already exists" is expected (bootstrap role); nothing else is
     psql -X -q -d postgres -f "$SET/globals.sql" 2>/tmp/globals.err || true
     if grep ERROR /tmp/globals.err | grep -qv "already exists"; then cat /tmp/globals.err >&2; exit 4; fi
     psql -X -q -d postgres -c "DROP DATABASE IF EXISTS aztdp"   # fresh, empty cluster only
     for db in aztdp keycloak aztdp_django; do
       pg_restore --create --exit-on-error -d postgres "$SET/$db.dump"
     done
   '
   ```
5. Run `db-migrate` (idempotent: versions already in `schema_migrations` are
   skipped; it re-asserts role passwords and grants from the current `.env`):
   ```
   docker compose up --no-deps db-migrate
   ```
6. Verify the audit immutability triggers and grants survived (as the
   superuser, so this proves the trigger, not just grants; both must fail with
   "append-only"):
   ```
   docker compose exec -T postgres psql -U aztdp -d aztdp -c "UPDATE audit_events SET service=service"
   docker compose exec -T postgres psql -U aztdp -d aztdp -c "TRUNCATE audit_events"
   docker compose exec -T postgres psql -U aztdp -d aztdp -tAc "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'audit_events_immutable%'"
   ```
   For the full privilege suite run `bash scripts/db/tests/test_roles.sh`
   (it writes probe rows: use it on a rehearsal, not on the recovered
   production database).
7. Start the rest of the stack and restart the gateway so it re-syncs
   token revocations from Postgres into the (empty) Redis:
   ```
   docker compose up -d
   docker compose restart gateway
   ```

Coverage: `scripts/backup/pg_restore_test.sh` automates the same restore commands
(globals, then `pg_restore --create` per database) into a throwaway container
and the post-restore checks; the in-place wrapper (steps 1-3, 5, 7: volume wipe,
one-off `pg-backup` container, `db-migrate`, service restart) is covered by a
manual rehearsal recorded in the task report, not by CI.

## Measured restore time

`scripts/backup/pg_restore_test.sh` printed `RESTORE_TIME_SECONDS=3.7` on a dev
machine (Docker Desktop, Windows 11) for the test dataset (a few hundred KB, 116 KB
backup set; globals + three `pg_restore --create`). This is the mechanical
restore only. It scales with data size, so re-measure with a production-size
backup; the 1 h RTO budget must also cover detection, decision, DNS/ingress and
service restart. Update this number when you re-measure.

## Limits and what to do next

- **Backups on the same volume/host as the database are not disaster
  recovery.** Losing the host or the Docker volume store loses both. Copy
  `/backups` off-host on a schedule (object storage with versioning/object
  lock, or another site), encrypt it at rest (dumps contain role password
  hashes and audit data), and restore-test from the off-host copy. This
  service does not do the off-host copy; it is a deployment task.
- **RPO is 24 h**: up to a day of audit events and revocations can be lost.
  Revocations lost this way are the dangerous case; for a smaller RPO enable
  WAL archiving (`archive_mode=on`, `archive_command` to off-host storage,
  e.g. pgBackRest or WAL-G) for point-in-time recovery, keeping these dumps as
  the logical fallback.
- Backups are not tamper-evident: the `audit_events` trigger protects the live
  table, not a restored copy in an attacker's hands, and a superuser can
  disable it. Use object lock off-host for tamper resistance.
