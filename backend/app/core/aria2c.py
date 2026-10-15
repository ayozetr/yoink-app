# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Locate an aria2c binary to hand yt-dlp as an external downloader.

aria2c opens several byte-range connections to one file, which can bypass a
per-connection speed cap on hosts that allow range requests. It's opt-in
(``AppSettings.use_aria2c``) and resolved in this order:

  1. a **bundled** ``aria2c`` next to the PyInstaller backend (``sys._MEIPASS``),
     if a future build ships one in ``backend/vendor/aria2/`` — zero-config;
  2. a system ``aria2c`` on ``PATH`` (``shutil.which``);
  3. ``None`` — not available, so the feature degrades to a no-op.

Nothing is bundled today (aria2 has no official static Linux binary), so this
uses the system aria2c when present; dropping a binary into the vendor dir later
makes it zero-config with no code change.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def aria2c_path() -> str | None:
    """Path to an aria2c binary (bundled or on PATH), or None if unavailable."""
    exe = "aria2c.exe" if os.name == "nt" else "aria2c"
    base = getattr(sys, "_MEIPASS", None)
    if base and (Path(base) / exe).exists():
        return str(Path(base) / exe)
    return shutil.which(exe)


def aria2c_available() -> bool:
    """Whether an aria2c binary can be found (for the Settings UI to reflect)."""
    return aria2c_path() is not None
