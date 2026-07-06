"""Persistence infrastructure (Track A: asyncpg + Postgres).

The ONLY packages allowed to import asyncpg are this one and each feature
module's `infrastructure/`. Application, domain, and API code depend on
repository Protocols (ports), never on the engine. No FastAPI imports here.
"""
