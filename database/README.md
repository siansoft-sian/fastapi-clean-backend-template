# database/

The PostgreSQL side of the template. **FastAPI never reads this folder at
runtime** — the application only calls the functions the migrations create.

```
postgres/                     the sqitch project (system of record)
  sqitch.plan / sqitch.conf
  deploy/ revert/ verify/     one triplet per change; verify raises on failure
  procedures/                 function bodies (single source, \ir-included)
  schema/                     table DDL (single source, \ir-included)
  DESIGN-sessions-identity.md the sessions + identity contract (start here)
  functions/README.md         pointer + ground rules
```

Deploy with `sqitch deploy db:pg://…`. Integration tests apply these exact
scripts via `backend/tests/integration/sqitch_harness.py`, so the test suite
always exercises what ships.
