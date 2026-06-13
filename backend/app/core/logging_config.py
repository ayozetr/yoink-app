"""Application logging — structured logs to ``~/.yoink/logs/yoink.log`` + console.

A rotating file handler keeps a bounded on-disk history of what the backend did
(extractions, downloads, the yt-dlp error text that used to vanish), so a failed
download can actually be diagnosed after the fact. Everything is logged under the
``app`` namespace; modules use ``logging.getLogger(__name__)`` and propagate up.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.core.config import settings

_configured = False


def setup_logging() -> None:
    """Configure the ``app`` logger once: a rotating file + console handler."""
    global _configured
    if _configured:
        return

    log_dir = settings.ensure_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        log_dir / "yoink.log",
        maxBytes=2_000_000,  # ~2 MB per file
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.handlers.clear()
    app_logger.addHandler(file_handler)
    app_logger.addHandler(console_handler)
    app_logger.propagate = False  # don't double-log through the root logger

    _configured = True
