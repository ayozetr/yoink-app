"""Tests for the keyless Spotify resolver (embed parsing mocked, offline)."""

from __future__ import annotations

import pytest

from app.services import spotify_service as svc

_TRACK_ENTITY = {
    "type": "track",
    "name": "Never Gonna Give You Up",
    "artists": [{"name": "Rick Astley"}],
    "duration": 213573,
    "isExplicit": False,
    "releaseDate": {"isoString": "1987-07-27"},
    "visualIdentity": {"image": [{"url": "http://img/lo"}, {"url": "http://img/hi"}]},
}

_PLAYLIST_ENTITY = {
    "type": "playlist",
    "name": "Today's Top Hits",
    "visualIdentity": {"image": [{"url": "http://cover"}]},
    "trackList": [
        {"title": "Song A", "subtitle": "Artist A", "duration": 200000,
         "isExplicit": True, "uri": "spotify:track:AAA"},
        {"title": "Song B", "subtitle": "Artist B, Artist C", "duration": 180000,
         "uri": "spotify:track:BBB"},
        {"subtitle": "no title -> skipped", "uri": "spotify:track:CCC"},
    ],
}


def test_is_spotify_url_and_parse():
    assert svc.is_spotify_url("https://open.spotify.com/track/4PTG3Z6ehGkBFwjybzWkR8?si=x")
    assert svc.is_spotify_url("https://open.spotify.com/intl-es/playlist/37i9abc")
    assert svc.is_spotify_url("spotify:album:1234ABCdef")
    assert not svc.is_spotify_url("https://youtube.com/watch?v=x")
    assert svc._parse_url("https://open.spotify.com/intl-es/album/XYZ123?si=q") == ("album", "XYZ123")


def test_parse_non_spotify_raises():
    with pytest.raises(svc.SpotifyError):
        svc._parse_url("https://example.com/not-spotify")


def test_resolve_track(monkeypatch):
    monkeypatch.setattr(svc, "_fetch_embed", lambda kind, sid: (_TRACK_ENTITY, None))
    info = svc.resolve_spotify("https://open.spotify.com/track/abc?si=x")
    assert info.type == "track" and len(info.tracks) == 1
    t = info.tracks[0]
    assert t.title == "Never Gonna Give You Up"
    assert t.artists == "Rick Astley"
    assert t.duration_ms == 213573
    assert t.year == "1987"
    assert t.cover_url == "http://img/hi"  # last (highest-res) image
    assert t.spotify_url.endswith("/track/abc")


def test_resolve_playlist(monkeypatch):
    monkeypatch.setattr(svc, "_fetch_embed", lambda kind, sid: (_PLAYLIST_ENTITY, None))
    info = svc.resolve_spotify("https://open.spotify.com/playlist/xyz")
    assert info.type == "playlist" and info.name == "Today's Top Hits"
    assert info.cover_url == "http://cover"
    # The item with no title is dropped.
    assert [t.title for t in info.tracks] == ["Song A", "Song B"]
    assert info.tracks[0].is_explicit is True
    assert info.tracks[1].artists == "Artist B, Artist C"
    assert info.tracks[0].spotify_url == "https://open.spotify.com/track/AAA"


_ALBUM_ENTITY = {
    "type": "album",
    "name": "Me Muevo Con Dios",
    "releaseDate": {"isoString": "2022-05-20"},
    "visualIdentity": {"image": [{"url": "http://albumcover"}]},
    "trackList": [
        {"title": "TURBO", "subtitle": "Cruz Cafuné", "duration": 164374,
         "uri": "spotify:track:T1"},
        {"title": "BABI BOI", "subtitle": "Cruz Cafuné, Chita", "duration": 213525,
         "uri": "spotify:track:T2"},
    ],
}


def test_resolve_album_sets_album_name_and_year(monkeypatch):
    monkeypatch.setattr(svc, "_fetch_embed", lambda kind, sid: (_ALBUM_ENTITY, None))
    info = svc.resolve_spotify("https://open.spotify.com/album/abc")
    assert info.type == "album"
    # Every track inherits the album's name + release year.
    assert all(t.album == "Me Muevo Con Dios" for t in info.tracks)
    assert all(t.year == "2022" for t in info.tracks)


def test_resolve_playlist_via_api_token(monkeypatch):
    # When the anonymous token works, the FULL tracklist comes from the API with
    # richer per-track metadata (album/year/cover), and truncated is False.
    monkeypatch.setattr(
        svc, "_fetch_embed", lambda kind, sid: ({"type": "playlist", "name": "Big PL"}, "tok")
    )
    api_items = [
        {"track": {"name": "T1", "duration_ms": 200000, "explicit": False,
                   "artists": [{"name": "A1"}], "id": "id1",
                   "album": {"name": "Alb1", "release_date": "2020-01-01",
                             "images": [{"url": "http://c1"}]}}},
        {"track": {"name": "T2", "duration_ms": 180000, "artists": [{"name": "A2"}],
                   "id": "id2", "album": {"name": "Alb2", "release_date": "2019"}}},
        {"track": None},  # skipped
    ]
    monkeypatch.setattr(svc, "_fetch_all_tracks", lambda kind, sid, tok: api_items)
    info = svc.resolve_spotify("https://open.spotify.com/playlist/big")
    assert info.truncated is False
    assert [t.title for t in info.tracks] == ["T1", "T2"]
    assert info.tracks[0].album == "Alb1" and info.tracks[0].year == "2020"
    assert info.tracks[0].cover_url == "http://c1"


def test_find_youtube_match_wires_search_to_ranker(monkeypatch):
    from app.models.spotify import SpotifyTrack

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, query, download=False):
            return {"entries": [
                {"title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
                 "channel": "Rick Astley", "duration": 213, "id": "OFFICIAL"},
                {"title": "Never Gonna Give You Up (Live)",
                 "channel": "Rick Astley", "duration": 400, "id": "LIVE"},
            ]}

    monkeypatch.setattr(svc, "YoutubeDL", FakeYDL)
    track = SpotifyTrack(title="Never Gonna Give You Up", artists="Rick Astley",
                         duration_ms=213573, spotify_url="https://open.spotify.com/track/x")
    assert svc.find_youtube_match(track) == "https://www.youtube.com/watch?v=OFFICIAL"
