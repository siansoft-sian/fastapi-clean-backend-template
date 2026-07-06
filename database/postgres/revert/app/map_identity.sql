-- Revert: app/map_identity

BEGIN;

DROP FUNCTION IF EXISTS app.map_identity(text, text, text, boolean);

COMMIT;
