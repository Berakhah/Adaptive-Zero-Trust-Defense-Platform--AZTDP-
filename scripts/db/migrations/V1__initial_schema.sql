-- Flyway migration V1: Initial AZTDP schema
-- This file is identical in content to scripts/db/schema.sql.
-- schema.sql is used for Docker init (psql \i); this file is used by Flyway CI.
-- Flyway tracks applied migrations in its own flyway_schema_history table.

\i /migrations/../../schema.sql
