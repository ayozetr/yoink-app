"""Cancelling mid-merge frees the download lock without waiting for the worker.

yt-dlp's ffmpeg merge can't be interrupted once it's running, so a cancel during
the merge leaves the worker blocked until ffmpeg finishes. The download lock must
not be held that whole time, or the next download sits silently at 0%.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading

from app.core.config import settings
from app.models.media import DownloadRequest
from app.services import download_service as ds


def test_lock_freed_on_cancel_before_slow_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "download_dir", tmp_path)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    gate = threading.Event()  # the fake "ffmpeg merge" blocks until released

    class _SlowYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=True):
            # Simulate a long ffmpeg merge that ignores the cancel flag.
            gate.wait(timeout=5)
            return {"title": "x", "ext": "mp3"}

        def sanitize_info(self, info):
            return info

        def prepare_filename(self, info):
            return str(tmp_path / "x.mp3")

    monkeypatch.setattr(ds, "YoutubeDL", _SlowYDL)
    monkeypatch.setattr(ds, "register_threads_ie", lambda ydl: None)
    monkeypatch.setattr(ds, "register_embedded_vr", lambda ydl: None)
    monkeypatch.setattr(ds, "_final_path", lambda info: None)

    async def run():
        assert not ds._download_lock.locked()
        agen = ds.download_events(
            DownloadRequest(url="https://example.com/x", kind="audio"),
            threading.Event(),
        )
        pull = asyncio.create_task(agen.__anext__())
        # Wait until the worker is running (it holds the lock).
        for _ in range(200):
            if ds._download_lock.locked():
                break
            await asyncio.sleep(0.01)
        assert ds._download_lock.locked(), "the worker should hold the download lock"

        # Cancel mid-"merge": this runs the generator's finally.
        pull.cancel()
        for _ in range(200):
            if not ds._download_lock.locked():
                break
            await asyncio.sleep(0.01)
        assert not ds._download_lock.locked(), (
            "the lock must be freed on cancel, not held until the merge finishes"
        )

        gate.set()  # let the orphaned worker thread finish
        with contextlib.suppress(BaseException):
            await pull
        await asyncio.sleep(0.1)

    try:
        asyncio.run(run())
    finally:
        gate.set()
