-- Deploy: app/roles
-- app_service is the role the application's login role is granted into.
-- EXECUTE on app.* functions is granted to it; no direct table privileges.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_service') THEN
        CREATE ROLE app_service NOLOGIN;
    END IF;
END $$;

COMMIT;
