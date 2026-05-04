-- V2: Convert audit_events to monthly range-partitioned table.
-- Safe to run on an empty or populated table; migrates existing rows to the
-- partitioned structure and installs a maintenance procedure for 90-day retention.
--
-- Retention policy (SOC 2 Type II requirement):
--   Hot  : 90 days — in audit_events partitions (PostgreSQL native access)
--   Cold : 7 years  — rows detached into audit_events_cold (archive / external)
--
-- Run with: psql -U aztdp -d aztdp -f V2__audit_partitioning.sql

BEGIN;

-- ── 1. Rename the existing heap table ────────────────────────────────────────
ALTER TABLE IF EXISTS audit_events RENAME TO audit_events_legacy;

-- ── 2. Create the new partitioned table ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_events (
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
    PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);

-- ── 3. Create 6-month rolling set of partitions ───────────────────────────────
-- Partitions are named audit_events_YYYY_MM.
-- The maintenance procedure below keeps these rolling.
DO $$
DECLARE
    start_month DATE := date_trunc('month', now() - interval '2 months');
    i           INT;
    part_name   TEXT;
    part_start  TEXT;
    part_end    TEXT;
BEGIN
    FOR i IN 0..5 LOOP
        part_name  := 'audit_events_' || to_char(start_month + (i || ' months')::interval, 'YYYY_MM');
        part_start := to_char(start_month + (i || ' months')::interval, 'YYYY-MM-DD');
        part_end   := to_char(start_month + ((i+1) || ' months')::interval, 'YYYY-MM-DD');
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF audit_events '
            'FOR VALUES FROM (%L) TO (%L)',
            part_name, part_start, part_end
        );
    END LOOP;
END $$;

-- ── 4. Restore indexes on the partitioned table ───────────────────────────────
CREATE INDEX IF NOT EXISTS idx_audit_request_id  ON audit_events (request_id)     WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_session_id  ON audit_events (session_id)     WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_user_id     ON audit_events (user_id)        WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_occurred_at ON audit_events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_event_type  ON audit_events (event_type);

-- ── 5. Migrate legacy rows ────────────────────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'audit_events_legacy') THEN
        INSERT INTO audit_events
            SELECT * FROM audit_events_legacy;
        DROP TABLE audit_events_legacy;
    END IF;
END $$;

-- ── 6. Cold archive table ─────────────────────────────────────────────────────
-- Detached partitions are attached here for long-term storage.
CREATE TABLE IF NOT EXISTS audit_events_cold (
    LIKE audit_events INCLUDING ALL
);

-- ── 7. Maintenance procedure ──────────────────────────────────────────────────
-- Call monthly (e.g. from a cron job or pg_cron extension):
--   CALL aztdp_audit_maintenance();
--
-- What it does:
--   a. Creates next month's partition so inserts never hit "no partition" error.
--   b. Detaches partitions older than 90 days into audit_events_cold.
CREATE OR REPLACE PROCEDURE aztdp_audit_maintenance()
LANGUAGE plpgsql AS $$
DECLARE
    next_month  DATE := date_trunc('month', now() + interval '1 month');
    cutoff      DATE := date_trunc('month', now() - interval '90 days');
    part_name   TEXT;
    part_start  TEXT;
    part_end    TEXT;
    r           RECORD;
BEGIN
    -- a. Ensure next month's partition exists
    part_name  := 'audit_events_' || to_char(next_month, 'YYYY_MM');
    part_start := to_char(next_month, 'YYYY-MM-DD');
    part_end   := to_char(next_month + interval '1 month', 'YYYY-MM-DD');
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF audit_events '
        'FOR VALUES FROM (%L) TO (%L)',
        part_name, part_start, part_end
    );

    -- b. Detach and archive partitions older than 90 days
    FOR r IN
        SELECT inhrelid::regclass::text AS pname
        FROM   pg_inherits
        WHERE  inhparent = 'audit_events'::regclass
    LOOP
        -- Extract the month from the partition name (format: audit_events_YYYY_MM)
        IF r.pname ~ 'audit_events_\d{4}_\d{2}' THEN
            DECLARE
                part_month DATE := to_date(
                    regexp_replace(r.pname, '.*_(\d{4})_(\d{2})$', '\1-\2-01'), 'YYYY-MM-DD'
                );
            BEGIN
                IF part_month < cutoff THEN
                    EXECUTE format('ALTER TABLE audit_events DETACH PARTITION %I', r.pname);
                    EXECUTE format(
                        'INSERT INTO audit_events_cold SELECT * FROM %I', r.pname
                    );
                    EXECUTE format('DROP TABLE %I', r.pname);
                    RAISE NOTICE 'Archived partition % to audit_events_cold', r.pname;
                END IF;
            END;
        END IF;
    END LOOP;
END $$;

COMMIT;
