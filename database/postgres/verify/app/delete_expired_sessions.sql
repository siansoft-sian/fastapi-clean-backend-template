-- Verify: app/delete_expired_sessions

DO $$
BEGIN
    IF to_regprocedure('app.delete_expired_sessions(interval)') IS NULL THEN
        RAISE EXCEPTION 'function app.delete_expired_sessions(interval) not found';
    END IF;
END $$;
