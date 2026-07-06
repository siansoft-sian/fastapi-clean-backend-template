-- Deploy: app/identity_tables
-- Requires: app/init_app_schema

BEGIN;

\ir ../../schema/app/tables/identity_tables.sql

COMMIT;
