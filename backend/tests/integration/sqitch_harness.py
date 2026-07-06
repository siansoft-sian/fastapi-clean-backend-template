"""Applies the REAL sqitch migrations from database/postgres/ for integration tests.

Replaces the M3 test-only scaffold: integration tests now exercise the exact
deploy/revert/verify scripts that ship. The harness parses `sqitch.plan`,
resolves psql `\\ir`/`\\i` includes script-relative, and executes each change
via asyncpg (sqitch itself is not required on the test machine — it remains
the system of record for real deployments).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import asyncpg

POSTGRES_TEST_DSN = os.environ.get("POSTGRES_TEST_DSN", "postgresql://app:app@localhost:5432/app")

SQITCH_ROOT = Path(__file__).resolve().parents[3] / "database" / "postgres"
PLAN_FILE = SQITCH_ROOT / "sqitch.plan"

_INCLUDE_RE = re.compile(r"^\\ir?\s+(?P<path>\S+)\s*$", re.MULTILINE)


def plan_changes() -> list[str]:
    """Change names from sqitch.plan, in plan order."""
    changes: list[str] = []
    for raw_line in PLAN_FILE.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("%", "#")):
            continue
        changes.append(line.split()[0])
    return changes


def read_sql(script: Path) -> str:
    """Script text with ``\\ir``/``\\i`` includes resolved relative to the script."""
    text = script.read_text()

    def _resolve(match: re.Match[str]) -> str:
        include = (script.parent / match.group("path")).resolve()
        return read_sql(include)

    return _INCLUDE_RE.sub(_resolve, text)


async def deploy_all(connection: asyncpg.Connection) -> None:
    for change in plan_changes():
        await connection.execute(read_sql(SQITCH_ROOT / "deploy" / f"{change}.sql"))


async def verify_all(connection: asyncpg.Connection) -> None:
    """Run every verify script; each raises on failure (sqitch convention)."""
    for change in plan_changes():
        await connection.execute(read_sql(SQITCH_ROOT / "verify" / f"{change}.sql"))


async def revert_all(connection: asyncpg.Connection) -> None:
    for change in reversed(plan_changes()):
        await connection.execute(read_sql(SQITCH_ROOT / "revert" / f"{change}.sql"))


async def reset_and_deploy(dsn: str = POSTGRES_TEST_DSN) -> None:
    """Fresh state for a test: drop the app schema and deploy every change."""
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute("DROP SCHEMA IF EXISTS app CASCADE")
        await deploy_all(connection)
    finally:
        await connection.close()
