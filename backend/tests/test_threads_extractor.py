"""Tests for the custom Threads (Meta) yt-dlp extractor.

These exercise the URL matching and HTML/JSON parsing offline, plus the full
``_real_extract`` flow against a synthetic fixture that mirrors the real page
shape — including the empty *placeholder* media object Threads emits next to the
real one, and an avatar block that must not be mistaken for the video cover.
"""

from __future__ import annotations

import base64
import json

import pytest
from yt_dlp import YoutubeDL

from app.services.threads_extractor import ThreadsIE, register


def _efg(**data: object) -> str:
    """Build a URL-safe base64 ``efg`` blob like the ones in signed URLs."""
    raw = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    return raw.rstrip("=")  # Threads omits padding


EFG = _efg(duration_s=107, xpv_asset_id=123)
VIDEO_URL = (
    f"https://instagram.fmad8-1.fna.fbcdn.net/o1/v/t2/f2/m86/AQabc.mp4"
    f"?_nc_cat=103&efg={EFG}&oh=00_xyz&oe=6A212B48"
)
COVER_URL = "https://scontent.cdninstagram.com/v/t51.82787-15/cover_711.jpg?stp=dst-jpg"
AVATAR_URL = "https://scontent.cdninstagram.com/v/t51.2885-19/avatar_357.jpg"


def _esc(url: str) -> str:
    """Escape slashes the way the embedded JSON does (``https:\\/\\/``)."""
    return url.replace("/", "\\/")


# A trimmed page: an avatar (must be ignored), then an EMPTY placeholder media
# (candidates:[]/video_versions:null), then the REAL media (caption, code,
# cover image_versions2 and a non-empty video_versions).
FIXTURE = (
    '{"user":{"username":"villages.three",'
    '"image_versions2":{"candidates":[{"height":150,"url":"' + _esc(AVATAR_URL) + '"}]}},'
    '"placeholder":{"image_versions2":{"candidates":[]},"original_height":612,'
    '"video_versions":null},'
    '"post":{"caption":{"text":"\\u201cFalse Remedy\\u201d clip\\n#tag","pk":"1"},'
    '"code":"DZDjY7mlSZw",'
    '"image_versions2":{"candidates":['
    '{"height":640,"url":"' + _esc(COVER_URL) + '"},'
    '{"height":1280,"url":"' + _esc(COVER_URL) + '"}]},'
    '"original_height":1664,"original_width":936,"usertags":null,'
    '"video_versions":[{"type":101,"url":"' + _esc(VIDEO_URL) + '",'
    '"width":720,"height":1280}]}}'
)


@pytest.mark.parametrize(
    ("url", "expected_id"),
    [
        ("https://www.threads.com/@villages.three/post/DZDjY7mlSZw", "DZDjY7mlSZw"),
        ("https://threads.net/@user/post/AbC-123_x", "AbC-123_x"),
        ("https://www.threads.com/@user/post/DZD2bG-gMVd?xmt=AQG0", "DZD2bG-gMVd"),
        ("https://www.threads.com/t/DYfBXSUoBix", "DYfBXSUoBix"),
    ],
)
def test_valid_url_matches(url, expected_id):
    assert ThreadsIE.suitable(url)
    assert ThreadsIE._match_valid_url(url).group("id") == expected_id


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/reel/DZDxkxQisRu/",
        "https://www.threads.com/@villages.three",  # profile, not a post
        "https://example.com/post/abc",
    ],
)
def test_valid_url_rejects(url):
    assert not ThreadsIE.suitable(url)


def test_efg_duration():
    assert ThreadsIE._efg_duration(VIDEO_URL) == 107
    assert ThreadsIE._efg_duration("https://x/y.mp4?_nc_cat=1") is None


def test_caption_decodes_escapes():
    assert ThreadsIE._caption(FIXTURE) == "“False Remedy” clip\n#tag"
    assert ThreadsIE._caption('{"no":"caption here"}') is None


def test_json_array_skips_null_and_parses_urls():
    versions = ThreadsIE._json_array("video_versions", FIXTURE)
    assert versions and versions[0]["url"] == VIDEO_URL  # slashes un-escaped
    assert versions[0]["height"] == 1280


def test_thumbnail_prefers_cover_over_avatar_and_placeholder():
    # last non-empty image_versions2 before the real video == the cover, and the
    # highest-res candidate within it. Never the avatar (t51.2885-19).
    thumb = ThreadsIE._thumbnail(FIXTURE)
    assert thumb == COVER_URL
    assert "t51.2885-19" not in (thumb or "")


def test_register_puts_threads_ahead_of_generic():
    with YoutubeDL({"quiet": True}) as ydl:
        register(ydl)
        keys = list(ydl._ies.keys())
        assert keys[0] == "Threads"
        assert keys.index("Threads") < keys.index("Generic")


def test_real_extract_against_fixture(monkeypatch):
    url = "https://www.threads.com/@villages.three/post/DZDjY7mlSZw"
    with YoutubeDL({"quiet": True}) as ydl:
        ie = ThreadsIE()
        ie.set_downloader(ydl)
        monkeypatch.setattr(ie, "_download_webpage", lambda *a, **k: FIXTURE)
        info = ie._real_extract(url)

    assert info["id"] == "DZDjY7mlSZw"
    assert info["title"] == "“False Remedy” clip #tag"
    assert info["uploader"] == "villages.three"
    assert info["duration"] == 107
    assert info["thumbnail"] == COVER_URL
    assert len(info["formats"]) == 1
    assert info["formats"][0]["url"] == VIDEO_URL
    assert info["formats"][0]["height"] == 1280
