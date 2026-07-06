-- Function: app.revoke_user_session
-- Purpose: revoke one session (logout). IDEMPOTENT by contract: revoking a
--          missing or already-revoked session still returns success — logout
--          must never fail.
-- Inputs:  p_token_hash bytea
-- Returns: ok({revoked: true})
-- Errors:  none (idempotent success)

CREATE OR REPLACE FUNCTION app.revoke_user_session(p_token_hash bytea)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS
$$
BEGIN
    UPDATE user_sessions
    SET revoked_at = now()
    WHERE token_hash = p_token_hash AND revoked_at IS NULL;

    RETURN app.ok(jsonb_build_object('revoked', true));
END;
$$;
