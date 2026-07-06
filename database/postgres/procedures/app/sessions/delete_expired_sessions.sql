-- Function: app.delete_expired_sessions
-- Purpose: retention purge for a scheduled job. Deletes sessions whose hard
--          expiry (or revocation) is older than the grace window. If volume
--          grows large, switch to monthly partitions on created_at and drop
--          partitions instead (see DESIGN doc, Retention).
-- Inputs:  p_older_than interval - grace window past expiry/revocation
-- Returns: ok({deleted_count})
-- Errors:  none
-- Note: rotated_from is ON DELETE SET NULL, so purging old generations never
--       breaks newer sessions' audit chain rows.

CREATE OR REPLACE FUNCTION app.delete_expired_sessions(p_older_than interval)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS
$$
DECLARE
    v_count integer;
BEGIN
    DELETE FROM user_sessions
    WHERE absolute_expires_at < now() - p_older_than
       OR (revoked_at IS NOT NULL AND revoked_at < now() - p_older_than);
    GET DIAGNOSTICS v_count = ROW_COUNT;

    RETURN app.ok(jsonb_build_object('deleted_count', v_count));
END;
$$;
