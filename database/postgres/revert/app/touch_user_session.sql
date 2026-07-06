-- Revert: app/touch_user_session

BEGIN;

DROP FUNCTION IF EXISTS app.touch_user_session(bytea, interval);

COMMIT;
