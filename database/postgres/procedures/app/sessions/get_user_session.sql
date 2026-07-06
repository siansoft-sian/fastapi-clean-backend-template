-- Function: app.get_user_session
-- Purpose: resolve an ACTIVE session by token hash. Pure read — never slides
--          expiry (that is touch_user_session's job).
-- Inputs:  p_token_hash bytea - sha256 of the cookie token
-- Returns: ok({session_internal_id, user_id, tenant_id, email,
--              gotrue_access_token, gotrue_refresh_token,  -- hex-encoded ciphertext
--              gotrue_expires_at, absolute_expires_at, idle_expires_at})
--          `email` is joined from app.users for the /auth/me surface.
--          bytea travels HEX-encoded inside jsonb (adapter: bytes.fromhex).
-- Errors:  SESSION_NOT_FOUND, SESSION_REVOKED, SESSION_EXPIRED

CREATE OR REPLACE FUNCTION app.get_user_session(p_token_hash bytea)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = app, pg_temp AS
$$
DECLARE
    v_row record;
BEGIN
    SELECT s.*, u.email AS user_email
    INTO v_row
    FROM user_sessions s
    JOIN users u ON u.id = s.user_id
    WHERE s.token_hash = p_token_hash;

    IF NOT FOUND THEN
        RETURN app.error('SESSION_NOT_FOUND', 'no session for this token');
    END IF;
    IF v_row.revoked_at IS NOT NULL THEN
        RETURN app.error('SESSION_REVOKED', 'session has been revoked');
    END IF;
    IF v_row.absolute_expires_at <= now() OR v_row.idle_expires_at <= now() THEN
        RETURN app.error('SESSION_EXPIRED', 'session has expired');
    END IF;

    RETURN app.ok(jsonb_build_object(
        'session_internal_id', v_row.id,
        'user_id', v_row.user_id,
        'tenant_id', v_row.tenant_id,
        'email', v_row.user_email,
        'gotrue_access_token', encode(v_row.gotrue_access_token, 'hex'),
        'gotrue_refresh_token', encode(v_row.gotrue_refresh_token, 'hex'),
        'gotrue_expires_at', v_row.gotrue_expires_at,
        'absolute_expires_at', v_row.absolute_expires_at,
        'idle_expires_at', v_row.idle_expires_at
    ));
END;
$$;
