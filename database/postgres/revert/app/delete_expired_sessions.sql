-- Revert: app/delete_expired_sessions

BEGIN;

DROP FUNCTION IF EXISTS app.delete_expired_sessions(interval);

COMMIT;
