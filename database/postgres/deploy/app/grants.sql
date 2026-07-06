-- Deploy: app/grants
-- Stored-procedure-only access: the app role gets EXECUTE on functions and
-- ZERO direct table privileges. Future functions must be granted here too
-- (no ALTER DEFAULT PRIVILEGES on purpose: grants stay explicit + reviewable).

BEGIN;

REVOKE ALL ON ALL TABLES IN SCHEMA app FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app FROM PUBLIC;

GRANT USAGE ON SCHEMA app TO app_service;
GRANT EXECUTE ON FUNCTION app.ok(jsonb) TO app_service;
GRANT EXECUTE ON FUNCTION app.error(text, text, jsonb) TO app_service;
GRANT EXECUTE ON FUNCTION app.create_user_session(bytea, uuid, uuid, bytea, bytea, timestamptz, interval, interval, text, inet) TO app_service;
GRANT EXECUTE ON FUNCTION app.get_user_session(bytea) TO app_service;
GRANT EXECUTE ON FUNCTION app.touch_user_session(bytea, interval) TO app_service;
GRANT EXECUTE ON FUNCTION app.rotate_user_session(bytea, bytea, bytea, bytea, timestamptz, interval) TO app_service;
GRANT EXECUTE ON FUNCTION app.revoke_user_session(bytea) TO app_service;
GRANT EXECUTE ON FUNCTION app.revoke_all_user_sessions(uuid, uuid) TO app_service;
GRANT EXECUTE ON FUNCTION app.delete_expired_sessions(interval) TO app_service;
GRANT EXECUTE ON FUNCTION app.map_identity(text, text, text, boolean) TO app_service;

COMMIT;
