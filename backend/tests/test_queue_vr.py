"""The queue path tags immersive (VR) output.

The main panel sets ``is_vr`` + an explicit ``vr_layout`` from its preview; the
queue has no preview so it sets ``auto_vr`` and the download detects VR from the
resolved info, tagging only when found. ``is_vr`` takes precedence over ``auto_vr``.
"""

from __future__ import annotations

import asyncio
import threading

from app.core.config import settings
from app.models.media import CompletedEvent, DownloadRequest
from app.services import download_service as ds


def _fake_ydl(out_path):
    class FakeYDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=True):
            return {"id": "x", "title": "clip", "ext": "mp4"}

        def sanitize_info(self, info):
            return info

        def prepare_filename(self, info):
            return str(out_path)

    return FakeYDL


def _setup(monkeypatch, out):
    out.write_bytes(b"video")
    monkeypatch.setattr(settings, "nfo_sidecars", False)  # isolate the VR step
    monkeypatch.setattr(ds, "YoutubeDL", _fake_ydl(out))
    monkeypatch.setattr(ds, "register_threads_ie", lambda ydl: None)
    monkeypatch.setattr(ds, "register_embedded_vr", lambda ydl: None)
    monkeypatch.setattr(ds, "_final_path", lambda info: None)


async def _drain(request):
    events = []
    async for event in ds.download_events(request, threading.Event()):
        events.append(event)
    return events


def test_auto_vr_detects_and_tags(temp_dirs, monkeypatch):
    out = temp_dirs / "clip.mp4"
    _setup(monkeypatch, out)
    applied: list[tuple[str, str]] = []
    monkeypatch.setattr(ds, "detect_vr", lambda info, strict=True: (True, "360_tb"))
    monkeypatch.setattr(
        ds, "apply_vr", lambda file, layout: applied.append((str(file), layout)) or file
    )

    events = asyncio.run(
        _drain(DownloadRequest(url="https://example.com/x", kind="video", auto_vr=True))
    )

    assert applied == [(str(out), "360_tb")]  # tagged with the *detected* layout
    assert any(isinstance(e, CompletedEvent) for e in events)


def test_auto_vr_skips_when_not_detected(temp_dirs, monkeypatch):
    out = temp_dirs / "clip.mp4"
    _setup(monkeypatch, out)
    applied: list[int] = []
    monkeypatch.setattr(ds, "detect_vr", lambda info, strict=True: (False, None))
    monkeypatch.setattr(ds, "apply_vr", lambda file, layout: applied.append(1) or file)

    asyncio.run(
        _drain(DownloadRequest(url="https://example.com/x", kind="video", auto_vr=True))
    )
    assert applied == []  # nothing detected → no tagging


def test_is_vr_wins_over_auto_vr(temp_dirs, monkeypatch):
    out = temp_dirs / "clip.mp4"
    _setup(monkeypatch, out)
    detect_calls: list[int] = []
    applied: list[tuple[str, str]] = []
    monkeypatch.setattr(
        ds,
        "detect_vr",
        lambda info, strict=True: detect_calls.append(1) or (True, "360_tb"),
    )
    monkeypatch.setattr(
        ds, "apply_vr", lambda file, layout: applied.append((str(file), layout)) or file
    )

    asyncio.run(
        _drain(
            DownloadRequest(
                url="https://example.com/x",
                kind="video",
                is_vr=True,
                vr_layout="180_sbs",
                auto_vr=True,
            )
        )
    )
    assert detect_calls == []  # is_vr wins → detection is never consulted
    assert applied == [(str(out), "180_sbs")]  # the explicit layout is used
