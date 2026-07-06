-- Verify: app/create_user_session

DO $$
BEGIN
    IF to_regprocedure('app.create_user_session(bytea, uuid, uuid, bytea, bytea, timestamptz, interval, interval, text, inet)') IS NULL THEN
        RAISE EXCEPTION 'function app.create_user_session(bytea, uuid, uuid, bytea, bytea, timestamptz, interval, interval, text, inet) not found';
    END IF;
END $$;
