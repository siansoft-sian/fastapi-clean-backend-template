-- Revert: app/create_user_session

BEGIN;

DROP FUNCTION IF EXISTS app.create_user_session(bytea, uuid, uuid, bytea, bytea, timestamptz, interval, interval, text, inet);

COMMIT;
