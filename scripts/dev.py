#!/usr/bin/env python3
"""Run the Yoink backend and frontend together with one command.

    python scripts/dev.py                 # backend :8000, frontend :5173
    python scripts/dev.py --api-port 8010 --web-port 5180

Starts uvicorn (with --reload) and the Vite dev server, points the frontend at
the chosen backend port, and shuts both down cleanly on Ctrl+C. Cross-platform
(Linux + Windows): it locates the backend virtualenv automatically.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"


def _venv_python() -> str:
    """Path to the backend venv's Python, or the current interpreter."""
    candidates = [
        BACKEND / ".venv" / "bin" / "python",  # Linux/macOS
        BACKEND / ".venv" / "Scripts" / "python.exe",  # Windows
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    print("! No backend venv found — run `python scripts/setup.py` first.")
    return sys.executable


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Yoink (backend + frontend).")
    parser.add_argument("--api-port", type=int, default=8756)
    parser.add_argument("--web-port", type=int, default=5173)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    api_base = f"http://{args.host}:{args.api_port}/api"
    npm = "npm.cmd" if os.name == "nt" else "npm"

    backend_cmd = [
        _venv_python(),
        "-m",
        "uvicorn",
        "app.main:app",
        "--reload",
        "--host",
        args.host,
        "--port",
        str(args.api_port),
    ]
    frontend_cmd = [
        npm,
        "run",
        "dev",
        "--",
        "--host",
        args.host,
        "--port",
        str(args.web_port),
    ]

    print(f"> backend   http://{args.host}:{args.api_port}  (docs at /docs)")
    print(f"> frontend  http://{args.host}:{args.web_port}")
    print("  Ctrl+C to stop both.\n")

    procs: list[subprocess.Popen[bytes]] = []
    try:
        procs.append(subprocess.Popen(backend_cmd, cwd=BACKEND))
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
