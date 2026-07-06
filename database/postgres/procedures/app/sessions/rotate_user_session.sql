-- Function: app.rotate_user_session
-- Purpose: session-fixation defense. Atomically revoke the old session and
--          mint a new one carrying the same user/tenant/absolute expiry.
-- Inputs:
--   p_old_token_hash    bytea       - hash of the token being retired
--   p_new_token_hash    bytea       - hash of the freshly generated token
--   p_access_ct         bytea       - new GoTrue access ciphertext
--   p_refresh_ct        bytea       - new GoTrue refresh ciphertext
--   p_gotrue_expires_at timestamptz - new GoTrue access-token expiry
--   p_idle_ttl          interval    - fresh idle window (capped at absolute)
-- Returns: ok({session_internal_id, absolute_expires_at, idle_expires_at})
-- Errors:  SESSION_NOT_FOUND, SESSION_REVOKED, SESSION_EXPIRED
-- Concurrency: the old row is locked FOR UPDATE. Two concurrent rotations of
--   the same session serialize on that lock: the loser re-reads the row after
--   the winner commits (READ COMMITTED EvalPlanQual recheck), sees revoked_at
--   set, and gets SESSION_REVOKED — exactly one rotation ever succeeds.

CREATE OR REPLACE FUNCTION app.rotate_user_session(
    p_old_token_hash bytea,
    p_new_token_hash bytea,
    p_access_ct bytea,
    p_refresh_ct bytea,
    p_gotrue_expires_at timestamptz,
    p_idle_ttl interval
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS
$$
DECLARE
    v_old user_sessions;
    v_new user_sessions;
BEGIN
    SELECT * INTO v_old
    FROM user_sessions
    WHERE token_hash = p_old_token_hash
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN app.error('SESSION_NOT_FOUND', 'no session for this token');
    END IF;
    IF v_old.revoked_at IS NOT NULL THEN
        RETURN app.error('SESSION_REVOKED', 'session has been revoked');
    END IF;
    IF v_old.absolute_expires_at <= now() OR v_old.idle_expires_at <= now() THEN
        RETURN app.error('SESSION_EXPIRED', 'session has expired');
    END IF;

    INSERT INTO user_sessions (
        token_hash, user_id, tenant_id,
        gotrue_access_token, gotrue_refresh_token, gotrue_expires_at,
        absolute_expires_at, idle_expires_at, rotated_from, user_agent, ip
    ) VALUES (
        p_new_token_hash, v_old.user_id, v_old.tenant_id,
        p_access_ct, p_refresh_ct, p_gotrue_expires_at,
        v_old.absolute_expires_at,                                   -- never extended
        LEAST(now() + p_idle_ttl, v_old.absolute_expires_at),
        v_old.id, v_old.user_agent, v_old.ip
    )
    RETURNING * INTO v_new;

    UPDATE user_sessions SET revoked_at = now() WHERE id = v_old.id;

    RETURN app.ok(jsonb_build_object(
        'session_internal_id', v_new.id,
        'absolute_expires_at', v_new.absolute_expires_at,
        'idle_expires_at', v_new.idle_expires_at
    ));
END;
$$;
