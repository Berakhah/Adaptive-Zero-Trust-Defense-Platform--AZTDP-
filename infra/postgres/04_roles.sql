-- 04_roles.sql — login roles, database ownership and isolation.
--
-- Run by scripts/db/migrate.sh (step 1 of 3) as the bootstrap superuser
-- (POSTGRES_USER), connected to the aztdp database, BEFORE migrations. Idempotent:
-- re-running only re-applies passwords and attributes (password rotation = change
-- the env value and re-run db-migrate). Table grants are in 05_grants.sql, which
-- runs after the migrations because it needs the tables.
--
-- Required psql variables (passed with -v from the environment, never defaulted):
--   owner_pw ingest_pw forensics_pw gateway_pw anomaly_pw django_pw keycloak_pw
--
-- Roles:
--   aztdp_owner      owns the aztdp database and every object in it; migrations
--                    and audit retention only. No service connects as it.
--   aztdp_ingest     telemetry-ingest   (append audit + derived tables, upsert sessions)
--   aztdp_forensics  forensics          (read-only)
--   aztdp_gateway    gateway            (token_revocations)
--   aztdp_anomaly    anomaly-service    (anomaly_baselines)
--   aztdp_django     django-app         (owns database aztdp_django; no access to aztdp)
--   keycloak         keycloak           (owns database keycloak; no access to aztdp)

\set ON_ERROR_STOP on

SELECT format('CREATE ROLE %I', r)
FROM unnest(ARRAY['aztdp_owner', 'aztdp_ingest', 'aztdp_forensics', 'aztdp_gateway',
                  'aztdp_anomaly', 'aztdp_django', 'keycloak']) AS r
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
\gexec

-- Explicit attributes every run, so a role created or altered by hand is reset.
ALTER ROLE aztdp_owner     WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'owner_pw';
ALTER ROLE aztdp_ingest    WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'ingest_pw';
ALTER ROLE aztdp_forensics WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'forensics_pw';
ALTER ROLE aztdp_gateway   WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'gateway_pw';
ALTER ROLE aztdp_anomaly   WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'anomaly_pw';
ALTER ROLE aztdp_django    WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'django_pw';
ALTER ROLE keycloak        WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'keycloak_pw';

-- ── Databases ────────────────────────────────────────────────────────────────
-- aztdp's public schema is owned by pg_database_owner (PG15+), so the database
-- owner is the only non-superuser that can create objects there.
ALTER DATABASE aztdp OWNER TO aztdp_owner;

-- Keycloak and Django get their own databases so neither can reach audit data.
SELECT 'CREATE DATABASE keycloak OWNER keycloak'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'keycloak')
\gexec
SELECT 'CREATE DATABASE aztdp_django OWNER aztdp_django'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'aztdp_django')
\gexec
ALTER DATABASE keycloak     OWNER TO keycloak;
ALTER DATABASE aztdp_django OWNER TO aztdp_django;

-- No implicit CONNECT/TEMP for PUBLIC; owners keep theirs, services get CONNECT
-- on aztdp only.
REVOKE ALL ON DATABASE aztdp, keycloak, aztdp_django FROM PUBLIC;
GRANT CONNECT ON DATABASE aztdp TO aztdp_ingest, aztdp_forensics, aztdp_gateway, aztdp_anomaly;

-- ── Upgrade path for volumes initialised before Task 8 ───────────────────────
-- The old docker-entrypoint-initdb.d scripts created the schema as the bootstrap
-- superuser. Hand those objects to aztdp_owner so migrations (run as owner) can
-- alter them. No-op on a fresh database. ALTER TABLE also moves owned sequences
-- and indexes.
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT c.oid::regclass AS rel, c.relkind
        FROM   pg_class c
        JOIN   pg_namespace n ON n.oid = c.relnamespace
        WHERE  n.nspname = 'public'
          AND  c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
          AND  c.relkind IN ('r', 'p', 'v', 'm', 'S')
          AND  NOT EXISTS (SELECT 1 FROM pg_depend d
                           WHERE d.objid = c.oid AND d.deptype IN ('a', 'i')
                             AND d.classid = 'pg_class'::regclass
                             AND d.refclassid = 'pg_class'::regclass)
    LOOP
        IF r.relkind = 'S' THEN
            EXECUTE format('ALTER SEQUENCE %s OWNER TO aztdp_owner', r.rel);
        ELSE
            EXECUTE format('ALTER TABLE %s OWNER TO aztdp_owner', r.rel);
        END IF;
    END LOOP;
    FOR r IN
        SELECT p.oid::regprocedure AS fn, p.prokind
        FROM   pg_proc p
        JOIN   pg_namespace n ON n.oid = p.pronamespace
        WHERE  n.nspname = 'public'
          AND  p.proowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
          AND  NOT EXISTS (SELECT 1 FROM pg_depend d
                           WHERE d.objid = p.oid AND d.deptype = 'e')
    LOOP
        IF r.prokind = 'p' THEN
            EXECUTE format('ALTER PROCEDURE %s OWNER TO aztdp_owner', r.fn);
        ELSE
            EXECUTE format('ALTER FUNCTION %s OWNER TO aztdp_owner', r.fn);
        END IF;
    END LOOP;
END $$;
