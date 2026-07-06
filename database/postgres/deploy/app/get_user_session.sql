-- Deploy: app/get_user_session
-- Requires: app/user_sessions, app/envelope_helpers

BEGIN;

\ir ../../procedures/app/sessions/get_user_session.sql

COMMIT;
