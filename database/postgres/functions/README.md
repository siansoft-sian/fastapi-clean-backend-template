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
