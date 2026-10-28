# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Tests for the multi-source keyless music import (HTTP layer mocked, offline)."""

from __future__ import annotations

import pytest

from app.services import music_import as mi


def test_feat_regex_strips_credits_not_inner_letters():
    # A real "(feat. X)"/" ft. X" credit is dropped before scoring...
    from app.services.matching import _FEAT_RE
    assert _FEAT_RE.sub("", "Song feat. X") == "Song"
    assert _FEAT_RE.sub("", "Song ft. X") == "Song"
    assert _FEAT_RE.sub("", "Song (feat. X)") == "Song"
    # ...but "ft"/"feat" *inside* a word must not truncate it (word boundary).
    assert _FEAT_RE.sub("", "Daft Punk") == "Daft Punk"
    assert _FEAT_RE.sub("", "Drift Away") == "Drift Away"


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


def test_detect_source_rejects_ssrf_steering():
    # Detection must pin the brand to the URL *host*, not match it anywhere in
    # the path — otherwise an internal host could be steered into a fetch (SSRF).
    assert mi.detect_source("http://169.254.169.254/music.apple.com/us/playlist/x/pl.abc") is None
    assert mi.detect_source("http://127.0.0.1:8756/link.deezer.com/s/x") is None
    assert mi.detect_source("https://music.apple.com.attacker.example/us/playlist/x/pl.abc") is None
    assert mi.detect_source("https://evil.test/?u=https://open.spotify.com/album/abc") is None


def test_fetch_helpers_block_internal_hosts():
    # Defense-in-depth: even if a URL reached a resolver, the fetch layer
    # (safe_http) must refuse loopback/internal hosts — no localhost/LAN probing.
    with pytest.raises(mi.MusicImportError):
        mi._get("http://127.0.0.1:8756/anything")
    with pytest.raises(mi.MusicImportError):
        mi._final_url("http://127.0.0.1/redirect")


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


_DEEZER_PLAYLIST = {
    "title": "My Mix",
    "creator": {"name": "Curator"},
    "cover_xl": "http://playlist/cover",
    "tracks": {"data": [
        {"title": "T1", "artist": {"name": "A1"}, "duration": 200,
         "album": {"title": "Album1", "cover_xl": "http://album1/xl"}},
        {"title": "T2", "artist": {"name": "A2"}, "duration": 180,
         "album": {"title": "Album2", "cover_xl": "http://album2/xl"}},
    ]},
}


def test_resolve_deezer_playlist_keeps_per_track_covers(monkeypatch):
    monkeypatch.setattr(mi, "_get_json", lambda url, headers=None: _DEEZER_PLAYLIST)
    info = mi.resolve("https://www.deezer.com/playlist/999")
    assert info.type == "playlist"
    assert info.cover_url == "http://playlist/cover"  # header = the playlist's own
    # Each track keeps its own album cover, not the playlist's.
    assert info.tracks[0].cover_url == "http://album1/xl"
    assert info.tracks[1].cover_url == "http://album2/xl"


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


# The real embed has no og:image: the cover is the header <img>, and each track
# row carries its own album art as a CSS background-image.
_AMAZON_HTML = """
<title>Amazon Music - Álbum My Album [Explicit]</title>
<a class="headerImg albumHeader refLink"><img src="https://m.media-amazon.com/images/I/HEADER._SY240_.jpg"></a>
<ul>
  <li class="trackItem albumTrackItem" data-asin="ASIN1">
    <div class="imageBackground" style="background-image: url('https://m.media-amazon.com/images/I/T1.jpg');"></div>
    <div class="trackListTitle truncate"><a href="#" class="refLink">T1 [Explicit]</a></div>
    <div class="trackListArtist"><a href="#">The Artist</a></div>
  </li>
  <li class="trackItem albumTrackItem" data-asin="ASIN2">
    <div class="imageBackground" style="background-image: url('https://m.media-amazon.com/images/I/T2.jpg');"></div>
    <div class="trackListTitle truncate"><a href="#" class="refLink">T2</a></div>
    <div class="trackListArtist"><a href="#">The Artist & X</a></div>
  </li>
</ul>
"""


def test_resolve_amazon_scrape(monkeypatch):
    monkeypatch.setattr(mi, "_get", lambda url, headers=None: _AMAZON_HTML)
    monkeypatch.setattr(mi, "_get_json", lambda url, headers=None: None)  # no Deezer
    info = mi.resolve("https://music.amazon.es/albums/B0C5JPHTGC")
    assert info.source == "amazon" and info.name == "My Album"
    assert [t.title for t in info.tracks] == ["T1", "T2"]
    assert info.tracks[0].is_explicit is True  # had [Explicit]
    assert info.tracks[1].artists == "The Artist & X"
    assert info.subtitle == "The Artist"
    # The header cover comes straight from Amazon (size token stripped to full-res),
    # and with Deezer offering nothing each track keeps its own Amazon art.
    assert info.cover_url == "https://m.media-amazon.com/images/I/HEADER.jpg"
    assert info.tracks[0].cover_url == "https://m.media-amazon.com/images/I/T1.jpg"
    assert info.tracks[1].cover_url == "https://m.media-amazon.com/images/I/T2.jpg"


_DEEZER_SEARCH = {"data": [{"id": 99, "cover_xl": "http://dz/cover_xl"}]}
_DEEZER_ALBUM_LOOKUP = {
    "cover_xl": "http://dz/cover_xl",
    "tracks": {"data": [
        {"title": "T1", "duration": 200},
        {"title": "T2 (feat. X)", "duration": 180},
    ]},
}


def test_resolve_amazon_enriches_from_deezer(monkeypatch):
    # The embed has no durations, so Deezer still fills them — and supplies a
    # higher-res cover for the (non-original) tracks. The header stays Amazon's.
    monkeypatch.setattr(mi, "_get", lambda url, headers=None: _AMAZON_HTML)

    def fake_json(url, headers=None):
        return _DEEZER_ALBUM_LOOKUP if "/album/" in url else _DEEZER_SEARCH

    monkeypatch.setattr(mi, "_get_json", fake_json)
    info = mi.resolve("https://music.amazon.es/albums/B0C5JPHTGC")
    assert info.cover_url == "https://m.media-amazon.com/images/I/HEADER.jpg"  # Amazon
    assert info.tracks[0].duration_ms == 200000  # matched "T1"
    assert info.tracks[1].duration_ms == 180000  # matched ignoring "(feat. X)"
    assert info.tracks[0].cover_url == "http://dz/cover_xl"  # Deezer's higher-res art


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


# A playlist's tracks span many albums, so a single album lookup won't do — each
# track is enriched on its own via a Deezer *track* search.
_AMAZON_PLAYLIST_HTML = """
<title>Amazon Music - Playlist Road Trip</title>
<ul>
  <li class="trackItem albumTrackItem" data-asin="ASIN1">
    <div class="trackListTitle truncate"><a href="#" class="refLink">Song One</a></div>
    <div class="trackListArtist"><a href="#">Artist One</a></div>
  </li>
  <li class="trackItem albumTrackItem" data-asin="ASIN2">
    <div class="trackListTitle truncate"><a href="#" class="refLink">Song Two</a></div>
    <div class="trackListArtist"><a href="#">Artist Two</a></div>
  </li>
</ul>
"""
_DEEZER_TRACK_SEARCH = {
    "data": [{"album": {"cover_xl": "http://dz/track_cover"}, "duration": 210}]
}


def test_resolve_amazon_playlist_enriches_per_track(monkeypatch):
    monkeypatch.setattr(mi, "_get", lambda url, headers=None: _AMAZON_PLAYLIST_HTML)
    monkeypatch.setattr(mi, "_get_json", lambda url, headers=None: _DEEZER_TRACK_SEARCH)
    info = mi.resolve("https://music.amazon.es/playlists/B0EXAMPLE1")
    assert info.type == "playlist"
    assert [t.title for t in info.tracks] == ["Song One", "Song Two"]
    # Each track is backfilled from its own Deezer track lookup (cover + duration).
    assert all(t.cover_url == "http://dz/track_cover" for t in info.tracks)
    assert all(t.duration_ms == 210000 for t in info.tracks)
    assert info.cover_url == "http://dz/track_cover"  # import header cover


# A curated playlist mixing an "Amazon Music Original" (artwork unique to Amazon,
# and not on Deezer) with a regular track that Deezer does have at higher res.
_AMAZON_ORIGINAL_HTML = """
<title>Amazon Music - Playlist Hits</title>
<a class="headerImg playlistHeader refLink"><img src="https://m.media-amazon.com/images/I/PL._SY240_.jpg"></a>
<ul>
  <li class="trackItem playlistTrackItem" data-asin="ASIN1">
    <div class="imageBackground" style="background-image: url('https://m.media-amazon.com/images/I/ORIG.jpg');"></div>
    <div class="trackListTitle truncate"><a href="#" class="refLink">Azul (Amazon Music Original)</a></div>
    <div class="trackListArtist"><a href="#">Some Artist</a></div>
  </li>
  <li class="trackItem playlistTrackItem" data-asin="ASIN2">
    <div class="imageBackground" style="background-image: url('https://m.media-amazon.com/images/I/REG.jpg');"></div>
    <div class="trackListTitle truncate"><a href="#" class="refLink">Regular Song</a></div>
    <div class="trackListArtist"><a href="#">Other Artist</a></div>
  </li>
</ul>
"""


def test_resolve_amazon_originals_keep_amazon_art(monkeypatch):
    monkeypatch.setattr(mi, "_get", lambda url, headers=None: _AMAZON_ORIGINAL_HTML)

    # Deezer has the regular track (higher-res cover) but not the Amazon Original.
    def fake_json(url, headers=None):
        if "Regular" in url or "Other" in url:
            return {"data": [{"album": {"cover_xl": "http://dz/reg"}, "duration": 200}]}
        return {"data": []}  # the Original isn't on Deezer

    monkeypatch.setattr(mi, "_get_json", fake_json)
    info = mi.resolve("https://music.amazon.es/playlists/B0EXAMPLE1")
    # Header is Amazon's own playlist art (size token stripped).
    assert info.cover_url == "https://m.media-amazon.com/images/I/PL.jpg"
    # The Amazon Original keeps Amazon's distinct art — Deezer can't override it…
    assert info.tracks[0].cover_url == "https://m.media-amazon.com/images/I/ORIG.jpg"
    # …while the regular track takes Deezer's higher-res cover + duration.
    assert info.tracks[1].cover_url == "http://dz/reg"
    assert info.tracks[1].duration_ms == 200000


def test_resolve_amazon_playlist_no_enrich_stays_instant(monkeypatch):
    # enrich=False (what the endpoint uses): the playlist returns with Amazon's own
    # per-track covers but no durations, and Deezer is never called — the frontend
    # then fills each cover/duration lazily via track_meta.
    monkeypatch.setattr(mi, "_get", lambda url, headers=None: _AMAZON_ORIGINAL_HTML)

    def boom(url, headers=None):
        raise AssertionError("Deezer must not be called when enrich=False")

    monkeypatch.setattr(mi, "_get_json", boom)
    info = mi.resolve("https://music.amazon.es/playlists/B0EXAMPLE1", enrich=False)
    assert info.tracks[0].cover_url == "https://m.media-amazon.com/images/I/ORIG.jpg"
    assert info.tracks[1].cover_url == "https://m.media-amazon.com/images/I/REG.jpg"
    assert all(t.duration_ms is None for t in info.tracks)


def test_track_meta_looks_up_deezer(monkeypatch):
    # The frontend's lazy per-track fill: one Deezer search -> (cover, duration).
    monkeypatch.setattr(mi, "_get_json", lambda url, headers=None: _DEEZER_TRACK_SEARCH)
    cover, duration_ms = mi.track_meta("Song One", "Artist One")
    assert cover == "http://dz/track_cover"
    assert duration_ms == 210000


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


def test_find_youtube_match_widens_on_miss(monkeypatch):
    """The tight top-5 misses; the fallback top-10 surfaces the real match."""
    from app.models.music import MusicTrack

    calls: list[int] = []

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, query, download=False):
            if "ytsearch" not in query:
                return {"entries": []}  # no SoundCloud lossless source for this track
            n = int(query.split("ytsearch", 1)[1].split(":", 1)[0])
            calls.append(n)
            # The correct upload only appears once the net widens past 5.
            if n <= 5:
                return {"entries": [
                    {"title": "Some Unrelated Song", "channel": "Nobody",
                     "duration": 100, "id": "BAD"},
                ]}
            return {"entries": [
                {"title": "salute - Check Check (Official Visualiser)",
                 "channel": "salute", "duration": 180, "id": "DEEP"},
            ]}

    monkeypatch.setattr(mi, "YoutubeDL", FakeYDL)
    track = MusicTrack(title="Check Check", artists="salute",
                       duration_ms=180000, source_url="http://x")
    assert mi.find_youtube_match(track) == "https://www.youtube.com/watch?v=DEEP"
    assert calls == [5, 10]  # tried tight first, then widened


def test_find_youtube_match_no_fallback_when_top5_hits(monkeypatch):
    """A top-5 hit returns immediately — the fallback search never runs."""
    from app.models.music import MusicTrack

    calls: list[int] = []

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, query, download=False):
            if "ytsearch" not in query:
                return {"entries": []}  # no SoundCloud lossless source for this track
            calls.append(int(query.split("ytsearch", 1)[1].split(":", 1)[0]))
            return {"entries": [
                {"title": "salute - Check Check", "channel": "salute",
                 "duration": 180, "id": "TOP"},
            ]}

    monkeypatch.setattr(mi, "YoutubeDL", FakeYDL)
    track = MusicTrack(title="Check Check", artists="salute",
                       duration_ms=180000, source_url="http://x")
    assert mi.find_youtube_match(track) == "https://www.youtube.com/watch?v=TOP"
    assert calls == [5]  # never widened — no wasted search


# --- ISRC resolution + match + SoundCloud lossless -------------------------

from app.models.music import MusicTrack


def _fake_ydl(responder):
    """A YoutubeDL stand-in whose extract_info returns responder(query)."""
    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, query, download=False):
            return responder(query)

    return FakeYDL


def test_sp_track_from_api_reads_isrc():
    item = {"track": {
        "name": "Song", "artists": [{"name": "A"}], "duration_ms": 180000,
        "external_ids": {"isrc": "USUM71703861"},
        "album": {"name": "Alb", "images": []}, "id": "tid",
    }}
    track = mi._sp_track_from_api(item, "playlist", {})
    assert track is not None and track.isrc == "USUM71703861"


def test_deezer_isrc_accepts_on_duration_match(monkeypatch):
    def fake_search(url):
        if "/search/track" in url:
            return {"data": [{"id": 1, "duration": 180}]}
        return {"isrc": "USUM71703861", "duration": 180}  # /track/1

    monkeypatch.setattr(mi, "_deezer_search", fake_search)
    assert mi._deezer_isrc("Song", "A", 180000) == "USUM71703861"


def test_deezer_isrc_rejects_on_duration_mismatch(monkeypatch):
    # Every query returns a hit whose length is 999 s vs the track's 180 s.
    monkeypatch.setattr(mi, "_deezer_search",
                        lambda url: {"data": [{"id": 1, "duration": 999}]})
    assert mi._deezer_isrc("Song", "A", 180000) is None


def test_find_youtube_match_uses_isrc(monkeypatch):
    def respond(query):
        if "scsearch" in query:
            return {"entries": []}  # no SoundCloud lossless source
        if "music.youtube.com/search" in query:
            return {"entries": [{"id": "ISRCVID"}]}
        if "music.youtube.com/watch" in query:
            return {"duration": 180}  # matches the track length
        return {"entries": []}

    monkeypatch.setattr(mi, "YoutubeDL", _fake_ydl(respond))
    track = MusicTrack(title="S", artists="A", duration_ms=180000, source_url="x")
    url = mi.find_youtube_match(track, isrc="USUM71703861")
    assert url == "https://music.youtube.com/watch?v=ISRCVID"


def test_find_youtube_match_isrc_mismatch_falls_back_to_text(monkeypatch):
    def respond(query):
        if "scsearch" in query:
            return {"entries": []}
        if "music.youtube.com/search" in query:
            return {"entries": [{"id": "WRONG"}]}
        if "music.youtube.com/watch" in query:
            return {"duration": 999}  # length doesn't match -> reject the ISRC hit
        if "ytsearch" in query:
            return {"entries": [{"title": "A - S", "channel": "A",
                                 "duration": 180, "id": "TEXT"}]}
        return {"entries": []}

    monkeypatch.setattr(mi, "YoutubeDL", _fake_ydl(respond))
    track = MusicTrack(title="S", artists="A", duration_ms=180000, source_url="x")
    url = mi.find_youtube_match(track, isrc="USUM71703861")
    assert url == "https://www.youtube.com/watch?v=TEXT"


def test_soundcloud_lossless_is_preferred(monkeypatch):
    monkeypatch.setattr(mi.settings, "prefer_soundcloud_lossless", True)
    sc_url = "https://soundcloud.com/a/s"

    def respond(query):
        if "scsearch" in query:
            return {"entries": [{"title": "A - S", "channel": "A",
                                 "duration": 180, "id": "SC1", "url": sc_url}]}
        if query == sc_url:
            return {"formats": [{"ext": "wav"}]}  # the resolve; lossless flag mocked
        return {"entries": [{"title": "A - S", "channel": "A",
                             "duration": 180, "id": "YT"}]}

    monkeypatch.setattr(mi, "YoutubeDL", _fake_ydl(respond))
    monkeypatch.setattr("app.services.ytdlp_service._audio_summary",
                        lambda formats: (True, True, 1000.0))  # lossless source
    track = MusicTrack(title="S", artists="A", duration_ms=180000, source_url="x")
    assert mi.find_youtube_match(track) == sc_url


def test_soundcloud_not_preferred_when_lossy(monkeypatch):
    monkeypatch.setattr(mi.settings, "prefer_soundcloud_lossless", True)
    def respond(query):
        if "scsearch" in query:
            return {"entries": [{"title": "A - S", "channel": "A",
                                 "duration": 180, "id": "SC1",
                                 "url": "https://soundcloud.com/a/s"}]}
        if query.startswith("https://soundcloud.com"):
            return {"formats": [{"ext": "mp3"}]}
        return {"entries": [{"title": "A - S", "channel": "A",
                             "duration": 180, "id": "YT"}]}

    monkeypatch.setattr(mi, "YoutubeDL", _fake_ydl(respond))
    monkeypatch.setattr("app.services.ytdlp_service._audio_summary",
                        lambda formats: (True, False, 320.0))  # lossy source
    track = MusicTrack(title="S", artists="A", duration_ms=180000, source_url="x")
    assert mi.find_youtube_match(track) == "https://www.youtube.com/watch?v=YT"
