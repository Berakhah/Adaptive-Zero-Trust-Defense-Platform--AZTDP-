-- V4: block TRUNCATE on individual audit_events partitions.
--
-- V3's row triggers (UPDATE/DELETE) are cloned to every partition, but
-- statement-level triggers are not: audit_events_no_truncate exists only on the
-- parent, so `TRUNCATE audit_events_2026_10` or `TRUNCATE audit_events_default`
-- bypassed it. This adds the same BEFORE TRUNCATE guard (aztdp_audit_immutable,
-- which exempts only aztdp_owner) to every existing partition and makes
-- aztdp_audit_ensure_partition add it to partitions created later.
--
-- audit_events_cold is a plain table and already has its own
-- audit_events_cold_no_truncate statement trigger (V3), so it needs nothing here.
--
-- Scope of this control: service roles hold no privileges on partitions at all
-- (and no TRUNCATE on the parent), so for them the trigger is defence in depth.
-- It is NOT a control against aztdp_owner or the bootstrap superuser, which can
-- DISABLE TRIGGER, SET session_replication_role = replica, or drop the trigger.
-- See docs/runbooks/AUDIT_RETENTION.md, "Immutability".

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT c.relname
        FROM   pg_inherits i
        JOIN   pg_class c ON c.oid = i.inhrelid
        WHERE  i.inhparent = 'audit_events'::regclass
    LOOP
        EXECUTE format(
            'CREATE TRIGGER audit_partition_no_truncate BEFORE TRUNCATE ON %I '
            'FOR EACH STATEMENT EXECUTE FUNCTION aztdp_audit_immutable()',
            r.relname);
    END LOOP;
END $$;

-- Same as V2's definition plus the TRUNCATE guard on the new partition (created
-- before ATTACH, so the partition is never attached unguarded).
CREATE OR REPLACE PROCEDURE aztdp_audit_ensure_partition(p_month DATE)
LANGUAGE plpgsql AS $$
DECLARE
    m_start   DATE        := date_trunc('month', p_month)::date;
    lo        TIMESTAMPTZ := m_start::timestamp AT TIME ZONE 'UTC';
    hi        TIMESTAMPTZ := (m_start + interval '1 month')::timestamp AT TIME ZONE 'UTC';
    part_name TEXT        := 'audit_events_' || to_char(m_start, 'YYYY_MM');
BEGIN
    IF to_regclass(part_name) IS NOT NULL THEN
        RETURN;
    END IF;
    EXECUTE format('CREATE TABLE %I (LIKE audit_events INCLUDING DEFAULTS INCLUDING CONSTRAINTS)',
                   part_name);
    EXECUTE format(
        'CREATE TRIGGER audit_partition_no_truncate BEFORE TRUNCATE ON %I '
        'FOR EACH STATEMENT EXECUTE FUNCTION aztdp_audit_immutable()',
        part_name);
    LOCK TABLE audit_events_default IN EXCLUSIVE MODE;
    EXECUTE format(
        'WITH moved AS (DELETE FROM audit_events_default '
        '               WHERE occurred_at >= %L AND occurred_at < %L RETURNING *) '
        'INSERT INTO %I SELECT * FROM moved',
        lo, hi, part_name);
    EXECUTE format('ALTER TABLE audit_events ATTACH PARTITION %I FOR VALUES FROM (%L) TO (%L)',
                   part_name, lo, hi);
END $$;

REVOKE ALL ON PROCEDURE aztdp_audit_ensure_partition(DATE) FROM PUBLIC;
