#!/usr/bin/env python3
"""One-time setup: create the backend venv, install all dependencies.

    python scripts/setup.py

Creates `backend/.venv`, installs the Python requirements into it, and runs
`npm install` for the frontend. Safe to re-run. Cross-platform (Linux+Windows).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
VENV = BACKEND / ".venv"


def _find_python313() -> str | None:
    """Locate a Python 3.13 interpreter — the version the backend is pinned to.

    The backend needs 3.13 (not the bleeding-edge 3.14) so `curl_cffi`'s
    impersonation works, which lets yt-dlp get past Cloudflare/anti-bot 403s.
    Prefer uv's managed 3.13 (fully isolated — it does NOT touch the system
    Python), then a `python3.13` on PATH. Returns None if neither is present.
    """
    uv = shutil.which("uv")
    if uv:
        try:
            out = subprocess.run(
                [uv, "python", "find", "3.13"],
                capture_output=True,
                text=True,
                check=True,
            )
            path = out.stdout.strip()
            if path:
                return path
        except (subprocess.CalledProcessError, OSError):
            pass
    return shutil.which("python3.13")


def _runtime_python(py: str) -> str:
    """Return a Python whose libpython is safe to bundle into the sidecar.

    uv's standalone Python ships `libpython` with an executable stack (RWE).
    PyInstaller `dlopen`s it at runtime and a hardened kernel then refuses to
    start the packaged sidecar ("cannot enable executable stack"). On Linux, if
    `patchelf` is available, copy the runtime into `backend/.python-rt` and clear
    the flag on the COPY (never uv's shared file), and build the venv from there.
    No-op on Windows/macOS or without patchelf.
    """
    if sys.platform != "linux":
        return py
    patchelf = shutil.which("patchelf")
    if not patchelf:
        print("  ! patchelf not found; the packaged Linux sidecar may fail to "
              "start (executable-stack). Install patchelf for release builds.")
        return py
    dest = BACKEND / ".python-rt"
    if not (dest / "bin").exists():
        home = Path(py).resolve().parents[1]
        print("> Copying the Python runtime and clearing its executable stack "
              "(so the packaged Linux sidecar can start)...")
        shutil.copytree(home, dest, symlinks=True)
        for lib in (dest / "lib").glob("libpython3.*.so*"):
            if not lib.is_symlink():
                subprocess.run([patchelf, "--clear-execstack", str(lib)], check=False)
    candidate = dest / "bin" / Path(py).name
    return str(candidate) if candidate.exists() else py


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"  $ {' '.join(cmd)}  (in {cwd})")
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    print("> Creating backend virtualenv (Python 3.13)...")
    if not _venv_python().exists():
        py313 = _find_python313()
        if py313:
            py313 = _runtime_python(py313)  # clear execstack on Linux (copy)
            _run([py313, "-m", "venv", str(VENV)], BACKEND)
        else:
            print(
                "  ! Python 3.13 not found. The backend needs it for "
                "curl_cffi/impersonate (getting past Cloudflare 403s).\n"
                "    Install it with `uv python install 3.13` and re-run, or\n"
                "    continue on the current interpreter (some sites may 403)."
            )
            venv.create(VENV, with_pip=True)

    print("> Installing backend dependencies...")
    py = str(_venv_python())
    _run([py, "-m", "pip", "install", "--upgrade", "pip"], BACKEND)
    _run([py, "-m", "pip", "install", "-r", "requirements.txt"], BACKEND)
    if (BACKEND / "requirements-dev.txt").exists():
        _run([py, "-m", "pip", "install", "-r", "requirements-dev.txt"], BACKEND)

    print("> Installing frontend dependencies...")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    _run([npm, "install"], ROOT)

    print("\n[OK] Setup complete. Start everything with:  python scripts/dev.py")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\n! Setup step failed: {exc}")
        sys.exit(exc.returncode)
