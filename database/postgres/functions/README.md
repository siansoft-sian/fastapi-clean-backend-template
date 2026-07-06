# Postgres function contracts (authored by the DB skills, not by hand)

The functions and tables described here are implemented via the
**database-designer** + **sqitch-migration-engineer** skills (or the Supabase
MCP `apply_migration` for Supabase targets). FastAPI never reads this folder
at runtime; `app/auth/session_repository.py` and `identity_mapper.py` only
CALL these functions. A test-only scaffold implementing this exact contract
lives in `backend/tests/integration/session_scaffold.py` so the repository can
be integration-tested before the real migrations land — it is NOT a migration.

## Conventions

- Every function returns the standard `jsonb` envelope:
  `{"success": bool, "data": {...} | null, "error": {"code": str, "message": str} | null}`.
- Timestamps serialize as ISO-8601 with timezone.
- Token columns are **encrypted at rest** with `pgcrypto`
  (`pgp_sym_encrypt`/`pgp_sym_decrypt`); the symmetric key is delivered via the
  database GUC `app.session_token_key` (e.g. `ALTER DATABASE ... SET`), never
  hardcoded. Functions return decrypted token values in `data`; the table never
  stores plaintext.

## Table `app.user_sessions`

| column | type | notes |
|---|---|---|
| `id` | `uuid` PK, `gen_random_uuid()` | the opaque session id in the cookie |
| `user_id` | `uuid` NOT NULL | internal user |
| `tenant_id` | `uuid` NOT NULL | internal tenant |
| `email` | `text` NULL | display email captured at login (for `/auth/me`) |
| `gotrue_access_token` | `bytea` NOT NULL | `pgp_sym_encrypt` — never plaintext |
| `gotrue_refresh_token` | `bytea` NOT NULL | `pgp_sym_encrypt` — never plaintext |
| `absolute_expires_at` | `timestamptz` NOT NULL | hard cap, never extended |
| `idle_expires_at` | `timestamptz` NOT NULL | slides on activity, capped by absolute |
| `created_at` | `timestamptz` NOT NULL default now() | |
| `last_seen_at` | `timestamptz` NOT NULL default now() | |
| `revoked_at` | `timestamptz` NULL | set once, never cleared |
| `user_agent` | `text` NULL | audit only |
| `ip` | `text` NULL | audit only |

Index: `(user_id)`, partial index on `revoked_at IS NULL`.

## Functions

All return the envelope; `data.session` carries the full session row with
decrypted tokens (field names exactly as the columns above, tokens as text).

- `app.create_user_session(p_user_id uuid, p_tenant_id uuid, p_email text, p_access_token text, p_refresh_token text, p_absolute_ttl_seconds int, p_idle_ttl_seconds int, p_user_agent text, p_ip text)`
  → inserts with `absolute_expires_at = now() + p_absolute_ttl_seconds`,
  `idle_expires_at = LEAST(now() + p_idle_ttl_seconds, absolute_expires_at)`.
- `app.get_user_session(p_session_id uuid)`
  → returns the session (including revoked ones — the caller decides validity);
  unknown id → `error.code = 'SESSION_NOT_FOUND'`.
- `app.touch_user_session(p_session_id uuid, p_idle_ttl_seconds int)`
  → slides `idle_expires_at = LEAST(now() + ttl, absolute_expires_at)` and
  `last_seen_at = now()` for a non-revoked session; revoked/unknown →
  `SESSION_NOT_FOUND`.
- `app.rotate_user_session(p_old_session_id uuid, p_access_token text, p_refresh_token text, p_idle_ttl_seconds int)`
  → session-fixation defense: atomically revokes the old session and inserts a
  NEW id carrying over `user_id`/`tenant_id`/`absolute_expires_at`, with fresh
  tokens and a re-slid idle expiry; revoked/unknown → `SESSION_NOT_FOUND`.
- `app.revoke_user_session(p_session_id uuid)`
  → sets `revoked_at = now()`; idempotent (revoking twice succeeds).
- `app.map_identity(p_provider_subject text, p_email text)`
  → maps a GoTrue subject to `data.identity = {user_id, tenant_id}`; when no
  mapping exists and provisioning is disallowed → `error.code = 'IDENTITY_NOT_FOUND'`.
  Whether/how to auto-provision users is a product decision for the
  database-designer stage.
