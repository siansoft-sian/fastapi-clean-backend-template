-- Table: app.user_sessions
-- Purpose: server-side BFF sessions (locked decision D11). The browser holds a
--          high-entropy opaque token in an HttpOnly cookie; the DATABASE only
--          ever sees sha256(token) — plaintext cookie tokens never reach SQL.
--          GoTrue access/refresh tokens are stored as opaque ciphertext
--          (app-level Fernet encryption — Decision A; the DB never sees
--          plaintext tokens or the key).
-- Access:  stored functions only; no direct table privileges are granted.

CREATE TABLE app.user_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- sha256 of the opaque cookie token; the ONLY lookup key the app uses.
    -- v4 uuid for id / random token for lookup is deliberate: session
    -- unpredictability beats index locality here.
    token_hash bytea NOT NULL,
    user_id uuid NOT NULL REFERENCES app.users (id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES app.tenants (id) ON DELETE CASCADE,
    gotrue_access_token bytea NOT NULL,
    gotrue_refresh_token bytea NOT NULL,
    gotrue_expires_at timestamptz,
    absolute_expires_at timestamptz NOT NULL,
    idle_expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    rotated_from uuid REFERENCES app.user_sessions (id) ON DELETE SET NULL,
    user_agent text,
    ip inet,
    CONSTRAINT user_sessions_token_hash_key UNIQUE (token_hash),
    CONSTRAINT user_sessions_token_hash_is_sha256 CHECK (octet_length(token_hash) = 32),
    CONSTRAINT user_sessions_idle_within_absolute CHECK (idle_expires_at <= absolute_expires_at)
);

-- "revoke everything for this user" scans.
CREATE INDEX user_sessions_user_id_idx ON app.user_sessions (user_id);
-- Active-session scans (revoke_all, admin views).
CREATE INDEX user_sessions_active_idx
    ON app.user_sessions (user_id, tenant_id)
    WHERE revoked_at IS NULL;
-- Retention sweeps by delete_expired_sessions.
CREATE INDEX user_sessions_absolute_expires_at_idx ON app.user_sessions (absolute_expires_at);
