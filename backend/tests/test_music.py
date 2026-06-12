"""Tests for the multi-source keyless music import (HTTP layer mocked, offline)."""

from __future__ import annotations

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
    # Deezer share/short links are recognised (resolved via redirect at fetch).
    assert mi.detect_source("https://link.deezer.com/s/33x4zIvNQBwjhW4mk") == "deezer"


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


# Apple playlists aren't in the iTunes Lookup API, so they're scraped from the
# web page's serialized-server-data blob (title/artist/duration/artwork per song).
_APPLE_PLAYLIST_HTML = """
<meta property="og:title" content="My Playlist en Apple Music" />
<meta property="og:image" content="http://apple/pl-cover.jpg" />
<script type="application/json" id="serialized-server-data">
[{"data":{"sections":[{"items":[
  {"title":"T1","artistName":"Artist A","duration":200000,"showExplicitBadge":true,
   "artwork":{"dictionary":{"url":"http://apple/{w}x{h}{c}.{f}"}},
   "contentDescriptor":{"kind":"song","url":"http://apple/song/1"}},
  {"title":"T2","artistName":"Artist B","duration":180000,"showExplicitBadge":false,
   "artwork":{"dictionary":{"url":"http://apple/b/{w}x{h}bb.jpg"}},
   "contentDescriptor":{"kind":"song","url":"http://apple/song/2"}}
]}]}}]
</script>
"""


def test_resolve_apple_playlist_scrapes_serialized_data(monkeypatch):
    monkeypatch.setattr(mi, "_get", lambda url, headers=None: _APPLE_PLAYLIST_HTML)
    info = mi.resolve("https://music.apple.com/us/playlist/x/pl.abc123")
    assert info.source == "apple" and info.type == "playlist"
    assert info.name == "My Playlist"  # "en Apple Music" suffix stripped
    assert info.cover_url == "http://apple/pl-cover.jpg"
    assert [t.title for t in info.tracks] == ["T1", "T2"]
    assert info.tracks[0].artists == "Artist A"
    assert info.tracks[0].duration_ms == 200000
    assert info.tracks[0].is_explicit is True
    assert info.tracks[0].cover_url == "http://apple/600x600bb.jpg"  # template filled


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


# Same album HTML but with no og:image — the real Amazon embed exposes neither
# cover art nor durations, so resolution must fall back to Deezer for both.
_AMAZON_HTML_NO_COVER = _AMAZON_HTML.replace(
    '<meta property="og:image" content="http://cover.jpg" />', ""
)
_DEEZER_SEARCH = {"data": [{"id": 99, "cover_xl": "http://dz/cover_xl"}]}
_DEEZER_ALBUM_LOOKUP = {
    "cover_xl": "http://dz/cover_xl",
    "tracks": {"data": [
        {"title": "T1", "duration": 200},
        {"title": "T2 (feat. X)", "duration": 180},
    ]},
}


def test_resolve_amazon_enriches_from_deezer(monkeypatch):
    monkeypatch.setattr(mi, "_get", lambda url, headers=None: _AMAZON_HTML_NO_COVER)

    def fake_json(url, headers=None):
        return _DEEZER_ALBUM_LOOKUP if "/album/" in url else _DEEZER_SEARCH

    monkeypatch.setattr(mi, "_get_json", fake_json)
    info = mi.resolve("https://music.amazon.es/albums/B0C5JPHTGC")
    assert info.cover_url == "http://dz/cover_xl"  # backfilled
    assert info.tracks[0].duration_ms == 200000  # matched "T1"
    assert info.tracks[1].duration_ms == 180000  # matched ignoring "(feat. X)"
    assert info.tracks[0].cover_url == "http://dz/cover_xl"


# A single-track embed uses a <div class="trackItem"> + a "trackArtist" link
# (not the album's <li>/"trackListArtist"); the name comes from the <title>.
_AMAZON_TRACK_HTML = """
<title>Amazon Music - Pista La flaca</title>
<div class="trackItem darkSkin container" data-asin="ASINX">
  <div class="trackTitle"><a class="refLink" aria-label="canción, La flaca">La flaca</a></div>
  <div class="trackArtist grey truncate"><a href="#">Jarabe De Palo</a></div>
</div>
"""


def test_resolve_amazon_single_track(monkeypatch):
    monkeypatch.setattr(mi, "_get", lambda url, headers=None: _AMAZON_TRACK_HTML)
    monkeypatch.setattr(mi, "_get_json", lambda url, headers=None:
                        _DEEZER_ALBUM_LOOKUP if "/album/" in url else _DEEZER_SEARCH)
    info = mi.resolve("https://music.amazon.es/tracks/B077K5H3WR")
    assert info.type == "track" and len(info.tracks) == 1
    assert info.tracks[0].title == "La flaca"
    assert info.tracks[0].artists == "Jarabe De Palo"
    assert info.cover_url == "http://dz/cover_xl"  # enriched from Deezer


# Tidal single track: the embed has no <list-item>, so it's built from the
# regular page's og:title ("Artist - Title") + og:image.
_TIDAL_TRACK_EMBED = '<div class="player">no list items here</div>'
_TIDAL_TRACK_PAGE = """
<meta property="og:title" content="Jarabe De Palo - La flaca" />
<meta property="og:image" content="http://tidal/cover.jpg" />
"""


def test_resolve_tidal_single_track(monkeypatch):
    def fake_get(url, headers=None):
        return _TIDAL_TRACK_EMBED if "embed.tidal.com" in url else _TIDAL_TRACK_PAGE

    monkeypatch.setattr(mi, "_get", fake_get)
    info = mi.resolve("https://tidal.com/track/295364470")
    assert info.type == "track" and len(info.tracks) == 1
    assert info.tracks[0].title == "La flaca"
    assert info.tracks[0].artists == "Jarabe De Palo"
    assert info.cover_url == "http://tidal/cover.jpg"


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
