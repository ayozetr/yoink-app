#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres
"""Build the native egui desktop app and assemble a self-contained Linux bundle.

    python scripts/build_desktop.py            # release build + assemble
    python scripts/build_desktop.py --debug    # use existing debug binaries (for testing the layout)
    python scripts/build_desktop.py --skip-build

Produces ``dist/yoink-linux/`` with the three native binaries (``yoink-desktop``,
``yoink-minter``, ``yoink-core``) plus the bundled ``yt-dlp``/``ffmpeg``, a
``.desktop`` file, the icon, and ``install.sh``/``uninstall.sh``. Running
``sudo ./install.sh`` lays it out under ``/usr/lib/yoink`` with a
``/usr/bin/yoink-desktop`` symlink and registers the ``yoink://`` scheme — a
drop-in replacement for the Tauri bundle, with no WebView runtime.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "yoink-linux"
LIB = DIST / "lib"
CORE_BUNDLE = ROOT / "src-tauri" / "binaries" / "core"
VENDOR_FFMPEG = ROOT / "backend" / "vendor" / "ffmpeg"

CRATES = [
    ("desktop", "yoink-desktop"),
    ("desktop-minter", "yoink-minter"),
    ("backend-rs", "yoink-core"),
]
TOOLS = ("yt-dlp", "ffmpeg", "ffprobe")


def run(cmd: list, cwd: Path | None = None) -> None:
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=cwd, check=True)


def build() -> None:
    # The hidden-minter WebView embeds a Vite bundle — refresh it first.
    vite = ROOT / "node_modules" / ".bin" / "vite"
    if vite.exists():
        run([str(vite), "build", "--config", "desktop-minter/web/vite.config.mjs"], cwd=ROOT)
    for crate, _ in CRATES:
        run(["cargo", "build", "--release"], cwd=ROOT / crate)


def binary(crate: str, name: str, profile: str) -> Path:
    return ROOT / crate / "target" / profile / name


def assemble(profile: str) -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    LIB.mkdir(parents=True)

    for crate, name in CRATES:
        src = binary(crate, name, profile)
        if not src.exists():
            raise SystemExit(f"! missing {src} — build it first (drop --skip-build)")
        shutil.copy2(src, LIB / name)
        os.chmod(LIB / name, 0o755)

    # yt-dlp + ffmpeg/ffprobe: prefer the assembled core bundle, else the vendor dir.
    missing = []
    for tool in TOOLS:
        src = CORE_BUNDLE / tool
        if not src.exists():
            src = VENDOR_FFMPEG / tool
        if src.exists():
            shutil.copy2(src, LIB / tool)
            os.chmod(LIB / tool, 0o755)
        else:
            missing.append(tool)
    if missing:
        print(f"  ! not bundled (run scripts/build_core.py + build_ffmpeg.sh): {', '.join(missing)}")

    shutil.copy2(ROOT / "desktop" / "packaging" / "yoink.desktop", DIST / "yoink.desktop")
    shutil.copy2(ROOT / "desktop" / "assets" / "icon.png", DIST / "yoink.png")
    (DIST / "install.sh").write_text(INSTALL_SH)
    os.chmod(DIST / "install.sh", 0o755)
    (DIST / "uninstall.sh").write_text(UNINSTALL_SH)
    os.chmod(DIST / "uninstall.sh", 0o755)


INSTALL_SH = """#!/bin/sh
# Install Yoink (native) under $PREFIX (default /usr). Run with sudo for a system
# install, or set PREFIX=$HOME/.local for a per-user one.
set -eu
PREFIX="${PREFIX:-/usr}"
LIBDIR="$PREFIX/lib/yoink"
here="$(cd "$(dirname "$0")" && pwd)"

install -d "$LIBDIR"
cp -f "$here"/lib/* "$LIBDIR"/
chmod 755 "$LIBDIR"/*
install -d "$PREFIX/bin"
ln -sf "$LIBDIR/yoink-desktop" "$PREFIX/bin/yoink-desktop"
install -D -m644 "$here/yoink.desktop" "$PREFIX/share/applications/yoink.desktop"
install -D -m644 "$here/yoink.png" "$PREFIX/share/icons/hicolor/512x512/apps/yoink.png"

update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
gtk-update-icon-cache -q "$PREFIX/share/icons/hicolor" 2>/dev/null || true
echo "Yoink installed. Launch 'yoink-desktop' or pick Yoink from your menu."
echo "The yoink:// links from the browser extension now open this app."
"""

UNINSTALL_SH = """#!/bin/sh
set -eu
PREFIX="${PREFIX:-/usr}"
rm -rf "$PREFIX/lib/yoink"
rm -f "$PREFIX/bin/yoink-desktop"
rm -f "$PREFIX/share/applications/yoink.desktop"
rm -f "$PREFIX/share/icons/hicolor/512x512/apps/yoink.png"
update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
echo "Yoink removed."
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Assemble the native Yoink Linux bundle.")
    ap.add_argument("--debug", action="store_true", help="use existing debug binaries (testing)")
    ap.add_argument("--skip-build", action="store_true", help="don't cargo build, just assemble")
    args = ap.parse_args()

    profile = "debug" if args.debug else "release"
    if not args.debug and not args.skip_build:
        build()
    assemble(profile)

    print(f"\n✓ bundle at {DIST.relative_to(ROOT)}")
    print(f"  install:  cd {DIST.relative_to(ROOT)} && sudo ./install.sh")
    print("  the tree: lib/{yoink-desktop,yoink-minter,yoink-core,yt-dlp,ffmpeg,ffprobe} + yoink.desktop + yoink.png")


if __name__ == "__main__":
    sys.exit(main())
