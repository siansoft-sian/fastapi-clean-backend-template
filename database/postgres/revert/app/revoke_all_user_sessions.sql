-- Revert: app/revoke_all_user_sessions

BEGIN;

DROP FUNCTION IF EXISTS app.revoke_all_user_sessions(uuid, uuid);

COMMIT;
