# Design: BFF sessions + identity mapping (database contract)

Status: **implemented** (sqitch plan `app/init_app_schema` … `app/grants`).
Consumers: `backend/app/auth/session_repository.py`, `backend/app/auth/identity_mapper.py`.
Audience: backend + QA handoff.

The FastAPI template uses the locked BFF auth model (D11): FastAPI talks to
Supabase GoTrue server-to-server, keeps the session **server-side in
PostgreSQL**, and the browser holds only an opaque token in an HttpOnly
cookie. This document is the database side of that contract. **All access is
through the functions below** — the application role has zero direct table
privileges (enforced by the `app/grants` change).

These functions are auth *infrastructure* called by FastAPI's auth layer —
not end-user-authorized actions, so Casbin does not gate them. They still
validate inputs and enforce tenant scoping (coarse-authz boundary).

## The two M3 reconciliations (locked)

1. **Opaque token, hashed at rest.** The cookie carries
   `secrets.token_urlsafe(32)` — high-entropy random, NOT a UUID. The app
   passes `sha256(token)` (32 raw bytes) to every session function; the raw
   token never reaches the database. The internal `id uuid` PK exists only
   for FK/audit (`rotated_from` chain). Randomness is the point here — do not
   substitute a time-ordered id for the token (v7 locality loses to
   unpredictability for credentials).
2. **Token-at-rest encryption: Decision (A), app-level.** FastAPI encrypts
   the GoTrue access/refresh tokens with Fernet (key from
   `SESSION_TOKEN_ENCRYPTION_KEY`, env/KMS) before storing and decrypts after
   fetch. The database stores/returns opaque `bytea`; it never sees plaintext
   or the key. **No `pgcrypto`, no extensions at all** (`gen_random_uuid()`
   is built in since PG13). Column types and function signatures are
   identical if this is ever switched to DB-side pgcrypto (Decision B) with
   an app-supplied key parameter.

## Envelope

Every function returns `{success, data, error, meta}` (`jsonb`) via
`app.ok(p_data)` / `app.error(p_code, p_message, p_details)`. `meta` is `{}`
at this layer — request-scoped meta is added by the API. **`bytea` values in
`data` travel hex-encoded** (`encode(col, 'hex')`; adapters decode with
`bytes.fromhex`) because jsonb cannot carry binary.

## Table `app.user_sessions`

See `schema/app/tables/user_sessions.sql` (single source; deploy includes it).

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK `gen_random_uuid()` | internal id for FK/audit — not the cookie value |
| `token_hash` | `bytea` NOT NULL, UNIQUE | sha256 of the cookie token; the only lookup key; CHECK `octet_length = 32` |
| `user_id` | `uuid` FK → `app.users` | |
| `tenant_id` | `uuid` FK → `app.tenants` | the session's **active** tenant |
| `gotrue_access_token` | `bytea` NOT NULL | Fernet ciphertext (Decision A) |
| `gotrue_refresh_token` | `bytea` NOT NULL | Fernet ciphertext |
| `gotrue_expires_at` | `timestamptz` | GoTrue access-token expiry; drives refresh |
| `absolute_expires_at` | `timestamptz` NOT NULL | hard lifetime; **never extended** (rotation carries it over) |
| `idle_expires_at` | `timestamptz` NOT NULL | sliding; CHECK `idle <= absolute` |
| `created_at` / `last_seen_at` | `timestamptz` NOT NULL | `touch` updates `last_seen_at` |
| `revoked_at` | `timestamptz` | NULL = active |
| `rotated_from` | `uuid` self-FK, ON DELETE SET NULL | rotation audit chain; purge-safe |
| `user_agent` / `ip` | `text` / `inet` | audit |

Indexes: `(user_id)`; partial `(user_id, tenant_id) WHERE revoked_at IS NULL`;
`(absolute_expires_at)` for retention sweeps.

**Active-session predicate** (used everywhere):
`revoked_at IS NULL AND absolute_expires_at > now() AND idle_expires_at > now()`.

## Function registry (category: `auth`)

All: `SECURITY DEFINER SET search_path = app, pg_temp`, `RETURNS jsonb`
envelope, EXECUTE granted to `app_service` only. Sources under
`procedures/app/{sessions,identity}/` (deploy scripts `\ir`-include them).

| Function | Purpose | Returns (`data`) | Error codes |
|---|---|---|---|
| `create_user_session(p_token_hash, p_user_id, p_tenant_id, p_access_ct, p_refresh_ct, p_gotrue_expires_at, p_absolute_ttl, p_idle_ttl, p_user_agent, p_ip)` | mint session after login; validates tenant active + user membership | `{session_internal_id, absolute_expires_at, idle_expires_at}` | `TENANT_NOT_FOUND`, `USER_NOT_IN_TENANT` |
| `get_user_session(p_token_hash)` | pure read of an ACTIVE session — does **not** slide expiry; joins `app.users` for `email` (serves `/auth/me`) | `{session_internal_id, user_id, tenant_id, email, gotrue_access_token(hex), gotrue_refresh_token(hex), gotrue_expires_at, absolute_expires_at, idle_expires_at}` | `SESSION_NOT_FOUND`, `SESSION_REVOKED`, `SESSION_EXPIRED` |
| `touch_user_session(p_token_hash, p_idle_ttl)` | slide idle: `LEAST(now()+ttl, absolute)`; bumps `last_seen_at` | `{idle_expires_at}` | same three `SESSION_*` |
| `rotate_user_session(p_old_token_hash, p_new_token_hash, p_access_ct, p_refresh_ct, p_gotrue_expires_at, p_idle_ttl)` | fixation defense; atomic (below) | `{session_internal_id, absolute_expires_at, idle_expires_at}` | same three `SESSION_*` |
| `revoke_user_session(p_token_hash)` | logout; **idempotent** — missing/already-revoked still succeeds | `{revoked: true}` | none |
| `revoke_all_user_sessions(p_user_id, p_tenant_id)` | "log out everywhere"; strictly tenant-scoped | `{revoked_count}` | none |
| `delete_expired_sessions(p_older_than)` | scheduled retention purge | `{deleted_count}` | none |
| `map_identity(p_provider, p_subject, p_email, p_provision)` | GoTrue subject → internal user + **active** tenant; optional provisioning | `{user_id, tenant_id, email}` | `IDENTITY_NOT_FOUND`, `NO_ACTIVE_TENANT`, `PROVISIONING_DISABLED` (reserved, see below) |

### Error code → M3 exception map

| DB code | Backend exception | HTTP |
|---|---|---|
| `SESSION_NOT_FOUND`, `SESSION_REVOKED` | `InvalidSessionError` | 401 |
| `SESSION_EXPIRED` | `SessionExpiredError` | 401 |
| `TENANT_NOT_FOUND`, `USER_NOT_IN_TENANT` | `IdentityMappingError` | 500 |
| `IDENTITY_NOT_FOUND`, `NO_ACTIVE_TENANT`, `PROVISIONING_DISABLED` | `IdentityMappingError` | 500 |

`PROVISIONING_DISABLED` is **reserved** for a future server-side kill switch;
today the per-call `p_provision` flag governs and an unknown identity with
`p_provision = false` returns `IDENTITY_NOT_FOUND` (per the M3-DB spec).

## Concurrency

- **Rotation is atomic and race-safe.** `rotate_user_session` locks the old
  row `FOR UPDATE`. Two concurrent rotations serialize on the lock; the loser
  re-reads the row after the winner commits (READ COMMITTED recheck), sees
  `revoked_at` set, and receives `SESSION_REVOKED`. Exactly one rotation ever
  succeeds — a lost double-rotation cannot mint two live sessions.
- **Revoke is idempotent** by contract: logout never fails.
- **Provisioning race**: `map_identity` catches the `identities` PK
  `unique_violation` and returns the winner's mapping.

## Security

- Stored-procedure-only: `app/grants` revokes ALL table and function
  privileges from PUBLIC, grants EXECUTE to `app_service` (NOLOGIN; the
  deployment's login role is granted membership by ops). No direct
  `user_sessions` access exists for the app.
- Cookie tokens: stored **only** as sha256; GoTrue tokens: stored **only** as
  app-side ciphertext. Neither plaintext tokens nor the Fernet key ever
  appear in the database, its logs, or function parameters' plaintext form.
- All functions `SECURITY DEFINER` with pinned `search_path = app, pg_temp`.
- New functions must be added to `app/grants` explicitly — no
  `ALTER DEFAULT PRIVILEGES` on purpose (grants stay reviewable).

## Retention

`delete_expired_sessions(p_older_than)` runs on a schedule (job runner
arrives with the Celery milestone; until then a cron `SELECT
app.delete_expired_sessions(interval '30 days')` suffices). If session volume
grows large, switch to monthly partitions on `created_at` and drop partitions
instead of row deletes; `rotated_from ... ON DELETE SET NULL` already makes
purges chain-safe.

## Supporting identity tables (minimal, by design)

`app.tenants`, `app.users`, `app.identities`, `app.memberships` carry only
what `map_identity` needs (see `schema/app/tables/identity_tables.sql`). The
full identity/RBAC/tenancy model — roles, invitations, RLS policies, email
uniqueness/verification — is a **separate milestone**; do not extend these
tables ad hoc.

## Migrations

Authored as sqitch changes (this directory is the sqitch project; plan:
`sqitch.plan`, engine pg, registry schema `sqitch`). Dependency order:
schema → helpers → roles → identity tables → user_sessions → one change per
function → grants. Deploy scripts use **script-relative `\ir` includes** so
`procedures/` and `schema/` stay the single source of truth (plain `\i` would
depend on psql's cwd). Required extensions: **none**.

Real deployments: `sqitch deploy db:pg://…`. Supabase targets may prototype
via the Supabase MCP `apply_migration`, but the sqitch change is the system
of record. Integration tests apply these exact scripts through
`backend/tests/integration/sqitch_harness.py`.

## Test plan

Executable coverage lives in `backend/tests/` (pytest, `-m integration`
against compose Postgres — pgTAP is not bundled with `postgres:16-alpine`;
the equivalent pgTAP suite below can be added when a CI image with pgtap
exists).

- **Constraints**: duplicate `token_hash` rejected (unique_violation);
  `idle_expires_at > absolute_expires_at` rejected (check_violation);
  non-32-byte `token_hash` rejected.
- **Contract**: create → get round-trips (email, hex ciphertext, expiries);
  get on revoked → `SESSION_REVOKED`; past idle/absolute → `SESSION_EXPIRED`;
  touch slides idle but never past absolute; revoke idempotent (twice OK).
- **Rotation atomicity**: rotate revokes old + returns new active session;
  **two concurrent rotations → exactly one succeeds**, the loser gets
  `SESSION_REVOKED`.
- **Tenant isolation**: `revoke_all_user_sessions` touches only the given
  tenant's sessions for that user.
- **Retention**: `delete_expired_sessions` deletes only past-window rows.
- **Migration cycle**: deploy → verify (all scripts) → revert (schema gone) →
  redeploy, on a scratch database.

## Open questions

1. **Tenancy for provisioning (D8).** `map_identity(p_provision => true)`
   currently creates one personal tenant + default membership and resolution
   picks `is_default DESC, created_at ASC`. Tenant-selected-at-login and
   invite-based onboarding are unresolved — full identity milestone.
2. **Identity/RBAC model.** `users/tenants/identities/memberships` here are
   the minimum for `map_identity`; roles, invitations, email uniqueness, and
   RLS policies (deferred here because all access is SECURITY DEFINER
   functions) belong to that milestone.
3. **Server-side provisioning switch.** `PROVISIONING_DISABLED` is reserved;
   decide whether a DB-level kill switch (GUC/config table) should override
   the per-call flag.
