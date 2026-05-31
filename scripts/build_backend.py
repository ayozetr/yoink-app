#!/usr/bin/env python3
"""Bundle the FastAPI backend into a single-file binary (Tauri sidecar).

    python scripts/build_backend.py

Runs PyInstaller (from the backend venv) on `run_backend.py`, collecting the
yt-dlp extractors and uvicorn internals that are imported dynamically, then
copies the result to `src-tauri/binaries/yoink-backend-<target-triple>` — the
name Tauri expects for an `externalBin` sidecar.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
BINARIES = ROOT / "src-tauri" / "binaries"


def _venv_python() -> str:
    win = BACKEND / ".venv" / "Scripts" / "python.exe"
    nix = BACKEND / ".venv" / "bin" / "python"
    return str(win if os.name == "nt" else nix)


def _target_triple() -> str:
    """The Rust host target triple Tauri uses to name the sidecar."""
    out = subprocess.run(
        ["rustc", "-Vv"], capture_output=True, text=True, check=True
    ).stdout
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("Could not determine the Rust host target triple.")


def main() -> int:
    py = _venv_python()
    triple = _target_triple()
    exe_suffix = ".exe" if os.name == "nt" else ""

    print(f"▸ Building backend sidecar for {triple}…")
    subprocess.run(
        [
            py, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--onefile",
            "--name", "yoink-backend",
            "--collect-all", "yt_dlp",
            "--collect-all", "uvicorn",
            "--collect-submodules", "app",
            "--hidden-import", "app.main",
            "run_backend.py",
        ],
        cwd=BACKEND,
        check=True,
    )

    built = BACKEND / "dist" / f"yoink-backend{exe_suffix}"
    BINARIES.mkdir(parents=True, exist_ok=True)
    target = BINARIES / f"yoink-backend-{triple}{exe_suffix}"
    shutil.copy2(built, target)
    print(f"✓ Sidecar ready: {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\n! Build step failed: {exc}")
        sys.exit(exc.returncode)
