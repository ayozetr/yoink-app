"""ffmpeg binary resolution: bundled vs PATH.

Guards the bug where the WebP→JPEG cover converter built a bare ``{dir}/ffmpeg``
path that misses the ``.exe`` suffix inside a packaged Windows bundle. The fix
routes through ``ffmpeg_path()``, which appends the platform's exe name (mirroring
``ffprobe_path``). Note: the Windows ``.exe`` branch can't be unit-tested on a
posix host — pathlib refuses to build a WindowsPath — so we exercise the bundled
resolution with the host platform's own exe name.
"""

from __future__ import annotations

import os
import sys

from app.core import ffmpeg as ff


def test_ffmpeg_path_falls_back_to_bare_name_when_unbundled(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    # Bare name → subprocess resolves it via PATH ("ffmpeg.exe" on Windows).
    assert ff.ffmpeg_path() == ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")


def test_ffmpeg_path_bundled_returns_joined_binary(tmp_path, monkeypatch):
    # When packaged, the bundled binary path is returned — joined with the
    # platform's exe name (the .exe suffix on Windows, which the cover converter
    # relies on), not a bare "{dir}/ffmpeg".
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    (tmp_path / exe).write_bytes(b"")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert ff.ffmpeg_path() == str(tmp_path / exe)


def test_ffmpeg_path_bundled_missing_binary_falls_back(tmp_path, monkeypatch):
    # _MEIPASS set but no ffmpeg there → fall back to the bare name (PATH).
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert ff.ffmpeg_path() == ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
