"""FastAPI clean backend template.

Track A: asyncpg + Postgres-first behind repository ports. The delivery layer
(FastAPI) and application code never know the database engine; only
infrastructure adapters do.
"""
