-- Revert: app/get_user_session

BEGIN;

DROP FUNCTION IF EXISTS app.get_user_session(bytea);

COMMIT;
