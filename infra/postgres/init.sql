-- PostgreSQL Docker entrypoint init script.
-- Runs once on first container start (when data volume is empty).
-- Executed as the 'postgres' superuser inside the container.

-- Database and user are created by the Docker entrypoint using
-- POSTGRES_DB and POSTGRES_USER. Avoid recreating them here.
GRANT ALL PRIVILEGES ON DATABASE aztdp TO aztdp;

-- Switch to the application database. The canonical schema is applied
-- by 02_schema.sql (next file in lexical order); table-grants by 03_grants.sql.
\connect aztdp

-- Allow aztdp user to create tables and sequences (needed for BIGSERIAL)
GRANT CREATE ON SCHEMA public TO aztdp;
GRANT USAGE  ON SCHEMA public TO aztdp;

-- Ensure future tables created by migrations are also accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES TO aztdp;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO aztdp;
