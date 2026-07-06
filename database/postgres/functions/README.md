# Postgres function contracts

The session + identity contract that `backend/app/auth/` calls through is
**implemented** as sqitch changes in the parent directory
(`database/postgres/sqitch.plan`) and fully documented in
[`DESIGN-sessions-identity.md`](../DESIGN-sessions-identity.md).

Ground rules (unchanged):

- FastAPI never reads this folder at runtime; repositories only call the
  functions the migrations create, and the app role has **no direct table
  privileges** (see the `app/grants` change).
- Migrations are applied with **sqitch** (or prototyped via the Supabase MCP
  `apply_migration` — sqitch stays the system of record).
- Function sources live under `../procedures/`; tables under `../schema/`.
  Deploy scripts `\ir`-include them, so those files are the single source of
  truth. Signature changes go through `sqitch rework`, never in-place edits.

## Pending contract: RBAC role data (identity/RBAC milestone)

TODO(M3-reconcile) — authored by the **database-designer** skill, consumed by
M4 authorization:

- `app.roles` (role codes: admin, manager, staff, owner, finance, ...) and
  `app.user_roles` (user ↔ role per tenant; or extend `app.memberships`).
- `app.get_user_roles(p_user_id uuid, p_tenant_id uuid)` → envelope with
  `data.roles: [text]` — called at session creation/refresh so `AuthContext`
  carries `roles`, and scopes are cached via
  `AuthorizationService.compute_scopes(roles, tenant_id)`.
- Longer term, the rbac-library projection (`identity.casbin_rule` +
  `sp_rebuild_casbin_policy()`) can replace the request-carried roles in
  `app/authorization/casbin_model.conf` with `g` rules.

## Pending contract: bookings (M6 reference module)

Authored by **database-designer** + **sqitch-migration-engineer**; consumed by
`app/modules/bookings/infrastructure/database_booking_repository.py`. The
integration contract tests self-skip until `app.fn_create_booking` exists,
then activate automatically.

### Table `app.bookings`

| column | type | notes |
|---|---|---|
| `id` | `uuid` PK `gen_random_uuid()` | |
| `tenant_id` | `uuid` NOT NULL FK → `app.tenants` | every function filters on it |
| `owner_id` | `uuid` NOT NULL FK → `app.users` | |
| `status` | `text` NOT NULL CHECK (`pending/approved/cancelled/completed`) | transition guard in functions (belt-and-suspenders with the domain) |
| `reference` | `text` NOT NULL | client-supplied business key; UNIQUE `(tenant_id, reference)` — the idempotency anchor |
| `resource_id` | `text` NOT NULL | the thing being booked |
| `scheduled_at` | `timestamptz` NOT NULL | UTC; see data-types-and-money.md |
| `duration_minutes` | `int` NOT NULL DEFAULT 60 | `# TODO(BA)` template default |
| `slot` | `tstzrange` GENERATED (`[scheduled_at, scheduled_at + duration)`) | drives the exclusion constraint |
| `created_at`/`updated_at` | `timestamptz` NOT NULL | functions bump `updated_at` |
| `created_by`/`updated_by` | `uuid` | audit |
| `version` | `int` NOT NULL DEFAULT 1 | optimistic concurrency; +1 per mutation |
| `cancel_reason` | `text` NULL | |

**Double-booking (concurrency-and-integrity.md):** requires `btree_gist`;
`EXCLUDE USING gist (tenant_id WITH =, resource_id WITH =, slot WITH &&)
WHERE (status IN ('pending','approved'))` — the adapter maps the exclusion
violation to `BOOKING_SLOT_UNAVAILABLE` (409).

### Functions (standard envelope; every one takes `p_tenant_id` first and
enforces tenant scoping + coarse actor validation — active membership)

- `app.fn_create_booking(p_tenant_id, p_owner_id, p_reference, p_resource_id, p_scheduled_at, p_created_by)` → `data.booking`; errors `BOOKING_REFERENCE_EXISTS`, `BOOKING_SLOT_UNAVAILABLE`, `USER_NOT_IN_TENANT`
- `app.fn_get_booking(p_tenant_id, p_booking_id)` → `data.booking`; `BOOKING_NOT_FOUND` (cross-tenant answers identically)
- `app.fn_approve_booking(p_tenant_id, p_booking_id, p_actor_id, p_expected_version)` → guard `pending→approved`; errors `BOOKING_NOT_FOUND`, `BOOKING_INVALID_TRANSITION` (details: current/target), `BOOKING_VERSION_CONFLICT`
- `app.fn_cancel_booking(p_tenant_id, p_booking_id, p_actor_id, p_expected_version, p_reason)` → guard `pending|approved→cancelled`; same error set
- `app.fn_list_bookings(p_tenant_id, p_status, p_limit, p_offset)` → `data.bookings: [...]` ordered by `created_at`

`data.booking` fields mirror `BookingDTO`: id, tenant_id, owner_id, status,
reference, resource_id, scheduled_at, created_at, updated_at, version.
