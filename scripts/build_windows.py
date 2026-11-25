#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Build the Windows package: the signed NSIS setup .exe.

    python scripts/build_windows.py

The Windows counterpart of ``build_egui_appimage.sh``. It:

  1. fetches a prebuilt LGPL ffmpeg/ffprobe for win64 (``scripts/ffmpeg-windows.txt``)
     into ``backend/vendor/ffmpeg`` if they're not already there;
  2. runs ``build_core.py`` to assemble ``yoink-core.exe`` + ``yt-dlp.exe`` +
     ``ffmpeg.exe`` + ``ffprobe.exe`` (DEST = ``desktop/target/core``);
  3. builds the egui app (``yoink-desktop.exe``);
  4. lays out ``desktop/target/windows/dist`` with those five binaries;
  5. runs ``makensis`` on ``desktop/packaging/windows/yoink.nsi`` to produce
     ``desktop/target/windows/Yoink_<ver>_x64-setup.exe``.

Sign the result with ``cargo tauri signer sign`` (the same minisign key the
legacy Tauri updater trusts) — the release workflow does this. Meant to run on
Windows (it builds native .exe binaries).
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "desktop"
VENDOR_FFMPEG = ROOT / "backend" / "vendor" / "ffmpeg"
CORE_BUNDLE = DESKTOP / "target" / "core"
OUT_DIR = DESKTOP / "target" / "windows"
DIST = OUT_DIR / "dist"
NSI = DESKTOP / "packaging" / "windows" / "yoink.nsi"

BINARIES = (
    "yoink-desktop.exe",
    "yoink-core.exe",
    "yt-dlp.exe",
    "ffmpeg.exe",
    "ffprobe.exe",
)


def _version() -> str:
    cargo = (DESKTOP / "Cargo.toml").read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', cargo)
    if not m:
        raise SystemExit("! could not read version from desktop/Cargo.toml")
    return m.group(1)


def fetch_ffmpeg() -> None:
    """Vendor ffmpeg.exe + ffprobe.exe and their shared DLLs into
    backend/vendor/ffmpeg (download if absent). We use the *shared* LGPL build
    (small exes + shared DLLs) rather than the static one, which halves the
    installer — avcodec/avformat/… aren't duplicated into each .exe. ffplay is
    skipped (Yoink never plays media)."""
    have = (VENDOR_FFMPEG / "ffmpeg.exe").exists() and (VENDOR_FFMPEG / "ffprobe.exe").exists()
    if have:
        print("> ffmpeg/ffprobe (win64) already vendored")
        return
    url = (ROOT / "scripts" / "ffmpeg-windows.txt").read_text(encoding="utf-8").strip()
    if not url:
        raise SystemExit("! scripts/ffmpeg-windows.txt is empty")
    VENDOR_FFMPEG.mkdir(parents=True, exist_ok=True)
    print(f"> Downloading ffmpeg (win64, LGPL shared): {url}")
    with urllib.request.urlopen(url) as resp:  # noqa: S310 — pinned, trusted host
        blob = resp.read()
    got_exes = set()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            name = member.rsplit("/", 1)[-1]
            under_bin = "/bin/" in member
            want = under_bin and (
                name in ("ffmpeg.exe", "ffprobe.exe") or name.endswith(".dll")
            )
            if not want:
                continue  # skip ffplay.exe, docs, presets, …
            dst = VENDOR_FFMPEG / name
            dst.write_bytes(zf.read(member))
            print(f"  extracted {name} ({dst.stat().st_size // 1024} KiB)")
            if name in ("ffmpeg.exe", "ffprobe.exe"):
                got_exes.add(name)
    missing = {"ffmpeg.exe", "ffprobe.exe"} - got_exes
    if missing:
        raise SystemExit(f"! did not find {missing} in the ffmpeg zip")


def _find_makensis() -> str:
    exe = shutil.which("makensis")
    if exe:
        return exe
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            cand = Path(base) / "NSIS" / "makensis.exe"
            if cand.exists():
                return str(cand)
    raise SystemExit("! makensis not found (install NSIS, e.g. `choco install nsis`)")


def main() -> int:
    version = _version()
    print(f"> Yoink Windows package {version}")

    fetch_ffmpeg()

    # 1 + 2: backend bundle (yoink-core + yt-dlp + ffmpeg/ffprobe) → desktop/target/core
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_core.py")], check=True)

    # 3: the egui app
    print("> Building yoink-desktop (release)...")
    subprocess.run(["cargo", "build", "--release"], cwd=DESKTOP, check=True)

    # 4: lay out dist/ with the five binaries
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    sources = {
        "yoink-desktop.exe": DESKTOP / "target" / "release" / "yoink-desktop.exe",
        "yoink-core.exe": CORE_BUNDLE / "yoink-core.exe",
        "yt-dlp.exe": CORE_BUNDLE / "yt-dlp.exe",
        "ffmpeg.exe": CORE_BUNDLE / "ffmpeg.exe",
        "ffprobe.exe": CORE_BUNDLE / "ffprobe.exe",
    }
    for name in BINARIES:
        src = sources[name]
        if not src.exists():
            raise SystemExit(f"! missing build output: {src}")
        shutil.copy2(src, DIST / name)
        print(f"  {name}  ({(DIST / name).stat().st_size // 1024} KiB)")
    # The shared ffmpeg build's DLLs (installed beside ffmpeg.exe).
    for dll in sorted(CORE_BUNDLE.glob("*.dll")):
        shutil.copy2(dll, DIST / dll.name)
        print(f"  {dll.name}  ({(DIST / dll.name).stat().st_size // 1024} KiB)")

    # 5: NSIS installer
    makensis = _find_makensis()
    print(f"> makensis: {makensis}")
    setup = OUT_DIR / f"Yoink_{version}_x64-setup.exe"
    subprocess.run(
        [
            makensis,
            f"-DVERSION={version}",
            f"-DSRCDIR={DIST}",
            f"-DOUTFILE={setup}",
            str(NSI),
        ],
        cwd=OUT_DIR,
        check=True,
    )
    if not setup.exists():
        raise SystemExit(f"! installer not produced: {setup}")
    print(f"[OK] {setup.relative_to(ROOT)}  ({setup.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"! build step failed: {exc}")
