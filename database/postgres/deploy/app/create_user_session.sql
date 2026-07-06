-- Deploy: app/create_user_session
-- Requires: app/user_sessions, app/envelope_helpers

BEGIN;

\ir ../../procedures/app/sessions/create_user_session.sql

COMMIT;
