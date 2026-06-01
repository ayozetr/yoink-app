"""Entry point for the packaged backend (PyInstaller sidecar).

The Tauri desktop shell launches this as a sidecar. The port defaults to 8000
(what the bundled frontend expects) but can be overridden with YOINK_PORT.
"""

from __future__ import annotations

import os

import uvicorn

from app.main import app

if __name__ == "__main__":
    port = int(os.environ.get("YOINK_PORT", "8756"))
    uvicorn.run(app, host="127.0.0.1", port=port)
