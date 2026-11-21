#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Run the Yoink backend (yoink-core) and frontend together with one command.

    python scripts/dev.py                 # backend :8756, frontend :5173
    python scripts/dev.py --api-port 8010 --web-port 5180

Builds + runs the Rust backend with `cargo run`, starts the Vite dev server,
points the frontend at the chosen backend port, and shuts both down cleanly on
Ctrl+C. Cross-platform (Linux + Windows).

The backend shells out to `yt-dlp` and `ffmpeg`: it uses the bundled
`backend/vendor/ffmpeg` when present (set up by scripts/build_ffmpeg.sh) and
otherwise falls back to whatever is on PATH; `yt-dlp` must be on PATH (or set
YOINK_YTDLP) for a dev run.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "backend-rs"
VENDOR_FFMPEG = ROOT / "backend" / "vendor" / "ffmpeg"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Yoink (backend + frontend).")
    parser.add_argument("--api-port", type=int, default=8756)
    parser.add_argument("--web-port", type=int, default=5173)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--release", action="store_true", help="build the backend in release mode")
    args = parser.parse_args()

    api_base = f"http://{args.host}:{args.api_port}/api"
    npm = "npm.cmd" if os.name == "nt" else "npm"

    backend_cmd = ["cargo", "run"]
    if args.release:
        backend_cmd.append("--release")
    frontend_cmd = [npm, "run", "dev", "--", "--host", args.host, "--port", str(args.web_port)]

    # The backend reads these; ffmpeg is used bundled when available.
    backend_env = {**os.environ, "YOINK_PORT": str(args.api_port)}
    if VENDOR_FFMPEG.is_dir():
        backend_env["YOINK_FFMPEG"] = str(VENDOR_FFMPEG)

    print(f"> backend   http://{args.host}:{args.api_port}  (yoink-core)")
    print(f"> frontend  http://{args.host}:{args.web_port}")
    print("  Ctrl+C to stop both.\n")

    procs: list[subprocess.Popen[bytes]] = []
    try:
        procs.append(subprocess.Popen(backend_cmd, cwd=CORE, env=backend_env))
        # The frontend reads VITE_API_BASE_URL to find the backend.
        env = {**os.environ, "VITE_API_BASE_URL": api_base}
        procs.append(subprocess.Popen(frontend_cmd, cwd=ROOT, env=env))

        # Exit as soon as either process dies.
        while True:
            for proc in procs:
                code = proc.poll()
                if code is not None:
                    print(f"\n! A process exited (code {code}); shutting down.")
                    return code or 0
            try:
                procs[0].wait(timeout=1)
            except subprocess.TimeoutExpired:
                continue
    except KeyboardInterrupt:
        print("\n> stopping...")
        return 0
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT if os.name != "nt" else signal.SIGTERM)
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
