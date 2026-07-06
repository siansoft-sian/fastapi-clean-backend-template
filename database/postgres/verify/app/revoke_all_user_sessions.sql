-- Verify: app/revoke_all_user_sessions

DO $$
BEGIN
    IF to_regprocedure('app.revoke_all_user_sessions(uuid, uuid)') IS NULL THEN
        RAISE EXCEPTION 'function app.revoke_all_user_sessions(uuid, uuid) not found';
    END IF;
END $$;
