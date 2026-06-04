"""Tests for the audio auto-tagging service (Apple Music / iTunes, Deezer, MusicBrainz).

The catalogue HTTP calls are mocked (no network); we test the filename parsing,
the per-source response mapping, the source dispatch, and the per-format tag
writing round-trip (skipped w/o ffmpeg).
"""

from __future__ import annotations

import json
import shutil
import subprocess

import mutagen
import pytest

from app.models.autotag import ApplyRequest
from app.services import autotag_service as svc

FFMPEG = shutil.which("ffmpeg")
FAKE_COVER = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png")


class _FakeResponse:
    """Minimal context-manager stand-in for urlopen()."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_: object) -> bool:
        return False


# --- filename → (artist, title) -------------------------------------------

@pytest.mark.parametrize(
    ("name", "artist", "title"),
    [
        ("Las Ninyas del Corro - Hood Films.m4a", "Las Ninyas del Corro", "Hood Films"),
        (
            "Rick Astley - Never Gonna Give You Up (Official Video).mp3",
            "Rick Astley",
            "Never Gonna Give You Up",
        ),
        ("Artist - Title (prod. X) [4K].opus", "Artist", "Title"),
        ("JustATitle.flac", "", "JustATitle"),
        # feat./ft. and stray emoji are stripped from the parsed title
        (
            "LOS DIOZES - DISOCIANDO ft. ORSLOK 📱 (Prod. Sceno).mp3",
            "LOS DIOZES",
            "DISOCIANDO",
        ),
        (
            "Bad Bunny - Tití Me Preguntó (feat. Nobody).mp3",
            "Bad Bunny",
            "Tití Me Preguntó",
        ),
        ("Soft Cell - Tainted Love.mp3", "Soft Cell", "Tainted Love"),  # 'ft' kept
    ],
)
def test_guess_from_filename(name, artist, title):
    assert svc.guess_from_filename(name) == (artist, title)


# --- album cleanup ---------------------------------------------------------

def test_clean_album():
    assert svc._clean_album("Hood Films - Single") == "Hood Films"
    assert svc._clean_album("#SKIT2025 - EP") == "#SKIT2025"
    assert svc._clean_album("Whenever You Need Somebody") == "Whenever You Need Somebody"
    assert svc._clean_album(None) is None


# --- iTunes response mapping (mocked) --------------------------------------

def test_itunes_search_maps_results(monkeypatch):
    payload = {
        "results": [
            {
                "trackName": "Hood Films",
                "artistName": "Las Ninyas del Corro",
                "collectionName": "#SKIT2025 - EP",
                "releaseDate": "2025-12-10T12:00:00Z",
                "trackNumber": 2,
                "artworkUrl100": "https://is1.example/abc/100x100bb.jpg",
            }
        ]
    }
    monkeypatch.setattr(svc, "urlopen", lambda *a, **k: _FakeResponse(payload))
    results = svc._itunes_search("Las Ninyas del Corro", "Hood Films")

    assert len(results) == 1
    c = results[0]
    assert c.title == "Hood Films"
    assert c.artist == "Las Ninyas del Corro"
    assert c.album == "#SKIT2025"  # " - EP" stripped
    assert c.year == "2025"
    assert c.track_number == 2
    assert c.cover_url.endswith("1000x1000bb.jpg")  # bumped from 100px


def test_itunes_search_empty_term_skips_network():
    # No term → returns [] without touching the network.
    assert svc._itunes_search("", "") == []


# --- Deezer response mapping (mocked) --------------------------------------

def test_deezer_search_maps_results(monkeypatch):
    payload = {
        "data": [
            {
                "title": "DISOCIANDO",
                "artist": {"name": "Los Diozes"},
                "album": {
                    "title": "MESÓN MASÓN",
                    "cover_xl": "https://cdn.deezer/cover/xl.jpg",
                    "cover_big": "https://cdn.deezer/cover/big.jpg",
                },
            }
        ]
    }
    monkeypatch.setattr(svc, "urlopen", lambda *a, **k: _FakeResponse(payload))
    results = svc._deezer_search("Los Diozes", "DISOCIANDO")

    assert len(results) == 1
    c = results[0]
    assert c.title == "DISOCIANDO"
    assert c.artist == "Los Diozes"
    assert c.album == "MESÓN MASÓN"
    assert c.cover_url.endswith("xl.jpg")  # prefers cover_xl
    assert c.year is None and c.track_number is None  # not in Deezer search


def test_deezer_search_empty_term_skips_network():
    assert svc._deezer_search("", "") == []


# --- MusicBrainz response mapping (mocked) ---------------------------------

def test_musicbrainz_search_maps_results(monkeypatch):
    payload = {
        "recordings": [
            {
                "title": "DISOCIANDO",
                "artist-credit": [
                    {"name": "Los Diozes", "joinphrase": " & "},
                    {"name": "Orslok"},
                ],
                "releases": [
                    {
                        "id": "a5eb9479-c94d-4191-83dd-929b6c89ef5e",
                        "title": "MESÓN MASÓN",
                        "date": "2026-05-26",
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr(svc, "urlopen", lambda *a, **k: _FakeResponse(payload))
    results = svc._musicbrainz_search("Los Diozes", "DISOCIANDO")

    assert len(results) == 1
    c = results[0]
    assert c.title == "DISOCIANDO"
    assert c.artist == "Los Diozes & Orslok"  # artist-credit joined via joinphrase
    assert c.album == "MESÓN MASÓN"
    assert c.year == "2026"
    assert c.cover_url.endswith("/a5eb9479-c94d-4191-83dd-929b6c89ef5e/front-500")


def test_musicbrainz_search_empty_term_skips_network():
    assert svc._musicbrainz_search("", "") == []


# --- source dispatch -------------------------------------------------------

def test_search_dispatches_on_source(monkeypatch):
    monkeypatch.setattr(svc, "_itunes_search", lambda *a: ["apple"])
    monkeypatch.setattr(svc, "_deezer_search", lambda *a: ["deezer"])
    monkeypatch.setattr(svc, "_musicbrainz_search", lambda *a: ["mb"])
    monkeypatch.setattr(svc.settings, "autotag_source", "apple")
    assert svc._search("a", "b") == ["apple"]
    monkeypatch.setattr(svc.settings, "autotag_source", "deezer")
    assert svc._search("a", "b") == ["deezer"]
    monkeypatch.setattr(svc.settings, "autotag_source", "musicbrainz")
    assert svc._search("a", "b") == ["mb"]
    monkeypatch.setattr(svc.settings, "autotag_source", "auto")
    assert svc._search("a", "b") == ["apple"]  # auto → first non-empty source


# --- automatic cascade -----------------------------------------------------

def test_auto_search_falls_through_to_first_match(monkeypatch):
    order: list[str] = []

    def stub(name, result):
        def fn(*a):
            order.append(name)
            return result

        return fn

    monkeypatch.setattr(svc, "_itunes_search", stub("apple", []))
    monkeypatch.setattr(svc, "_deezer_search", stub("deezer", []))
    monkeypatch.setattr(svc, "_musicbrainz_search", stub("mb", ["hit"]))
    assert svc._auto_search("a", "b") == ["hit"]
    assert order == ["apple", "deezer", "mb"]  # tried in order until a match


def test_auto_search_skips_a_failing_source(monkeypatch):
    def boom(*a):
        raise svc.AutotagError("source down")

    monkeypatch.setattr(svc, "_itunes_search", boom)
    monkeypatch.setattr(svc, "_deezer_search", lambda *a: ["deezer"])
    monkeypatch.setattr(svc, "_musicbrainz_search", lambda *a: [])
    assert svc._auto_search("a", "b") == ["deezer"]  # apple errored → next source


# --- apply error handling --------------------------------------------------

def test_apply_invalid_audio_file_raises_autotag_error(tmp_path):
    # A corrupt / mistyped file makes mutagen raise; apply() must surface it as
    # AutotagError (router → 422), not let a raw MutagenError become a 500.
    bad = tmp_path / "broken.flac"
    bad.write_bytes(b"this is definitely not a FLAC file")
    with pytest.raises(svc.AutotagError):
        svc.apply(ApplyRequest(path=str(bad), title="X"), bad)


def test_fetch_cover_rejects_non_http_schemes():
    # urlopen honors file:///ftp://; the guard must block them (SSRF / file read).
    assert svc._fetch_cover("file:///etc/passwd") is None
    assert svc._fetch_cover("ftp://internal-host/secret") is None


# --- tag writing round-trip (per format) ----------------------------------

@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available to synth audio")
@pytest.mark.parametrize("ext", ["mp3", "m4a", "flac"])
def test_write_and_reread_tags(tmp_path, ext):
    path = tmp_path / f"track.{ext}"
    subprocess.run(
        [FFMPEG, "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=mono", "-t", "1", str(path)],
        check=True,
    )
    tags = {"title": "Title", "artist": "Artist", "album": "Album",
            "date": "1999", "tracknumber": 3}

    embedded = svc._write_tags(path, tags, FAKE_COVER)
    assert embedded is True

    reread = mutagen.File(str(path), easy=True)
    assert reread["title"][0] == "Title"
    assert reread["artist"][0] == "Artist"
    assert reread["album"][0] == "Album"


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available to synth audio")
def test_write_without_cover(tmp_path):
    path = tmp_path / "track.mp3"
    subprocess.run(
        [FFMPEG, "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=mono", "-t", "1", str(path)],
        check=True,
    )
    assert svc._write_tags(path, {"title": "Only Title"}, None) is False
    assert mutagen.File(str(path), easy=True)["title"][0] == "Only Title"
