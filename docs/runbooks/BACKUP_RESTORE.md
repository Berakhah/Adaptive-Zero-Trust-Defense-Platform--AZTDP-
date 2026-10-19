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

Automated, throwaway, safe to run anywhere Docker runs (own compose project, no
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

1. Stop writers: `docker compose stop nginx gateway telemetry-ingest forensics anomaly-detection django keycloak`
   (keep `postgres` running; stop `pg-backup` too so retention cannot prune).
2. Pick the set: `docker compose run --rm --no-deps pg-backup ls /backups/daily`.
3. Into a **fresh, empty** cluster (new `postgres_data` volume, same
   `POSTGRES_USER`/`POSTGRES_PASSWORD`, `POSTGRES_DB=postgres`), as the postgres
   superuser:
   ```
   SET=/backups/daily/<timestamp>
   (cd $SET && sha256sum -c SHA256SUMS)
   psql -U aztdp -d postgres -f $SET/globals.sql     # "role aztdp already exists" is expected
   for db in aztdp keycloak aztdp_django; do
     pg_restore --create --exit-on-error -U aztdp -d postgres $SET/$db.dump
   done
   ```
4. Run `db-migrate` (idempotent; re-asserts roles, passwords, grants).
5. Start the services; restart the gateway so it resyncs revocations to Redis.
6. Confirm immutability still holds (`bash scripts/db/tests/test_roles.sh`).

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
