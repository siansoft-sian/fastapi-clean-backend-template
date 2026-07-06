-- Deploy: app/envelope_helpers
-- Requires: app/init_app_schema

BEGIN;

\ir ../../procedures/app/envelope/envelope_helpers.sql

COMMIT;
