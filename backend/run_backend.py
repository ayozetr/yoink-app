"""Entry point for the packaged backend (PyInstaller onedir binary).

The Tauri desktop shell launches this with **no arguments** to serve the local
API (port 8756 by default, override with ``YOINK_PORT``). Invoked **with**
arguments, the very same binary runs Yoink's command-line interface instead — so
the installed ``yoink-cli`` wrapper (``src-tauri/yoink-cli``) can offer a real
command line on a packaged install without shipping a second copy of the engine.
"""

from __future__ import annotations

import os
import sys
import threading


def _exit_when_parent_closes_stdin() -> None:
    """Shut down when the desktop shell (Tauri) goes away.

    Tauri launches this as a sidecar with its stdin wired to a pipe and closes
    that pipe when the app exits. Blocking on a read then returns EOF, which we
    use as a shutdown signal so the PyInstaller child doesn't linger holding
    port 8756 — and, on Windows, the on-disk exe, which would otherwise break
    the in-place updater.

    Only armed in the packaged build (``sys.frozen``), where Tauri owns our
    stdin. In development the server is launched straight from a terminal, where
    reading stdin would either block on the tty or hit an immediate EOF (e.g.
    stdin from /dev/null) and wrongly kill the server.
    """
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001 — any stdin error just means "stop watching".
        return
    os._exit(0)


def _serve() -> None:
    """Serve the FastAPI app under uvicorn (how the desktop shell launches us)."""
    import uvicorn

    from app.main import app

    if getattr(sys, "frozen", False):
        threading.Thread(
            target=_exit_when_parent_closes_stdin, daemon=True
        ).start()
    port = int(os.environ.get("YOINK_PORT", "8756"))
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv:
        # Arguments present → run the command-line interface. The `yoink-cli`
        # wrapper on a packaged install forwards here; Tauri always launches the
        # binary with *no* arguments, so its path only ever hits _serve() below.
        from app.cli import main as cli_main

        raise SystemExit(cli_main(argv))
    _serve()
