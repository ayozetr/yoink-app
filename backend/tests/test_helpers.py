"""Unit tests for pure helper functions across the services."""

from __future__ import annotations

import pytest

from app.core.humanize import humanize_bytes
from app.core.ytdlp_options import cookie_options, normalize_url
from app.services.download_service import (
    _format_eta,
    _format_speed,
    _map_progress,
    _parse_height,
)
from app.services.ytdlp_service import (
    _build_entry,
    _build_playlist,
    _build_video,
    _format_duration,
    _map_format,
)


@pytest.mark.parametrize(
    ("num", "expected"),
    [(0, "0 B"), (512, "512 B"), (1536, "1.5 KB"), (1048576, "1.0 MB"),
     (457389, "446.7 KB"), (5 * 1024**3, "5.0 GB")],
)
def test_humanize_bytes(num, expected):
    assert humanize_bytes(num) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(None, None), (5, "5s"), (61, "1m 1s"), (3661, "1h 1m 1s")],
)
def test_format_duration(seconds, expected):
    assert _format_duration(seconds) == expected


def test_format_speed_and_eta():
    assert _format_speed(None) is None
    assert _format_speed(3_500_000) == "3.3 MB/s"
    assert _format_eta(None) is None
    assert _format_eta(95) == "01:35"
    assert _format_eta(3725) == "1:02:05"


@pytest.mark.parametrize(
    ("quality", "expected"),
    [("1080p", 1080), ("720", 720), (None, None), ("best", None)],
)
def test_parse_height(quality, expected):
    assert _parse_height(quality) == expected


def test_normalize_url_tiktok_photo():
    assert (
        normalize_url("https://www.tiktok.com/@user/photo/123")
        == "https://www.tiktok.com/@user/video/123"
    )
    # Unrelated URLs pass through untouched.
    url = "https://www.youtube.com/watch?v=abc"
    assert normalize_url(url) == url


def test_cookie_options(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "cookies_from_browser", None)
    monkeypatch.setattr(settings, "cookies_file", None)
    assert cookie_options() == {}

    monkeypatch.setattr(settings, "cookies_from_browser", "firefox")
    assert cookie_options() == {"cookiesfrombrowser": ("firefox",)}

    # browser wins over file
    monkeypatch.setattr(settings, "cookies_file", "/tmp/c.txt")
    assert cookie_options() == {"cookiesfrombrowser": ("firefox",)}

    monkeypatch.setattr(settings, "cookies_from_browser", None)
    assert cookie_options() == {"cookiefile": "/tmp/c.txt"}


def test_map_progress_downloading():
    event = _map_progress(
        {
            "status": "downloading",
            "downloaded_bytes": 50,
            "total_bytes": 100,
            "speed": 1048576,
            "eta": 30,
            "filename": "/out/clip.mp4",
        }
    )
    assert event is not None
    assert event.status == "downloading"
    assert event.percent == 50.0
    assert event.speed == "1.0 MB/s"
    assert event.eta == "00:30"
    assert event.filename == "clip.mp4"


def test_map_progress_finished_and_other():
    finished = _map_progress({"status": "finished", "total_bytes": 100, "filename": "a.webm"})
    assert finished is not None and finished.status == "processing" and finished.percent == 100.0
    assert _map_progress({"status": "error"}) is None


def test_map_format_video_vs_audio():
    video = _map_format(
        {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "filesize": 1000}
    )
    assert video.has_video and not video.has_audio and video.filesize == 1000
    audio = _map_format({"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a"})
    assert audio.has_audio and not audio.has_video


def test_build_video():
    video = _build_video(
        {
            "id": "abc",
            "title": "Clip",
            "duration": 61,
            "uploader": "Chan",
            "thumbnail": "http://t/x.jpg",
            "formats": [{"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a"}],
        }
    )
    assert video.id == "abc"
    assert video.duration_string == "1m 1s"
    assert video.thumbnail_url == "http://t/x.jpg"
    assert len(video.formats) == 1


def test_build_entry_and_playlist():
    assert _build_entry({"id": "x", "title": "No URL"}) is None

    playlist = _build_playlist(
        {
            "_type": "playlist",
            "id": "PL1",
            "title": "My List",
            "uploader": "Me",
            "entries": [
                {"id": "a", "title": "A", "url": "http://x/a", "duration": 61},
                {"id": "b", "title": "B", "url": "http://x/b"},
                {"id": "c", "title": "skip"},  # no url -> dropped
            ],
        }
    )
    assert playlist.entry_count == 3  # total reported (incl. the dropped one)
    assert [e.id for e in playlist.entries] == ["a", "b"]
    assert playlist.entries[0].duration_string == "1m 1s"
    assert playlist.truncated is False
