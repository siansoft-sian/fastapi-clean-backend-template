-- Verify: app/envelope_helpers

DO $$
BEGIN
    IF (app.ok('{"a": 1}'::jsonb))->>'success' <> 'true' THEN
        RAISE EXCEPTION 'app.ok envelope malformed';
    END IF;
    IF (app.error('X', 'y'))->'error'->>'code' <> 'X' THEN
        RAISE EXCEPTION 'app.error envelope malformed';
    END IF;
END $$;
