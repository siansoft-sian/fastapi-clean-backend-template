-- Revert: app/grants

BEGIN;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app FROM app_service;
REVOKE USAGE ON SCHEMA app FROM app_service;

COMMIT;
