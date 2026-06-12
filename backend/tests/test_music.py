"""Tests for the multi-source keyless music import (HTTP layer mocked, offline)."""

from __future__ import annotations

import pytest

from app.services import music_import as mi


def test_detect_source():
    assert mi.detect_source("https://open.spotify.com/album/abc") == "spotify"
    assert mi.detect_source("https://www.deezer.com/en/album/123") == "deezer"
    assert mi.detect_source("https://music.apple.com/us/album/x/456") == "apple"
    assert mi.detect_source("https://tidal.com/album/295364468") == "tidal"
    assert mi.detect_source("https://music.amazon.es/albums/B0C5JPHTGC") == "amazon"
    assert mi.detect_source("https://youtube.com/watch?v=x") is None
    assert mi.is_music_url("spotify:track:abc")
    assert not mi.is_music_url("https://example.com")


_DEEZER_ALBUM = {
    "title": "My Album",
    "artist": {"name": "The Artist"},
    "release_date": "2020-05-01",
    "cover_xl": "http://cover/xl",
    "tracks": {"data": [
        {"title": "T1", "artist": {"name": "The Artist"}, "duration": 200,
         "explicit_lyrics": True, "link": "http://dz/1"},
        {"title": "T2", "artist": {"name": "The Artist & X"}, "duration": 180,
         "link": "http://dz/2"},
    ]},
}


def test_resolve_deezer(monkeypatch):
    monkeypatch.setattr(mi, "_get_json", lambda url, headers=None: _DEEZER_ALBUM)
    info = mi.resolve("https://www.deezer.com/album/123")
    assert info.source == "deezer" and info.type == "album"
    assert info.name == "My Album" and info.subtitle == "The Artist"
    assert info.cover_url == "http://cover/xl"
    assert [t.title for t in info.tracks] == ["T1", "T2"]
    assert info.tracks[0].duration_ms == 200000  # seconds -> ms
    assert info.tracks[0].year == "2020" and info.tracks[0].is_explicit is True


_APPLE = {"results": [
    {"wrapperType": "collection", "collectionName": "My Album",
     "artistName": "The Artist", "artworkUrl100": "http://a/100x100bb.jpg"},
    {"wrapperType": "track", "trackName": "T1", "artistName": "The Artist",
     "collectionName": "My Album", "releaseDate": "2020-05-01T00:00:00Z",
     "trackTimeMillis": 200000, "artworkUrl100": "http://a/100x100bb.jpg",
     "trackExplicitness": "explicit", "trackViewUrl": "http://apple/1"},
]}


def test_resolve_apple_album(monkeypatch):
    monkeypatch.setattr(mi, "_get_json", lambda url, headers=None: _APPLE)
    info = mi.resolve("https://music.apple.com/us/album/my-album/456")
    assert info.source == "apple" and info.name == "My Album"
    assert info.subtitle == "The Artist"
    assert info.cover_url == "http://a/600x600bb.jpg"  # bumped resolution
    assert info.tracks[0].duration_ms == 200000 and info.tracks[0].year == "2020"
    assert info.tracks[0].is_explicit is True


def test_resolve_apple_playlist_unsupported(monkeypatch):
    with pytest.raises(mi.MusicImportError):
        mi.resolve("https://music.apple.com/us/playlist/x/pl.abc123")


_AMAZON_HTML = """
<title>Amazon Music - Álbum My Album [Explicit]</title>
<meta property="og:image" content="http://cover.jpg" />
<ul>
  <li class="trackItem albumTrackItem" data-asin="ASIN1">
    <div class="trackListTitle truncate"><a href="#" class="refLink">T1 [Explicit]</a></div>
    <div class="trackListArtist"><a href="#">The Artist</a></div>
  </li>
  <li class="trackItem albumTrackItem" data-asin="ASIN2">
    <div class="trackListTitle truncate"><a href="#" class="refLink">T2</a></div>
    <div class="trackListArtist"><a href="#">The Artist & X</a></div>
  </li>
</ul>
"""


def test_resolve_amazon_scrape(monkeypatch):
    monkeypatch.setattr(mi, "_get", lambda url, headers=None: _AMAZON_HTML)
    info = mi.resolve("https://music.amazon.es/albums/B0C5JPHTGC")
    assert info.source == "amazon" and info.name == "My Album"
    assert [t.title for t in info.tracks] == ["T1", "T2"]
    assert info.tracks[0].is_explicit is True  # had [Explicit]
    assert info.tracks[1].artists == "The Artist & X"
    assert info.subtitle == "The Artist"


def test_find_youtube_match(monkeypatch):
    from app.models.music import MusicTrack

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, query, download=False):
            return {"entries": [
                {"title": "Rick Astley - Never Gonna Give You Up (Official Video)",
                 "channel": "Rick Astley", "duration": 213, "id": "GOOD"},
                {"title": "Never Gonna Give You Up (Live)", "channel": "Rick Astley",
                 "duration": 400, "id": "LIVE"},
            ]}

    monkeypatch.setattr(mi, "YoutubeDL", FakeYDL)
    track = MusicTrack(title="Never Gonna Give You Up", artists="Rick Astley",
                       duration_ms=213000, source_url="http://x")
    assert mi.find_youtube_match(track) == "https://www.youtube.com/watch?v=GOOD"
