-- Revert: app/rotate_user_session

BEGIN;

DROP FUNCTION IF EXISTS app.rotate_user_session(bytea, bytea, bytea, bytea, timestamptz, interval);

COMMIT;
