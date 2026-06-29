"""The process-wide download lock serializes concurrent download jobs.

Two ``download_events`` generators driven at once must not run their yt-dlp
workers simultaneously — otherwise two jobs could write the same ``.part`` file
in the shared download folder and corrupt each other.
"""

from __future__ import annotations

import asyncio
import threading
import time

from app.models.media import DownloadRequest
from app.services import download_service


def test_concurrent_downloads_are_serialized(temp_dirs, monkeypatch):
    state = {"active": 0, "max": 0}
    guard = threading.Lock()
    out_file = temp_dirs / "x.mp3"

    class FakeYDL:
        """A stand-in for yt-dlp's YoutubeDL that records overlap while "downloading"."""

        def __init__(self, options):  # noqa: D401 — matches YoutubeDL(opts)
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=True):
            with guard:
                state["active"] += 1
                state["max"] = max(state["max"], state["active"])
            time.sleep(0.05)  # hold the "download" so an overlap would be observed
            out_file.write_bytes(b"x")
            with guard:
                state["active"] -= 1
            return {
                "id": "x",
                "title": "x",
                "requested_downloads": [{"filepath": str(out_file)}],
            }

        def sanitize_info(self, info):
            return info

        def prepare_filename(self, info):
            return str(out_file)

    monkeypatch.setattr(download_service, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(download_service, "register_threads_ie", lambda ydl: None)
    monkeypatch.setattr(download_service, "register_embedded_vr", lambda ydl: None)

    async def drive():
        async def consume(req):
            events = []
            async for event in download_service.download_events(req):
                events.append(event)
            return events

        req_a = DownloadRequest(url="https://example.com/a", kind="audio")
        req_b = DownloadRequest(url="https://example.com/b", kind="audio")
        return await asyncio.gather(consume(req_a), consume(req_b))

    results = asyncio.run(drive())

    # The lock must have serialized the two workers (never both active at once).
    assert state["max"] == 1, f"downloads overlapped (max concurrent={state['max']})"
    # Both jobs still ran to a terminal event.
    assert all(events and events[-1].type in ("completed", "error") for events in results)
