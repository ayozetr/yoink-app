#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Build the Rust backend (`yoink-core`) and assemble the bundle resource.

    python scripts/build_core.py

Compiles `backend-rs` in release mode and lays out
`src-tauri/binaries/core/` with the three binaries the shipped app needs:

  - `yoink-core`  — the Rust backend (axum; orchestrates the two below)
  - `yt-dlp`      — the official standalone binary, pinned to the same version as
                    `scripts/ytdlp-version.txt` (no Python runtime needed)
  - `ffmpeg` + `ffprobe` — from `backend/vendor/ffmpeg/` (run `build_ffmpeg.sh` once)

`tauri.conf.json` bundles that folder as the `core` resource; `main.rs` launches
`yoink-core` from it and points it at the sibling `yt-dlp`/`ffmpeg` via
`YOINK_YTDLP`/`YOINK_FFMPEG`. This replaces the old PyInstaller backend build.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "backend-rs"
DEST = ROOT / "src-tauri" / "binaries" / "core"
VENDOR_FFMPEG = ROOT / "backend" / "vendor" / "ffmpeg"


def _ytdlp_version() -> str:
    """The pinned yt-dlp release to bundle — bump scripts/ytdlp-version.txt to
    update it (the app ships the official standalone binary; yt-dlp is
    owner-managed, never self-updated in-app)."""
    pin = (ROOT / "scripts" / "ytdlp-version.txt").read_text(encoding="utf-8").strip()
    m = re.fullmatch(r"[0-9.]+", pin)
    if not m:
        raise SystemExit("! scripts/ytdlp-version.txt must contain a version like 2026.10.26")
    return pin


def _ytdlp_asset() -> str:
    if os.name == "nt":
        return "yt-dlp.exe"
    if platform.system() == "Darwin":
        return "yt-dlp_macos"
    return "yt-dlp_linux"


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    print("> Building yoink-core (release)...")
    subprocess.run(["cargo", "build", "--release"], cwd=CORE, check=True)

    exe_name = "yoink-core.exe" if os.name == "nt" else "yoink-core"
    built = CORE / "target" / "release" / exe_name
    if not built.exists():
        raise SystemExit(f"! {built} not found after build")

    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    shutil.copy2(built, DEST / exe_name)

    # yt-dlp: the official standalone binary pinned to requirements.txt's version.
    version = _ytdlp_version()
    asset = _ytdlp_asset()
    ytdlp_name = "yt-dlp.exe" if os.name == "nt" else "yt-dlp"
    url = f"https://github.com/yt-dlp/yt-dlp/releases/download/{version}/{asset}"
    out = DEST / ytdlp_name
    print(f"> Downloading yt-dlp {version} ({asset})...")
    urllib.request.urlopen(url)  # noqa: S310 — trusted host  # fail fast on a bad URL
    urllib.request.urlretrieve(url, out)
    _make_executable(out)

    # ffmpeg + ffprobe from the vendored LGPL builds.
    if not VENDOR_FFMPEG.is_dir():
        print("  ! backend/vendor/ffmpeg not found — run scripts/fetch_ffmpeg.py first.")
    for name in ("ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"):
        src = VENDOR_FFMPEG / name
        if src.exists():
            dst = DEST / name
            shutil.copy2(src, dst)
            _make_executable(dst)

    print(f"[OK] core assembled: {DEST.relative_to(ROOT)}/")
    for f in sorted(DEST.iterdir()):
        print(f"    {f.name}  ({f.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\n! Build step failed: {exc}")
        sys.exit(exc.returncode)
