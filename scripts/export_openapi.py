#!/usr/bin/env python3
"""Write backend/openapi.json from create_app().openapi() — no running server needed.

Usage: backend/.venv/bin/python scripts/export_openapi.py [output-path]
"""

import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("APP_ENV", "testing")

from app.app import create_app  # noqa: E402


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND_DIR / "openapi.json"
    schema = create_app().openapi()
    output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
