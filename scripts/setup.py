#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""One-time setup: build the Rust backend and install frontend dependencies.

    python scripts/setup.py

Runs `cargo build` for the backend (yoink-core) and `npm install` for the
frontend. Safe to re-run. Cross-platform (Linux + Windows).

Prereqs: the Rust toolchain (rustup) and Node.js. For a dev run you also need
`yt-dlp` on PATH and ffmpeg (bundle it once with `scripts/build_ffmpeg.sh`, or
use a system ffmpeg). Then start everything with `python scripts/dev.py`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "backend-rs"


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"  $ {' '.join(cmd)}  (in {cwd})")
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    print("> Building the Rust backend (yoink-core)...")
    _run(["cargo", "build"], CORE)

    print("> Installing frontend dependencies...")
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    _run([npm, "install"], ROOT)

    print("\n[OK] Setup complete. Start everything with:  python scripts/dev.py")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\n! Setup step failed: {exc}")
        sys.exit(exc.returncode)
