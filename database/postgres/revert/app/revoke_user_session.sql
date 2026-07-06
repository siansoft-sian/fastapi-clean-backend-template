-- Revert: app/revoke_user_session

BEGIN;

DROP FUNCTION IF EXISTS app.revoke_user_session(bytea);

COMMIT;
