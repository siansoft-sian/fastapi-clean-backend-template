-- Revert: app/roles
-- Intentionally does NOT drop app_service: roles are cluster-wide and may be
-- referenced by other databases. Irreversible by design.

BEGIN;

COMMIT;
