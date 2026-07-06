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
