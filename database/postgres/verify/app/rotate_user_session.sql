-- Verify: app/rotate_user_session

DO $$
BEGIN
    IF to_regprocedure('app.rotate_user_session(bytea, bytea, bytea, bytea, timestamptz, interval)') IS NULL THEN
        RAISE EXCEPTION 'function app.rotate_user_session(bytea, bytea, bytea, bytea, timestamptz, interval) not found';
    END IF;
END $$;
