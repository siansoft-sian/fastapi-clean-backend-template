# database/

Schema and migrations for the PostgreSQL database. **FastAPI never reads this
folder at runtime** — it exists for humans and migration tooling only.

## How migrations are applied

- Migrations under `postgres/migrations/` are applied with **sqitch** (see the
  `sqitch-migration-engineer` skill) or via the **Supabase MCP** tool
  (`apply_migration`) when the target is a Supabase project.
- The application process never runs DDL. Repositories only ever call the
  tables/functions that migrations have already created.
- The first real migration arrives with the first real feature module; the
  folder is empty until then.

## The one deliberate exception

`app/modules/_example/` (throwaway scaffolding proving the repository seam)
creates its own `_example_items` table via `CREATE TABLE IF NOT EXISTS` in
`ensure_schema()`, because it predates the migration tooling being wired.
Real modules must NOT copy that shortcut — they get schema from migrations
here and call the resulting DB functions.
