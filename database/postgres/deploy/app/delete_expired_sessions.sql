-- Deploy: app/delete_expired_sessions
-- Requires: app/user_sessions, app/envelope_helpers

BEGIN;

\ir ../../procedures/app/sessions/delete_expired_sessions.sql

COMMIT;
