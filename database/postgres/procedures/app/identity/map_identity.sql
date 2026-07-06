-- Function: app.map_identity
-- Purpose: resolve an external identity (GoTrue subject) to the internal
--          (user_id, tenant_id, email). Optionally provisions a new user with
--          a personal tenant when p_provision = true.
-- Inputs:
--   p_provider  text    - identity provider key (e.g. 'supabase')
--   p_subject   text    - provider subject (GoTrue user id / sub claim)
--   p_email     text    - email captured at login (used when provisioning)
--   p_provision boolean - whether an unknown identity may be auto-provisioned
-- Returns: ok({user_id, tenant_id, email})
-- Errors:  IDENTITY_NOT_FOUND      - unknown identity, provisioning disabled
--          NO_ACTIVE_TENANT        - user exists but has no active membership
--          PROVISIONING_DISABLED   - reserved for a future server-side kill
--                                    switch; not emitted today (the per-call
--                                    p_provision flag governs)
-- Tenancy (OPEN QUESTION, D8): provisioning currently creates one personal
--   tenant + default membership. Tenant-choice-at-login / invite-based
--   onboarding is a separate identity-milestone decision.
-- Concurrency: a concurrent provision race on the same (provider, subject)
--   loses the identities PK insert; the loser retries the lookup and returns
--   the winner's mapping.

CREATE OR REPLACE FUNCTION app.map_identity(
    p_provider text,
    p_subject text,
    p_email text,
    p_provision boolean
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, pg_temp AS
$$
DECLARE
    v_user_id uuid;
    v_tenant_id uuid;
    v_email text;
BEGIN
    SELECT i.user_id INTO v_user_id
    FROM identities i
    WHERE i.provider = p_provider AND i.subject = p_subject;

    IF v_user_id IS NULL THEN
        IF NOT p_provision THEN
            RETURN app.error('IDENTITY_NOT_FOUND', 'identity is not mapped to a user');
        END IF;

        BEGIN
            INSERT INTO users (email) VALUES (p_email) RETURNING id INTO v_user_id;
            INSERT INTO identities (provider, subject, user_id, email)
            VALUES (p_provider, p_subject, v_user_id, p_email);
            INSERT INTO tenants (name)
            VALUES (coalesce(p_email, 'user') || ' (personal)')
            RETURNING id INTO v_tenant_id;
            INSERT INTO memberships (user_id, tenant_id, is_default)
            VALUES (v_user_id, v_tenant_id, true);
            RETURN app.ok(jsonb_build_object(
                'user_id', v_user_id, 'tenant_id', v_tenant_id, 'email', p_email
            ));
        EXCEPTION WHEN unique_violation THEN
            -- Lost a concurrent provision race: fall through to the winner's row.
            SELECT i.user_id INTO v_user_id
            FROM identities i
            WHERE i.provider = p_provider AND i.subject = p_subject;
            IF v_user_id IS NULL THEN
                RAISE;  -- some other unique violation: surface it
            END IF;
        END;
    END IF;

    SELECT m.tenant_id INTO v_tenant_id
    FROM memberships m
    JOIN tenants t ON t.id = m.tenant_id AND t.status = 'active'
    WHERE m.user_id = v_user_id AND m.status = 'active'
    ORDER BY m.is_default DESC, m.created_at ASC
    LIMIT 1;

    IF v_tenant_id IS NULL THEN
        RETURN app.error('NO_ACTIVE_TENANT', 'user has no active tenant membership');
    END IF;

    SELECT u.email INTO v_email FROM users u WHERE u.id = v_user_id;

    RETURN app.ok(jsonb_build_object(
        'user_id', v_user_id, 'tenant_id', v_tenant_id, 'email', v_email
    ));
END;
$$;
