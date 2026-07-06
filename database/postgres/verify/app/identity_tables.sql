-- Verify: app/identity_tables

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['tenants', 'users', 'identities', 'memberships'] LOOP
        IF to_regclass('app.' || t) IS NULL THEN
            RAISE EXCEPTION 'table app.% not found', t;
        END IF;
    END LOOP;
END $$;
