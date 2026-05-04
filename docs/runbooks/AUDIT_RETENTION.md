# Audit Log Retention Runbook

## Policy (SOC 2 Type II)

| Tier | Table | Duration | Access |
|---|---|---|---|
| Hot | `audit_events` (partitioned) | 90 days | Real-time query via application services |
| Cold | `audit_events_cold` | 7 years from event date | Forensics only — no SLA on query speed |

These windows satisfy the SOC 2 Type II evidence requirement for audit log completeness and access-control traceability.

## Schema

`audit_events` is a range-partitioned table (partition key: `occurred_at`). Each partition covers one calendar month and is named `audit_events_YYYY_MM`. Partitions older than 90 days are detached and merged into the `audit_events_cold` heap table by the maintenance procedure.

Applied by migration `scripts/db/migrations/V2__audit_partitioning.sql`.

## Running Maintenance

### One-time (manual)

```sql
CALL aztdp_audit_maintenance();
```

This is safe to call at any time. It is idempotent.

### Automated (monthly)

Using the `pg_cron` extension (available in Amazon RDS, Cloud SQL, etc.):

```sql
-- Run on the 1st of each month at 03:00 UTC
SELECT cron.schedule('audit-retention', '0 3 1 * *', 'CALL aztdp_audit_maintenance()');
```

For plain PostgreSQL without pg_cron, add a cron job on the host:

```
0 3 1 * * psql -U aztdp -d aztdp -c "CALL aztdp_audit_maintenance();" >> /var/log/aztdp-maintenance.log 2>&1
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
CREATE TABLE audit_events_2027_01 PARTITION OF audit_events
    FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');
```

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
