-- Function: app.revoke_all_user_sessions
-- Purpose: "log out everywhere" / security events. Revokes every ACTIVE
--          session for the user in the given tenant — strictly tenant-scoped.
-- Inputs:  p_user_id uuid, p_tenant_id uuid
-- Returns: ok({revoked_count})
-- Errors:  none (zero revocations is success)

CREATE OR REPLACE FUNCTION app.revoke_all_user_sessions(p_user_id uuid, p_tenant_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS
$$
DECLARE
    v_count integer;
BEGIN
    UPDATE user_sessions
    SET revoked_at = now()
    WHERE user_id = p_user_id
      AND tenant_id = p_tenant_id
      AND revoked_at IS NULL
      AND absolute_expires_at > now()
      AND idle_expires_at > now();
    GET DIAGNOSTICS v_count = ROW_COUNT;

    RETURN app.ok(jsonb_build_object('revoked_count', v_count));
END;
$$;
