"""friendly_download_error: yt-dlp noise → concise, user-facing messages."""

from __future__ import annotations

from app.services.download_service import friendly_download_error


def test_strips_prefix_and_report_boilerplate():
    raw = (
        "ERROR: [youtube] dQw4w9WgXcQ: Some odd failure. "
        "Please report this issue on https://github.com/yt-dlp/yt-dlp/issues"
    )
    assert friendly_download_error(raw) == "Some odd failure."


def test_maps_known_failures():
    assert "cookies" in friendly_download_error(
        "ERROR: unable to download video data: HTTP Error 403: Forbidden"
    ).lower()
    assert "rate-limiting" in friendly_download_error(
        "ERROR: HTTP Error 429: Too Many Requests"
    ).lower()
    assert "unavailable" in friendly_download_error(
        "ERROR: [youtube] abc123: Video unavailable"
    ).lower()
    assert "format" in friendly_download_error(
        "ERROR: Requested format is not available"
    ).lower()
    assert "cookies" in friendly_download_error(
        "ERROR: Sign in to confirm you're not a bot"
    ).lower()
    assert "private" in friendly_download_error(
        "ERROR: [youtube] x: Private video"
    ).lower()


def test_fallback_is_a_clean_first_line():
    out = friendly_download_error("ERROR: [generic] something weird\nsecond line")
    assert out == "something weird"


def test_keeps_a_word_prefix_without_a_digit():
    # Only id-shaped tokens (with a digit) are dropped; a legit "Word:" survives.
    assert (
        friendly_download_error("ERROR: Postprocessing: conversion failed")
        == "Postprocessing: conversion failed"
    )


def test_low_disk_space_aborts_before_download(temp_dirs, monkeypatch):
    """A near-full disk yields an error event up front, no download attempted."""
    import asyncio
    from collections import namedtuple

    from app.models.media import DownloadRequest
    from app.services import download_service as ds

    usage = namedtuple("usage", "total used free")
    # ~1 KB free — well under the threshold.
    monkeypatch.setattr(ds.shutil, "disk_usage", lambda p: usage(100, 99, 1024))

    async def first_event():
        async for event in ds.download_events(
            DownloadRequest(url="http://x/v", kind="audio")
        ):
            return event
        return None

    event = asyncio.run(first_event())
    assert event is not None and event.type == "error"
    assert "disk space" in event.message.lower()
