-- Verify: app/roles

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_service') THEN
        RAISE EXCEPTION 'role app_service not found';
    END IF;
END $$;
