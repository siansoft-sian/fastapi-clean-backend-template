-- Verify: app/revoke_user_session

DO $$
BEGIN
    IF to_regprocedure('app.revoke_user_session(bytea)') IS NULL THEN
        RAISE EXCEPTION 'function app.revoke_user_session(bytea) not found';
    END IF;
END $$;
