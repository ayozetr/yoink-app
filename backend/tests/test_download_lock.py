"""The process-wide download lock serializes concurrent download jobs.

Two ``download_events`` generators driven at once must not run their yt-dlp
workers simultaneously — otherwise two jobs could write the same ``.part`` file
in the shared download folder and corrupt each other.
"""

from __future__ import annotations

import asyncio
import contextlib
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


def test_queued_download_aborts_on_client_disconnect(temp_dirs, monkeypatch):
    """A second job blocked on the lock aborts when its client disconnects, instead
    of hanging until the first job finishes — the acquire races the disconnect."""
    gate = threading.Event()  # the first job's fake download blocks here
    out_file = temp_dirs / "x.mp3"

    class SlowYDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=True):
            gate.wait(timeout=5)  # hold the lock until the test releases it
            out_file.write_bytes(b"x")
            return {"id": "x", "title": "x"}

        def sanitize_info(self, info):
            return info

        def prepare_filename(self, info):
            return str(out_file)

    monkeypatch.setattr(download_service, "YoutubeDL", SlowYDL)
    monkeypatch.setattr(download_service, "register_threads_ie", lambda ydl: None)
    monkeypatch.setattr(download_service, "register_embedded_vr", lambda ydl: None)
    monkeypatch.setattr(download_service, "_final_path", lambda info: None)
    # The module-global asyncio.Lock binds to the first event loop that uses it, so
    # give this test (its own asyncio.run) a fresh lock — otherwise it clashes with
    # another lock test's already-closed loop. In production there's a single loop.
    monkeypatch.setattr(download_service, "_download_lock", asyncio.Lock())

    async def run():
        req = DownloadRequest(url="https://example.com/x", kind="audio")
        # Job 1 acquires and holds the lock.
        agen1 = download_service.download_events(req, threading.Event())
        pull1 = asyncio.create_task(agen1.__anext__())
        for _ in range(200):
            if download_service._download_lock.locked():
                break
            await asyncio.sleep(0.01)
        assert download_service._download_lock.locked()

        # Job 2 queues behind the lock, with a disconnect signal.
        disconnect = asyncio.Event()
        agen2 = download_service.download_events(req, threading.Event(), disconnect)
        pull2 = asyncio.create_task(agen2.__anext__())
        await asyncio.sleep(0.05)
        assert not pull2.done(), "job 2 should be blocked on the lock"

        # Its client disconnects: the acquire loses the race and the job ends with no
        # terminal event (StopAsyncIteration) rather than hanging on the lock.
        disconnect.set()
        with contextlib.suppress(StopAsyncIteration):
            await asyncio.wait_for(pull2, timeout=1)
        assert pull2.done(), "job 2 must abort on disconnect, not hang on the lock"
        # Job 1 is untouched and still holds the lock.
        assert download_service._download_lock.locked()

        gate.set()  # let job 1 finish
        pull1.cancel()
        with contextlib.suppress(BaseException):
            await pull1
        await asyncio.sleep(0.1)

    try:
        asyncio.run(run())
    finally:
        gate.set()
