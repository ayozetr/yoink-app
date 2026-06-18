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
