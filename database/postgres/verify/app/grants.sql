-- Verify: app/grants

DO $$
BEGIN
    IF NOT has_function_privilege('app_service', 'app.get_user_session(bytea)', 'EXECUTE') THEN
        RAISE EXCEPTION 'app_service missing EXECUTE on get_user_session';
    END IF;
    IF has_table_privilege('app_service', 'app.user_sessions', 'SELECT') THEN
        RAISE EXCEPTION 'app_service must NOT have direct SELECT on user_sessions';
    END IF;
END $$;
