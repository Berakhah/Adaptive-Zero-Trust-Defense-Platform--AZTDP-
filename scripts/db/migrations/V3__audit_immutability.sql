-- V3: make audit_events and audit_events_cold append-only.
--
-- Table grants already deny UPDATE/DELETE/TRUNCATE to every service role
-- (infra/postgres/05_grants.sql). This trigger is the second layer: it binds
-- every role, including superusers who bypass grants, except aztdp_owner, which
-- runs the retention procedures (aztdp_audit_ensure_partition moves rows out of
-- the default partition; aztdp_audit_maintenance archives old partitions).
--
-- Row triggers on a partitioned table (PG13+) are cloned to every existing
-- partition and to partitions created or attached later, including
-- audit_events_default.

CREATE FUNCTION aztdp_audit_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_user = 'aztdp_owner' THEN
        IF TG_LEVEL = 'ROW' THEN
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END IF;
        RETURN NULL;
    END IF;
    RAISE EXCEPTION '%.% is append-only: % denied for role %',
                    TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP, current_user
        USING ERRCODE = 'insufficient_privilege';
END $$;

REVOKE ALL ON FUNCTION aztdp_audit_immutable() FROM PUBLIC;

CREATE TRIGGER audit_events_immutable
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION aztdp_audit_immutable();

CREATE TRIGGER audit_events_no_truncate
    BEFORE TRUNCATE ON audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION aztdp_audit_immutable();

CREATE TRIGGER audit_events_cold_immutable
    BEFORE UPDATE OR DELETE ON audit_events_cold
    FOR EACH ROW EXECUTE FUNCTION aztdp_audit_immutable();

CREATE TRIGGER audit_events_cold_no_truncate
    BEFORE TRUNCATE ON audit_events_cold
    FOR EACH STATEMENT EXECUTE FUNCTION aztdp_audit_immutable();
