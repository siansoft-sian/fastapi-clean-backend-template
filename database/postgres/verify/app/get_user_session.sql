-- Verify: app/get_user_session

DO $$
BEGIN
    IF to_regprocedure('app.get_user_session(bytea)') IS NULL THEN
        RAISE EXCEPTION 'function app.get_user_session(bytea) not found';
    END IF;
END $$;
