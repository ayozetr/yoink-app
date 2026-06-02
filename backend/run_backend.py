"""Entry point for the packaged backend (PyInstaller sidecar).

The Tauri desktop shell launches this as a sidecar. The port defaults to 8756
(what the bundled frontend expects) but can be overridden with YOINK_PORT.
"""

from __future__ import annotations

import os
import sys
import threading

import uvicorn

from app.main import app


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


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        threading.Thread(
            target=_exit_when_parent_closes_stdin, daemon=True
        ).start()
    port = int(os.environ.get("YOINK_PORT", "8756"))
    uvicorn.run(app, host="127.0.0.1", port=port)
