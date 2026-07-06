-- Verify: app/user_sessions

DO $$
BEGIN
    IF to_regclass('app.user_sessions') IS NULL THEN
        RAISE EXCEPTION 'table app.user_sessions not found';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'user_sessions_token_hash_key'
    ) THEN
        RAISE EXCEPTION 'unique constraint on token_hash missing';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'user_sessions_idle_within_absolute'
    ) THEN
        RAISE EXCEPTION 'idle<=absolute check constraint missing';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'user_sessions_token_hash_is_sha256'
    ) THEN
        RAISE EXCEPTION 'token_hash length check constraint missing';
    END IF;
END $$;
