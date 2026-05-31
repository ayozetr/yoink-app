#!/usr/bin/env python3
"""One-time setup: create the backend venv, install all dependencies.

    python scripts/setup.py

Creates `backend/.venv`, installs the Python requirements into it, and runs
`npm install` for the frontend. Safe to re-run. Cross-platform (Linux+Windows).
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
VENV = BACKEND / ".venv"


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"  $ {' '.join(cmd)}  (in {cwd})")
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    print("▸ Creating backend virtualenv…")
    if not _venv_python().exists():
        venv.create(VENV, with_pip=True)

    print("▸ Installing backend dependencies…")
    py = str(_venv_python())
    _run([py, "-m", "pip", "install", "--upgrade", "pip"], BACKEND)
    _run([py, "-m", "pip", "install", "-r", "requirements.txt"], BACKEND)
    if (BACKEND / "requirements-dev.txt").exists():
        _run([py, "-m", "pip", "install", "-r", "requirements-dev.txt"], BACKEND)

    print("▸ Installing frontend dependencies…")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    _run([npm, "install"], ROOT)

    print("\n✓ Setup complete. Start everything with:  python scripts/dev.py")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\n! Setup step failed: {exc}")
        sys.exit(exc.returncode)
