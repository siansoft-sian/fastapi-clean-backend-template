-- Verify: app/init_app_schema

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'app') THEN
        RAISE EXCEPTION 'schema app not found';
    END IF;
END $$;
