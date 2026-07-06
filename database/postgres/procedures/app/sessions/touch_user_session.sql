-- Function: app.touch_user_session
-- Purpose: slide the idle expiry on an active session; never extends past
--          absolute_expires_at.
-- Inputs:  p_token_hash bytea, p_idle_ttl interval
-- Returns: ok({idle_expires_at})
-- Errors:  SESSION_NOT_FOUND, SESSION_REVOKED, SESSION_EXPIRED

CREATE OR REPLACE FUNCTION app.touch_user_session(p_token_hash bytea, p_idle_ttl interval)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS
$$
DECLARE
    v_row user_sessions;
    v_new_idle timestamptz;
BEGIN
    SELECT * INTO v_row FROM user_sessions WHERE token_hash = p_token_hash;

    IF NOT FOUND THEN
        RETURN app.error('SESSION_NOT_FOUND', 'no session for this token');
    END IF;
    IF v_row.revoked_at IS NOT NULL THEN
        RETURN app.error('SESSION_REVOKED', 'session has been revoked');
    END IF;
    IF v_row.absolute_expires_at <= now() OR v_row.idle_expires_at <= now() THEN
        RETURN app.error('SESSION_EXPIRED', 'session has expired');
    END IF;

    UPDATE user_sessions
    SET idle_expires_at = LEAST(now() + p_idle_ttl, absolute_expires_at),
        last_seen_at = now()
    WHERE id = v_row.id
    RETURNING idle_expires_at INTO v_new_idle;

    RETURN app.ok(jsonb_build_object('idle_expires_at', v_new_idle));
END;
$$;
