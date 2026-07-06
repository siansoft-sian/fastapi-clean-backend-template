-- Revert: app/user_sessions

BEGIN;

DROP TABLE app.user_sessions;

COMMIT;
