-- Verify: app/map_identity

DO $$
BEGIN
    IF to_regprocedure('app.map_identity(text, text, text, boolean)') IS NULL THEN
        RAISE EXCEPTION 'function app.map_identity(text, text, text, boolean) not found';
    END IF;
END $$;
