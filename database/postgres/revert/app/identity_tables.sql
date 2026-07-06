-- Revert: app/identity_tables

BEGIN;

DROP TABLE app.memberships;
DROP TABLE app.identities;
DROP TABLE app.users;
DROP TABLE app.tenants;

COMMIT;
