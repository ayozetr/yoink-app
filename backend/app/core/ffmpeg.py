"""Locate the ffmpeg/ffprobe to hand to yt-dlp.

When the backend runs as a PyInstaller bundle, ffmpeg + ffprobe are unpacked
next to the app (see scripts/build_backend.py), and we point yt-dlp at them via
`ffmpeg_location`. In development (or if no ffmpeg was bundled), this returns
None and yt-dlp falls back to a system ffmpeg on PATH.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def ffmpeg_location() -> str | None:
    """Directory containing the bundled ffmpeg, or None to use the system one."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    return base if (Path(base) / exe).exists() else None


def ffprobe_path() -> str:
    """Path to ffprobe: the bundled one when packaged, else "ffprobe" on PATH."""
    exe = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    base = getattr(sys, "_MEIPASS", None)
    if base and (Path(base) / exe).exists():
        return str(Path(base) / exe)
    return exe
