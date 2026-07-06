#!/usr/bin/env bash
# Fast gate: every check that must be green before a commit lands.
# Usage: ./scripts/self_test.sh   (override the interpreter with PYTHON=...)
set -euo pipefail

cd "$(dirname "$0")/../backend"

PYTHON="${PYTHON:-.venv/bin/python}"
BIN="$(dirname "$PYTHON")"

echo "==> compileall"
"$PYTHON" -m compileall -q app

echo "==> ruff check"
"$BIN/ruff" check .

echo "==> ruff format --check"
"$BIN/ruff" format --check .

echo "==> mypy"
"$BIN/mypy" app

echo "==> lint-imports"
"$BIN/lint-imports"

echo "==> pytest (fast suite: -m 'not integration')"
"$BIN/pytest" -m "not integration" -q

echo "==> ALL GATES GREEN"
