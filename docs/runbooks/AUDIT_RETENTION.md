# Audit Log Retention Runbook

## Policy (SOC 2 Type II)

| Tier | Table | Duration | Access |
|---|---|---|---|
| Hot | `audit_events` (partitioned) | 90 days | Real-time query via application services |
| Cold | `audit_events_cold` | 7 years from event date | Forensics only — no SLA on query speed |

These windows satisfy the SOC 2 Type II evidence requirement for audit log completeness and access-control traceability.

## Schema

`audit_events` is a range-partitioned table (partition key: `occurred_at`). Each partition covers one calendar month and is named `audit_events_YYYY_MM`. Partitions older than 90 days are detached and merged into the `audit_events_cold` heap table by the maintenance procedure.

A `DEFAULT` partition, `audit_events_default`, catches any row whose month has no partition yet (clock skew, backfill, maintenance not run), so an insert is never rejected. `aztdp_audit_ensure_partition(month)` moves those rows into their month when it creates the partition.

Applied by migration `scripts/db/migrations/V2__audit_partitioning.sql` (run by `scripts/db/migrate.sh`, compose service `db-migrate`).

## Immutability

Service roles cannot modify, erase or truncate audit rows in `audit_events` (every partition, including ones created later) or `audit_events_cold`:

- **Grants** (`infra/postgres/05_grants.sql`): `aztdp_ingest` has `INSERT` only; `aztdp_forensics` has `SELECT` only; no service role holds `UPDATE`, `DELETE` or `TRUNCATE`, and no service role has any privilege on individual partitions.
- **Triggers** (`scripts/db/migrations/V3__audit_immutability.sql`, `V4__audit_partition_truncate_guard.sql`): `audit_events_immutable` (row-level, cloned to every partition), `audit_events_no_truncate` (parent), `audit_partition_no_truncate` (on each partition, added by `aztdp_audit_ensure_partition` for new ones) and the `audit_events_cold_*` equivalents raise `insufficient_privilege` on `UPDATE`, `DELETE` or `TRUNCATE` for every role except `aztdp_owner`. That includes plain statements from the bootstrap superuser. Only the retention procedures below run as `aztdp_owner`.

**Limitation (break-glass roles).** `aztdp_owner` (owns the tables) and the bootstrap superuser (`POSTGRES_USER`) can bypass the triggers: `ALTER TABLE ... DISABLE TRIGGER`, `SET session_replication_role = replica`, or dropping the trigger. The database cannot make itself tamper-proof against them. Tamper-evidence against these roles needs external controls: ship audit rows or WAL/logs to write-once storage outside the database's trust boundary, and/or hash-chain rows so gaps and edits are detectable. Keep both credentials out of every service and restrict them to migrations and incident break-glass.

Verify with `bash scripts/db/tests/test_roles.sh`.

## Running Maintenance

### One-time (manual)

Run as `aztdp_owner` (the only role allowed to move audit rows; `EXECUTE` is revoked from everyone else):

```bash
docker compose exec postgres psql -U aztdp_owner -d aztdp -c "CALL aztdp_audit_maintenance();"
```

This is safe to call at any time. It is idempotent: it ensures this and next month's partitions exist and moves partitions (and default-partition rows) older than 90 days into `audit_events_cold`.

**Schedule it.** Migration V2 creates partitions from two months back to three months ahead. Without monthly maintenance, events after that window land in `audit_events_default` (still recorded, but unpartitioned and never archived until maintenance runs).

### Automated (monthly)

Using the `pg_cron` extension (available in Amazon RDS, Cloud SQL, etc.):

```sql
-- Run on the 1st of each month at 03:00 UTC
-- Schedule as aztdp_owner (pg_cron runs the job as the scheduling user)
SELECT cron.schedule('audit-retention', '0 3 1 * *', 'CALL aztdp_audit_maintenance()');
```

For plain PostgreSQL without pg_cron, add a cron job on the host:

```
0 3 1 * * PGPASSWORD="$PG_OWNER_PASSWORD" psql -h <db-host> -U aztdp_owner -d aztdp -c "CALL aztdp_audit_maintenance();" >> /var/log/aztdp-maintenance.log 2>&1
```

## Querying Cold Archive

```sql
-- Count cold events by type
SELECT event_type, count(*) FROM audit_events_cold GROUP BY 1 ORDER BY 2 DESC;

-- Find all events for a user in the cold archive
SELECT * FROM audit_events_cold WHERE user_id = '<uid>' ORDER BY occurred_at;
```

## Adding Future Partitions Manually

If you need to insert events far in the future (e.g., during testing):

```sql
-- as aztdp_owner; moves any rows for that month out of audit_events_default
CALL aztdp_audit_ensure_partition('2027-01-01');
```

Do not use `CREATE TABLE ... PARTITION OF` directly: it fails if `audit_events_default` already holds rows for that month.

## Disaster Recovery

If partitions are accidentally detached without archiving, rows are still in the individual partition tables. Reattach with:

```sql
ALTER TABLE audit_events ATTACH PARTITION audit_events_YYYY_MM
    FOR VALUES FROM ('YYYY-MM-01') TO ('YYYY-MM+1-01');
```

## Evidence for SOC 2 Auditors

- Partition listing: `SELECT inhrelid::regclass FROM pg_inherits WHERE inhparent = 'audit_events'::regclass;`
- Cold archive count: `SELECT count(*) FROM audit_events_cold;`
- Oldest event: `SELECT min(occurred_at) FROM audit_events_cold;`
- Screenshot of both queries at audit time constitutes retention evidence.
