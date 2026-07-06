-- Verify: app/touch_user_session

DO $$
BEGIN
    IF to_regprocedure('app.touch_user_session(bytea, interval)') IS NULL THEN
        RAISE EXCEPTION 'function app.touch_user_session(bytea, interval) not found';
    END IF;
END $$;
