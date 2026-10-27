-- 05_grants.sql — exact table privileges for each service role.
--
-- Run by scripts/db/migrate.sh (step 3 of 3) as aztdp_owner on the aztdp database,
-- AFTER migrations. Idempotent: every run first strips all privileges from the
-- service roles and PUBLIC, then grants exactly what each service's SQL needs, so
-- the effective set is always the one written here.
--
-- Matrix (derived from the statements in services/*):
--   aztdp_ingest     INSERT audit_events, risk_evaluations, policy_decisions,
--                    token_revocations (+ SELECT on column token_jti_hash, the
--                    ON CONFLICT DO NOTHING target);
--                    SELECT/INSERT/UPDATE sessions (ON CONFLICT DO UPDATE reads
--                    sessions.*); USAGE on the five id sequences.
--                    NO SELECT/UPDATE/DELETE/TRUNCATE on audit_events.
--   aztdp_forensics  SELECT audit_events, policy_decisions, risk_evaluations, sessions
--   aztdp_gateway    SELECT/INSERT token_revocations (+ id sequence)  [Task 9 inserts]
--   aztdp_anomaly    SELECT/INSERT/UPDATE anomaly_baselines (+ id sequence)
-- Partitions of audit_events get no grants: services reach rows only through the
-- parent, whose privileges are what PostgreSQL checks for partition routing.

\set ON_ERROR_STOP on

-- ── Reset ────────────────────────────────────────────────────────────────────
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM aztdp_ingest, aztdp_forensics, aztdp_gateway, aztdp_anomaly;
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM aztdp_ingest, aztdp_forensics, aztdp_gateway, aztdp_anomaly;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM aztdp_ingest, aztdp_forensics, aztdp_gateway, aztdp_anomaly;
-- Routines owned by aztdp_owner (retention procedures, trigger function).
-- Extension members (pgcrypto) are owned by the superuser and left as shipped.
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT p.oid::regprocedure AS fn, p.prokind
        FROM   pg_proc p
        JOIN   pg_namespace n ON n.oid = p.pronamespace
        WHERE  n.nspname = 'public' AND p.proowner = 'aztdp_owner'::regrole
    LOOP
        EXECUTE format('REVOKE ALL ON %s %s FROM PUBLIC, aztdp_ingest, aztdp_forensics, aztdp_gateway, aztdp_anomaly',
                       CASE r.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END, r.fn);
    END LOOP;
END $$;

-- Objects aztdp_owner creates later (new tables, partitions, functions) start
-- with no privileges for anyone else; a migration must grant explicitly.
ALTER DEFAULT PRIVILEGES FOR ROLE aztdp_owner IN SCHEMA public REVOKE ALL ON TABLES    FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE aztdp_owner IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE aztdp_owner REVOKE EXECUTE ON ROUTINES FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO aztdp_ingest, aztdp_forensics, aztdp_gateway, aztdp_anomaly;

-- ── telemetry-ingest ─────────────────────────────────────────────────────────
GRANT INSERT ON audit_events, risk_evaluations, policy_decisions, token_revocations TO aztdp_ingest;
-- ON CONFLICT (token_jti_hash) needs SELECT on the conflict-target column only.
GRANT SELECT (token_jti_hash) ON token_revocations TO aztdp_ingest;
GRANT SELECT, INSERT, UPDATE ON sessions TO aztdp_ingest;
GRANT USAGE ON SEQUENCE audit_events_id_seq, risk_evaluations_id_seq, policy_decisions_id_seq,
                        token_revocations_id_seq, sessions_id_seq TO aztdp_ingest;
-- Explicit, so the intent survives any future broad GRANT above.
REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM aztdp_ingest;

-- ── forensics ────────────────────────────────────────────────────────────────
GRANT SELECT ON audit_events, policy_decisions, risk_evaluations, sessions TO aztdp_forensics;

-- ── gateway ──────────────────────────────────────────────────────────────────
GRANT SELECT, INSERT ON token_revocations TO aztdp_gateway;
GRANT USAGE ON SEQUENCE token_revocations_id_seq TO aztdp_gateway;

-- ── anomaly-service ──────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE ON anomaly_baselines TO aztdp_anomaly;
GRANT USAGE ON SEQUENCE anomaly_baselines_id_seq TO aztdp_anomaly;
