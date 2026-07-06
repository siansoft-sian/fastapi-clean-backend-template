"""TEST-ONLY scaffold implementing the session/identity DB contract.

This mirrors `database/postgres/functions/README.md` exactly so the asyncpg
repositories can be integration-tested before the real sqitch migrations land.
It is NOT a migration and must never ship to production — the real objects are
authored via the database-designer + sqitch-migration-engineer skills.
"""

import os

import asyncpg

POSTGRES_TEST_DSN = os.environ.get("POSTGRES_TEST_DSN", "postgresql://app:app@localhost:5432/app")

TEST_SESSION_TOKEN_KEY = "test-only-session-key"  # noqa: S105 — test scaffold, not a secret

SCAFFOLD_SQL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.user_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    gotrue_access_token bytea NOT NULL,
    gotrue_refresh_token bytea NOT NULL,
    absolute_expires_at timestamptz NOT NULL,
    idle_expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    user_agent text,
    ip text
);

CREATE TABLE IF NOT EXISTS app.identity_map (
    provider_subject text PRIMARY KEY,
    user_id uuid NOT NULL,
    tenant_id uuid NOT NULL
);

CREATE OR REPLACE FUNCTION app._session_key() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT current_setting('app.session_token_key') $$;

CREATE OR REPLACE FUNCTION app._session_to_json(s app.user_sessions) RETURNS jsonb
LANGUAGE sql STABLE AS
$$
SELECT jsonb_build_object(
    'id', s.id,
    'user_id', s.user_id,
    'tenant_id', s.tenant_id,
    'gotrue_access_token', pgp_sym_decrypt(s.gotrue_access_token, app._session_key()),
    'gotrue_refresh_token', pgp_sym_decrypt(s.gotrue_refresh_token, app._session_key()),
    'absolute_expires_at', s.absolute_expires_at,
    'idle_expires_at', s.idle_expires_at,
    'created_at', s.created_at,
    'revoked_at', s.revoked_at
)
$$;

CREATE OR REPLACE FUNCTION app._not_found() RETURNS jsonb LANGUAGE sql IMMUTABLE AS
$$
SELECT jsonb_build_object(
    'success', false, 'data', null,
    'error', jsonb_build_object('code', 'SESSION_NOT_FOUND', 'message', 'session not found')
)
$$;

CREATE OR REPLACE FUNCTION app._session_ok(s app.user_sessions) RETURNS jsonb
LANGUAGE sql STABLE AS
$$
SELECT jsonb_build_object(
    'success', true,
    'data', jsonb_build_object('session', app._session_to_json(s)),
    'error', null
)
$$;

CREATE OR REPLACE FUNCTION app.create_user_session(
    p_user_id uuid, p_tenant_id uuid, p_access_token text, p_refresh_token text,
    p_absolute_ttl_seconds int, p_idle_ttl_seconds int, p_user_agent text, p_ip text
) RETURNS jsonb LANGUAGE plpgsql AS
$$
DECLARE
    v_row app.user_sessions;
    v_absolute timestamptz := now() + make_interval(secs => p_absolute_ttl_seconds);
BEGIN
    INSERT INTO app.user_sessions
        (user_id, tenant_id, gotrue_access_token, gotrue_refresh_token,
         absolute_expires_at, idle_expires_at, user_agent, ip)
    VALUES
        (p_user_id, p_tenant_id,
         pgp_sym_encrypt(p_access_token, app._session_key()),
         pgp_sym_encrypt(p_refresh_token, app._session_key()),
         v_absolute,
         LEAST(now() + make_interval(secs => p_idle_ttl_seconds), v_absolute),
         p_user_agent, p_ip)
    RETURNING * INTO v_row;
    RETURN app._session_ok(v_row);
END
$$;

CREATE OR REPLACE FUNCTION app.get_user_session(p_session_id uuid) RETURNS jsonb
LANGUAGE plpgsql AS
$$
DECLARE
    v_row app.user_sessions;
BEGIN
    SELECT * INTO v_row FROM app.user_sessions WHERE id = p_session_id;
    IF v_row.id IS NULL THEN
        RETURN app._not_found();
    END IF;
    RETURN app._session_ok(v_row);
END
$$;

CREATE OR REPLACE FUNCTION app.touch_user_session(p_session_id uuid, p_idle_ttl_seconds int)
RETURNS jsonb LANGUAGE plpgsql AS
$$
DECLARE
    v_row app.user_sessions;
BEGIN
    UPDATE app.user_sessions
    SET idle_expires_at = LEAST(now() + make_interval(secs => p_idle_ttl_seconds),
                                absolute_expires_at),
        last_seen_at = now()
    WHERE id = p_session_id AND revoked_at IS NULL
    RETURNING * INTO v_row;
    IF v_row.id IS NULL THEN
        RETURN app._not_found();
    END IF;
    RETURN app._session_ok(v_row);
END
$$;

CREATE OR REPLACE FUNCTION app.rotate_user_session(
    p_old_session_id uuid, p_access_token text, p_refresh_token text, p_idle_ttl_seconds int
) RETURNS jsonb LANGUAGE plpgsql AS
$$
DECLARE
    v_old app.user_sessions;
    v_new app.user_sessions;
BEGIN
    UPDATE app.user_sessions SET revoked_at = now()
    WHERE id = p_old_session_id AND revoked_at IS NULL
    RETURNING * INTO v_old;
    IF v_old.id IS NULL THEN
        RETURN app._not_found();
    END IF;
    INSERT INTO app.user_sessions
        (user_id, tenant_id, gotrue_access_token, gotrue_refresh_token,
         absolute_expires_at, idle_expires_at, user_agent, ip)
    VALUES
        (v_old.user_id, v_old.tenant_id,
         pgp_sym_encrypt(p_access_token, app._session_key()),
         pgp_sym_encrypt(p_refresh_token, app._session_key()),
         v_old.absolute_expires_at,
         LEAST(now() + make_interval(secs => p_idle_ttl_seconds), v_old.absolute_expires_at),
         v_old.user_agent, v_old.ip)
    RETURNING * INTO v_new;
    RETURN app._session_ok(v_new);
END
$$;

CREATE OR REPLACE FUNCTION app.revoke_user_session(p_session_id uuid) RETURNS jsonb
LANGUAGE plpgsql AS
$$
BEGIN
    UPDATE app.user_sessions SET revoked_at = now()
    WHERE id = p_session_id AND revoked_at IS NULL;
    RETURN jsonb_build_object('success', true, 'data', null, 'error', null);
END
$$;

CREATE OR REPLACE FUNCTION app.map_identity(p_provider_subject text, p_email text)
RETURNS jsonb LANGUAGE plpgsql AS
$$
DECLARE
    v_row app.identity_map;
BEGIN
    SELECT * INTO v_row FROM app.identity_map WHERE provider_subject = p_provider_subject;
    IF v_row.provider_subject IS NULL THEN
        RETURN jsonb_build_object(
            'success', false, 'data', null,
            'error', jsonb_build_object('code', 'IDENTITY_NOT_FOUND',
                                        'message', 'identity not mapped'));
    END IF;
    RETURN jsonb_build_object(
        'success', true,
        'data', jsonb_build_object('identity', jsonb_build_object(
            'user_id', v_row.user_id, 'tenant_id', v_row.tenant_id)),
        'error', null);
END
$$;
"""


async def apply_session_scaffold(dsn: str = POSTGRES_TEST_DSN) -> None:
    """Apply the scaffold + deliver the pgcrypto key via the database GUC."""
    connection = await asyncpg.connect(dsn)
    try:
        database = await connection.fetchval("SELECT current_database()")
        await connection.execute(
            f'ALTER DATABASE "{database}" '
            f"SET \"app.session_token_key\" = '{TEST_SESSION_TOKEN_KEY}'"
        )
        await connection.execute(SCAFFOLD_SQL)
    finally:
        await connection.close()
