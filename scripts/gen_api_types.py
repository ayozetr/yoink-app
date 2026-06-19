#!/usr/bin/env python3
"""Generate TypeScript types from the backend's OpenAPI schema.

Writes ``src/types/api.generated.ts`` from FastAPI's live schema via
``openapi-typescript`` — run through ``npx`` so it isn't a project devDep (it
still peers on TypeScript 5.x while the app is on 6.x).

Run with the backend venv's Python, from the repo root:

    backend/.venv/bin/python scripts/gen_api_types.py

The generated file is reference-only (gitignored). The *enforced* contract is
``backend/tests/test_type_contract.py``, which checks the hand-written
``src/types/*.ts`` against the Pydantic models on every test run.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
OUT = ROOT / "src" / "types" / "api.generated.ts"


def main() -> int:
    sys.path.insert(0, str(BACKEND))
    try:
        from app.main import app
    except ImportError as exc:  # pragma: no cover - guidance only
        print(f"Run this with the backend venv's Python ({exc}).", file=sys.stderr)
        return 1

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(app.openapi(), fh)
        schema = fh.name

    result = subprocess.run(
        ["npx", "-y", "openapi-typescript", schema, "-o", str(OUT)],
        cwd=ROOT,
        check=False,
    )
    if result.returncode == 0:
        print(f"Wrote {OUT.relative_to(ROOT)}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
