-- Deploy: app/revoke_all_user_sessions
-- Requires: app/user_sessions, app/envelope_helpers

BEGIN;

\ir ../../procedures/app/sessions/revoke_all_user_sessions.sql

COMMIT;
