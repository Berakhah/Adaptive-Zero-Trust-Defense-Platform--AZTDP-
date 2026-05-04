-- AZTDP PostgreSQL Schema
-- Version: 1.0
-- Apply: psql -U aztdp -d aztdp -f schema.sql
-- Idempotent: all objects use IF NOT EXISTS

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- audit_events
-- Master event log. Every service writes here via telemetry-ingest.
-- This is the single source of truth for forensics and incident replay.
-- Never deleted; archive old rows to a cold table after 90 days in production.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_events (
    id             BIGSERIAL        PRIMARY KEY,
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
    ingested_at    TIMESTAMPTZ      NOT NULL DEFAULT now()
);

-- Primary forensics query patterns: by session, by user, by time window, by type
CREATE INDEX IF NOT EXISTS idx_audit_request_id  ON audit_events (request_id)     WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_session_id  ON audit_events (session_id)     WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_user_id     ON audit_events (user_id)        WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_occurred_at ON audit_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_type  ON audit_events (event_type);
-- Composite: the most common forensics query (session + time range)
CREATE INDEX IF NOT EXISTS idx_audit_session_time
    ON audit_events (session_id, occurred_at DESC)
    WHERE session_id IS NOT NULL;
-- JSONB path index for querying by decision inside payload
CREATE INDEX IF NOT EXISTS idx_audit_payload_decision
    ON audit_events ((payload->>'decision'))
    WHERE event_type = 'policy_decision';

COMMENT ON TABLE audit_events IS
    'Immutable event log. One row per enforcement event across all services. '
    'Written by telemetry-ingest; read by forensics. Never update or delete rows.';

-- ---------------------------------------------------------------------------
-- risk_evaluations
-- Normalized projection of risk_eval audit events.
-- Enables fast analytical queries without JSONB parsing.
-- Populated by telemetry-ingest when event_type='risk_eval'.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_evaluations (
    id              BIGSERIAL    PRIMARY KEY,
    request_id      TEXT         NOT NULL,
    session_id      TEXT,
    user_id         TEXT,
    token_jti_hash  TEXT,
    risk_score      NUMERIC(5,4) NOT NULL CHECK (risk_score >= 0 AND risk_score <= 1),
    trust_score     NUMERIC(5,4) NOT NULL CHECK (trust_score >= 0 AND trust_score <= 1),
    anomaly_score   NUMERIC(5,4) NOT NULL DEFAULT 0
                        CHECK (anomaly_score >= 0 AND anomaly_score <= 1),
    reasons         JSONB        NOT NULL DEFAULT '[]',
    service         TEXT         NOT NULL,
    endpoint_path   TEXT,
    endpoint_method TEXT,
    sensitivity     SMALLINT     CHECK (sensitivity BETWEEN 1 AND 5),
    evaluated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_risk_eval_session   ON risk_evaluations (session_id)    WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_risk_eval_user       ON risk_evaluations (user_id)       WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_risk_eval_time       ON risk_evaluations (evaluated_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_eval_score      ON risk_evaluations (risk_score DESC);
-- Enables "show all high-risk evals in the last hour" efficiently
CREATE INDEX IF NOT EXISTS idx_risk_eval_score_time
    ON risk_evaluations (risk_score DESC, evaluated_at DESC)
    WHERE risk_score >= 0.65;

COMMENT ON TABLE risk_evaluations IS
    'Normalized risk engine outputs for analytics. Denormalized from audit_events '
    'by telemetry-ingest. risk_score + trust_score + anomaly_score always sum <= 2.';

-- ---------------------------------------------------------------------------
-- policy_decisions
-- Normalized projection of policy_decision audit events.
-- Enables fast queries on decision outcomes without JSONB parsing.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS policy_decisions (
    id              BIGSERIAL    PRIMARY KEY,
    request_id      TEXT         NOT NULL,
    session_id      TEXT,
    user_id         TEXT,
    token_jti_hash  TEXT,
    decision        TEXT         NOT NULL
                        CHECK (decision IN ('allow', 'deny', 'stepup', 'revoke')),
    rule            TEXT,
    policy          TEXT         NOT NULL DEFAULT 'aztdp.authz',
    risk_score      NUMERIC(5,4) CHECK (risk_score >= 0 AND risk_score <= 1),
    anomaly_score   NUMERIC(5,4) CHECK (anomaly_score >= 0 AND anomaly_score <= 1),
    service         TEXT         NOT NULL,
    endpoint_path   TEXT,
    decided_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_policy_dec_session   ON policy_decisions (session_id)  WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_policy_dec_user       ON policy_decisions (user_id)     WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_policy_dec_decision   ON policy_decisions (decision);
CREATE INDEX IF NOT EXISTS idx_policy_dec_time       ON policy_decisions (decided_at DESC);
-- Forensics: find all non-allow decisions (incident candidates)
CREATE INDEX IF NOT EXISTS idx_policy_dec_incidents
    ON policy_decisions (decided_at DESC)
    WHERE decision != 'allow';
-- Pair with risk score for "high risk that was still allowed" queries
CREATE INDEX IF NOT EXISTS idx_policy_dec_allow_risk
    ON policy_decisions (risk_score DESC)
    WHERE decision = 'allow' AND risk_score >= 0.5;

COMMENT ON TABLE policy_decisions IS
    'Normalized OPA/gateway outputs. Denormalized from audit_events by telemetry-ingest. '
    'Primary table for incident identification: query WHERE decision != ''allow''.';

-- ---------------------------------------------------------------------------
-- token_revocations
-- Durable record of all token revocations.
-- Complements the gateway's in-memory + Redis store with persistent history.
-- The gateway checks Redis (fast); this table is the audit record and cold-start
-- source (telemetry-ingest writes here; forensics reads here).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS token_revocations (
    id              BIGSERIAL    PRIMARY KEY,
    token_jti_hash  TEXT         NOT NULL UNIQUE,
    reason          TEXT         NOT NULL,
    source          TEXT         NOT NULL
                        CHECK (source IN ('policy', 'admin', 'session_end', 'manual')),
    revoked_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ,
    user_id         TEXT,
    session_id      TEXT
);

CREATE INDEX IF NOT EXISTS idx_token_rev_hash    ON token_revocations (token_jti_hash);
CREATE INDEX IF NOT EXISTS idx_token_rev_user    ON token_revocations (user_id)    WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_token_rev_expires ON token_revocations (expires_at) WHERE expires_at IS NOT NULL;

COMMENT ON TABLE token_revocations IS
    'Durable revocation log. The gateway holds the live revocation state in Redis; '
    'this table is the audit record. On gateway cold-start it could reload from here '
    '(not yet implemented — Phase 6B covers Redis backing; full cold-start reload is future work).';

-- ---------------------------------------------------------------------------
-- anomaly_baselines
-- Per-entity (user or session) feature baselines stored by the anomaly service
-- after model training. Used to explain anomaly scores in the forensics UI.
-- One row per (entity_type, entity_id, model_version) — UPSERT on update.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS anomaly_baselines (
    id              BIGSERIAL    PRIMARY KEY,
    entity_type     TEXT         NOT NULL CHECK (entity_type IN ('user', 'session', 'token')),
    entity_id       TEXT         NOT NULL,
    feature_vector  JSONB        NOT NULL,
    model_version   TEXT         NOT NULL,
    sample_count    INT          NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (entity_type, entity_id, model_version)
);

CREATE INDEX IF NOT EXISTS idx_anomaly_baseline_entity
    ON anomaly_baselines (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_baseline_model
    ON anomaly_baselines (model_version);

COMMENT ON TABLE anomaly_baselines IS
    'Per-user/session feature baselines written by the anomaly service training pipeline. '
    'feature_vector is a JSON object with the 11 feature names and their mean values. '
    'Used by the forensics service to explain why a score was high.';

-- ---------------------------------------------------------------------------
-- sessions
-- Session-level aggregation updated by telemetry-ingest on every event.
-- Enables O(1) session summary lookup in forensics (no GROUP BY needed).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id               BIGSERIAL    PRIMARY KEY,
    session_id       TEXT         NOT NULL UNIQUE,
    user_id          TEXT         NOT NULL,
    started_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_seen_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ip_first         TEXT,
    geo_first        TEXT,
    ip_last          TEXT,
    geo_last         TEXT,
    risk_max         NUMERIC(5,4) DEFAULT 0 CHECK (risk_max >= 0 AND risk_max <= 1),
    risk_avg         NUMERIC(5,4) DEFAULT 0 CHECK (risk_avg >= 0 AND risk_avg <= 1),
    anomaly_max      NUMERIC(5,4) DEFAULT 0 CHECK (anomaly_max >= 0 AND anomaly_max <= 1),
    request_count    INT          NOT NULL DEFAULT 0,
    decision_counts  JSONB        NOT NULL DEFAULT '{"allow":0,"deny":0,"stepup":0,"revoke":0}',
    closed_at        TIMESTAMPTZ,
    -- Derived flag: session had at least one non-allow decision
    is_suspicious    BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user      ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started   ON sessions (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_suspicious ON sessions (started_at DESC) WHERE is_suspicious = TRUE;
CREATE INDEX IF NOT EXISTS idx_sessions_risk_max  ON sessions (risk_max DESC)   WHERE risk_max >= 0.65;

COMMENT ON TABLE sessions IS
    'Session-level rollup updated by telemetry-ingest on every audit event. '
    'is_suspicious=TRUE when any decision != allow has been recorded for the session. '
    'decision_counts JSONB is updated with JSONB arithmetic on each write.';

-- ---------------------------------------------------------------------------
-- schema_migrations
-- Simple migration tracking (Flyway-compatible naming convention).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT        PRIMARY KEY,
    description TEXT        NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations (version, description)
VALUES ('V1', 'initial schema: audit_events, risk_evaluations, policy_decisions, token_revocations, anomaly_baselines, sessions')
ON CONFLICT (version) DO NOTHING;

COMMIT;
