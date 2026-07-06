-- Revert: app/envelope_helpers

BEGIN;

DROP FUNCTION IF EXISTS app.ok(jsonb);
DROP FUNCTION IF EXISTS app.error(text, text, jsonb);

COMMIT;
