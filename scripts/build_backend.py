#!/usr/bin/env python3
"""Bundle the FastAPI backend into a one-folder distribution (Tauri resource).

    python scripts/build_backend.py

Runs PyInstaller (from the backend venv) on `run_backend.py`, collecting the
yt-dlp extractors and uvicorn internals that are imported dynamically, then
copies the resulting `yoink-backend/` folder to `src-tauri/binaries/yoink-backend/`,
which `tauri.conf.json` bundles as a resource. `main.rs` launches the exe inside
it directly.

Uses PyInstaller **`--onedir`** (a folder), not `--onefile`: a one-file binary
re-extracts its whole ~180 MB payload to a temp dir on *every* launch (slow cold
start, notably on Windows), whereas the folder runs in place. It also removes the
bootloader→Python indirection, so the spawned exe *is* the backend process and
shutting it down is a plain kill.
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
VENDOR_FFMPEG = BACKEND / "vendor" / "ffmpeg"


def _ffmpeg_args() -> list[str]:
    """PyInstaller args to embed bundled ffmpeg/ffprobe + their license.

    Empty if `scripts/fetch_ffmpeg.py` hasn't been run — the app then falls
    back to a system ffmpeg on PATH.
    """
    if not VENDOR_FFMPEG.is_dir():
        print("  (no bundled ffmpeg; run scripts/fetch_ffmpeg.py to include it)")
        return []
    args: list[str] = []
    for name in ("ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"):
        binary = VENDOR_FFMPEG / name
        if binary.exists():
            # Place at the bundle root so ffmpeg_location() finds it.
            args += ["--add-binary", f"{binary}{os.pathsep}."]
    license_file = VENDOR_FFMPEG / "FFMPEG-LICENSE.txt"
    if license_file.exists():
        args += ["--add-data", f"{license_file}{os.pathsep}."]
    return args


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

    print(f"> Building backend (onedir) for {triple}...")
    subprocess.run(
        [
            py, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--onedir",
            "--name", "yoink-backend",
            "--collect-all", "yt_dlp",
            "--collect-all", "uvicorn",
            # curl_cffi ships native libs (libcurl-impersonate) that PyInstaller
            # won't pick up on its own; without them yt-dlp can't impersonate a
            # browser and Cloudflare-protected sites 403 in the packaged app.
            "--collect-all", "curl_cffi",
            "--collect-submodules", "app",
            "--hidden-import", "app.main",
            *_ffmpeg_args(),
            "run_backend.py",
        ],
        cwd=BACKEND,
        check=True,
    )

    built = BACKEND / "dist" / "yoink-backend"  # the onedir folder
    target = BINARIES / "yoink-backend"
    BINARIES.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(built, target)
    print(f"[OK] Backend ready: {target.relative_to(ROOT)}/ ({triple})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\n! Build step failed: {exc}")
        sys.exit(exc.returncode)
