-- V2: convert audit_events to a monthly range-partitioned table.
-- Safe on an empty or populated V1 heap table: existing rows are moved into the
-- partitioned structure. Installs the partition/retention procedures used by
-- docs/runbooks/AUDIT_RETENTION.md.
--
-- Retention policy (SOC 2 Type II requirement):
--   Hot  : 90 days — in audit_events partitions (PostgreSQL native access)
--   Cold : 7 years  — rows moved into audit_events_cold (archive / external)
--
-- Applied by scripts/db/migrate.sh as aztdp_owner, inside one transaction
-- (no BEGIN/COMMIT here). All partition bounds are UTC month boundaries.

-- ── 1. Move the V1 heap table aside and free its object names ────────────────
-- Without this the partitioned table would get audit_events_pkey1 /
-- audit_events_id_seq1, and every `CREATE INDEX IF NOT EXISTS idx_audit_*`
-- below would be skipped (the names still belong to the legacy table) and then
-- lost when the legacy table is dropped.
DO $$
BEGIN
    IF to_regclass('audit_events') IS NOT NULL
       AND (SELECT relkind FROM pg_class WHERE oid = to_regclass('audit_events')) = 'r' THEN
        ALTER TABLE audit_events RENAME TO audit_events_legacy;
        ALTER TABLE audit_events_legacy RENAME CONSTRAINT audit_events_pkey TO audit_events_legacy_pkey;
        ALTER TABLE audit_events_legacy RENAME CONSTRAINT audit_events_event_type_check
            TO audit_events_legacy_event_type_check;
        ALTER SEQUENCE audit_events_id_seq RENAME TO audit_events_legacy_id_seq;
        DROP INDEX IF EXISTS idx_audit_request_id, idx_audit_session_id, idx_audit_user_id,
                             idx_audit_occurred_at, idx_audit_event_type,
                             idx_audit_session_time, idx_audit_payload_decision;
    END IF;
END $$;

-- ── 2. Partitioned table (columns identical to V1) ───────────────────────────
CREATE TABLE audit_events (
    id             BIGSERIAL,
    event_id       UUID             NOT NULL DEFAULT gen_random_uuid(),
    event_type     TEXT             NOT NULL
                       CHECK (event_type IN (
                           'risk_eval',
                           'policy_decision',
                           'token_revocation',
                           'anomaly_score'
                       )),
    service        TEXT             NOT NULL,
    request_id     TEXT,
    session_id     TEXT,
    user_id        TEXT,
    token_jti_hash TEXT,
    ip             TEXT,
    geo            TEXT,
    payload        JSONB            NOT NULL DEFAULT '{}',
    occurred_at    TIMESTAMPTZ      NOT NULL DEFAULT now(),
    ingested_at    TIMESTAMPTZ      NOT NULL DEFAULT now(),
    CONSTRAINT audit_events_pkey PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);

COMMENT ON TABLE audit_events IS
    'Immutable event log, range-partitioned by month on occurred_at. One row per '
    'enforcement event across all services. Written by telemetry-ingest; read by '
    'forensics. UPDATE/DELETE/TRUNCATE are blocked by trigger (V3).';

-- Catch-all so an event whose occurred_at has no monthly partition (clock skew,
-- backfill, maintenance not yet run) is still recorded instead of rejected.
-- aztdp_audit_ensure_partition() moves such rows into their month when it is
-- created.
CREATE TABLE audit_events_default PARTITION OF audit_events DEFAULT;

-- ── 3. Indexes (same set as V1; created on the parent, cascaded to partitions)
CREATE INDEX idx_audit_request_id  ON audit_events (request_id)     WHERE request_id IS NOT NULL;
CREATE INDEX idx_audit_session_id  ON audit_events (session_id)     WHERE session_id IS NOT NULL;
CREATE INDEX idx_audit_user_id     ON audit_events (user_id)        WHERE user_id IS NOT NULL;
CREATE INDEX idx_audit_occurred_at ON audit_events (occurred_at DESC);
CREATE INDEX idx_audit_event_type  ON audit_events (event_type);
CREATE INDEX idx_audit_session_time
    ON audit_events (session_id, occurred_at DESC)
    WHERE session_id IS NOT NULL;
CREATE INDEX idx_audit_payload_decision
    ON audit_events ((payload->>'decision'))
    WHERE event_type = 'policy_decision';

-- ── 4. Partition management ──────────────────────────────────────────────────
-- Creates audit_events_YYYY_MM for the UTC month containing p_month, moving any
-- rows for that month out of the default partition first (a range partition
-- cannot be added while the default partition holds rows in its range). The
-- default partition is locked for the move so no row can slip in between.
CREATE PROCEDURE aztdp_audit_ensure_partition(p_month DATE)
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
    LOCK TABLE audit_events_default IN EXCLUSIVE MODE;
    EXECUTE format(
        'WITH moved AS (DELETE FROM audit_events_default '
        '               WHERE occurred_at >= %L AND occurred_at < %L RETURNING *) '
        'INSERT INTO %I SELECT * FROM moved',
        lo, hi, part_name);
    EXECUTE format('ALTER TABLE audit_events ATTACH PARTITION %I FOR VALUES FROM (%L) TO (%L)',
                   part_name, lo, hi);
END $$;

-- Call monthly (cron / pg_cron, see docs/runbooks/AUDIT_RETENTION.md):
--   CALL aztdp_audit_maintenance();
-- a. Ensures this month's and next month's partitions exist.
-- b. Moves partitions (and default-partition rows) older than 90 days into
--    audit_events_cold.
-- Runs as aztdp_owner: the immutability trigger (V3) exempts only that role.
CREATE PROCEDURE aztdp_audit_maintenance()
LANGUAGE plpgsql AS $$
DECLARE
    this_month DATE := date_trunc('month', now() AT TIME ZONE 'UTC')::date;
    cutoff     DATE := date_trunc('month', (now() AT TIME ZONE 'UTC') - interval '90 days')::date;
    part_month DATE;
    r          RECORD;
BEGIN
    CALL aztdp_audit_ensure_partition(this_month);
    CALL aztdp_audit_ensure_partition((this_month + interval '1 month')::date);

    FOR r IN
        SELECT c.relname AS pname
        FROM   pg_inherits i
        JOIN   pg_class c ON c.oid = i.inhrelid
        WHERE  i.inhparent = 'audit_events'::regclass
          AND  c.relname ~ '^audit_events_\d{4}_\d{2}$'
    LOOP
        part_month := to_date(substr(r.pname, length('audit_events_') + 1), 'YYYY_MM');
        IF part_month < cutoff THEN
            EXECUTE format('ALTER TABLE audit_events DETACH PARTITION %I', r.pname);
            EXECUTE format('INSERT INTO audit_events_cold SELECT * FROM %I', r.pname);
            EXECUTE format('DROP TABLE %I', r.pname);
            RAISE NOTICE 'Archived partition % to audit_events_cold', r.pname;
        END IF;
    END LOOP;

    -- Stragglers in the default partition follow the same 90-day rule.
    WITH moved AS (
        DELETE FROM audit_events_default
        WHERE occurred_at < (cutoff::timestamp AT TIME ZONE 'UTC')
        RETURNING *
    )
    INSERT INTO audit_events_cold SELECT * FROM moved;
END $$;

REVOKE ALL ON PROCEDURE aztdp_audit_ensure_partition(DATE) FROM PUBLIC;
REVOKE ALL ON PROCEDURE aztdp_audit_maintenance() FROM PUBLIC;

-- Rolling set of six monthly partitions: two months back to three ahead.
DO $$
BEGIN
    FOR i IN -2..3 LOOP
        CALL aztdp_audit_ensure_partition(
            (date_trunc('month', now() AT TIME ZONE 'UTC') + make_interval(months => i))::date);
    END LOOP;
END $$;

-- ── 5. Move legacy rows ──────────────────────────────────────────────────────
DO $$
BEGIN
    IF to_regclass('audit_events_legacy') IS NOT NULL THEN
        INSERT INTO audit_events SELECT * FROM audit_events_legacy;
        PERFORM setval('audit_events_id_seq',
                       greatest((SELECT max(id) FROM audit_events_legacy), 1),
                       (SELECT max(id) FROM audit_events_legacy) IS NOT NULL);
        DROP TABLE audit_events_legacy;
    END IF;
END $$;

-- ── 6. Cold archive ──────────────────────────────────────────────────────────
CREATE TABLE audit_events_cold (
    LIKE audit_events INCLUDING ALL
);

COMMENT ON TABLE audit_events_cold IS
    'Cold archive of audit_events partitions older than 90 days (7-year retention). '
    'Append-only: UPDATE/DELETE/TRUNCATE are blocked by trigger (V3).';
