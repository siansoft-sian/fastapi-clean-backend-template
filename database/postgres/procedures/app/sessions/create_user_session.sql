-- Function: app.create_user_session
-- Purpose: mint a server-side session after a successful GoTrue login.
-- Inputs:
--   p_token_hash        bytea       - sha256 of the opaque cookie token (32 bytes)
--   p_user_id           uuid        - internal user (from map_identity)
--   p_tenant_id         uuid        - the session's ACTIVE tenant
--   p_access_ct         bytea       - GoTrue access token ciphertext (app-encrypted)
--   p_refresh_ct        bytea       - GoTrue refresh token ciphertext
--   p_gotrue_expires_at timestamptz - GoTrue access-token expiry (drives refresh)
--   p_absolute_ttl      interval    - hard session lifetime
--   p_idle_ttl          interval    - sliding idle lifetime (capped at absolute)
--   p_user_agent        text        - audit
--   p_ip                inet        - audit
-- Returns: ok({session_internal_id, absolute_expires_at, idle_expires_at})
-- Errors:  TENANT_NOT_FOUND, USER_NOT_IN_TENANT
-- Security: DEFINER; coarse tenant-membership validation; Casbin does NOT
--           gate this (auth infrastructure, not an end-user action).

CREATE OR REPLACE FUNCTION app.create_user_session(
    p_token_hash bytea,
    p_user_id uuid,
    p_tenant_id uuid,
    p_access_ct bytea,
    p_refresh_ct bytea,
    p_gotrue_expires_at timestamptz,
    p_absolute_ttl interval,
    p_idle_ttl interval,
    p_user_agent text DEFAULT NULL,
    p_ip inet DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS
$$
DECLARE
    v_now timestamptz := now();
    v_absolute timestamptz := v_now + p_absolute_ttl;
    v_row user_sessions;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM tenants t WHERE t.id = p_tenant_id AND t.status = 'active') THEN
        RETURN app.error('TENANT_NOT_FOUND', 'tenant does not exist or is not active');
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM memberships m
        WHERE m.user_id = p_user_id AND m.tenant_id = p_tenant_id AND m.status = 'active'
    ) THEN
        RETURN app.error('USER_NOT_IN_TENANT', 'user is not an active member of the tenant');
    END IF;

    INSERT INTO user_sessions (
        token_hash, user_id, tenant_id,
        gotrue_access_token, gotrue_refresh_token, gotrue_expires_at,
        absolute_expires_at, idle_expires_at, user_agent, ip
    ) VALUES (
        p_token_hash, p_user_id, p_tenant_id,
        p_access_ct, p_refresh_ct, p_gotrue_expires_at,
        v_absolute, LEAST(v_now + p_idle_ttl, v_absolute), p_user_agent, p_ip
    )
    RETURNING * INTO v_row;

    RETURN app.ok(jsonb_build_object(
        'session_internal_id', v_row.id,
        'absolute_expires_at', v_row.absolute_expires_at,
        'idle_expires_at', v_row.idle_expires_at
    ));
END;
$$;
