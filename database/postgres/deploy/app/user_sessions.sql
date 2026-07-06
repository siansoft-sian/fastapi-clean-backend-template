-- Deploy: app/user_sessions
-- Requires: app/identity_tables

BEGIN;

\ir ../../schema/app/tables/user_sessions.sql

COMMIT;
