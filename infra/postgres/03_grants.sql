-- Runs after 02_schema.sql (entrypoint executes /docker-entrypoint-initdb.d/*
-- in lexical order). Grants table-level access after the schema exists.
\connect aztdp

GRANT SELECT, INSERT, UPDATE ON ALL TABLES    IN SCHEMA public TO aztdp;
GRANT USAGE, SELECT          ON ALL SEQUENCES IN SCHEMA public TO aztdp;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES TO aztdp;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO aztdp;
