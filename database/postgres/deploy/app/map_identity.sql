-- Deploy: app/map_identity
-- Requires: app/identity_tables, app/envelope_helpers

BEGIN;

\ir ../../procedures/app/identity/map_identity.sql

COMMIT;
