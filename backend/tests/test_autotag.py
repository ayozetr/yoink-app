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

from app.models.autotag import ApplyRequest, TagCandidate
from app.services import autotag_service as svc

FFMPEG = shutil.which("ffmpeg")
FAKE_COVER = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png")


class _FakeResponse:
    """Minimal context-manager stand-in for urlopen()."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self, *args: object) -> bytes:
        # Accept urlopen's read(size) cap argument (ignored — the fake is small).
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
        # Un-bracketed trailing noise ("| VIDEO", "Official Audio", "(Music Video)")
        (
            "CRUZ CAFUNÉ - 922 & HEARTBREAK | VIDEO.mp3",
            "CRUZ CAFUNÉ",
            "922 & HEARTBREAK",
        ),
        (  # yt-dlp sanitises "|" to the fullwidth "｜" in the on-disk filename
            "CRUZ CAFUNÉ - 922 & HEARTBREAK ｜ VIDEO.mp3",
            "CRUZ CAFUNÉ",
            "922 & HEARTBREAK",
        ),
        # other fullwidth sanitised chars (":" → "：") are normalised back too
        ("Artist - Title： Part 2.mp3", "Artist", "Title: Part 2"),
        ("Drake - Hotline Bling (Music Video) [4K].mp3", "Drake", "Hotline Bling"),
        ("Artist - Song - Official Audio.mp3", "Artist", "Song"),
        # Spanish-language YouTube noise ("(Videoclip/Vídeo/Audio Oficial)", "Letra")
        (
            "Daniela Garsal, Cruz Cafuné - QUÉ CRUEL (Videoclip Oficial).mp3",
            "Daniela Garsal, Cruz Cafuné",
            "QUÉ CRUEL",
        ),
        ("Quevedo - Columbia (Vídeo Oficial).m4a", "Quevedo", "Columbia"),
        ("Aitana - Mariposas (Audio Oficial).mp3", "Aitana", "Mariposas"),
        ("Quevedo - Columbia Vídeo Oficial.mp3", "Quevedo", "Columbia"),  # no brackets
        ("Morad - Pelele (Letra).mp3", "Morad", "Pelele"),
        # Real-world leaks from popular-playlist testing: a "| album/label" suffix
        # after the title (safe to drop once artist/title split on " - "), French
        # "(Clip officiel)", and an "(Explicit)" tag.
        (
            "BAD BUNNY - DtMF (Visualizer) | DeBÍ TiRAR MáS FOToS.mp3",
            "BAD BUNNY",
            "DtMF",
        ),
        ("SAIKO, Omar Montes - YO LO SOÑÉ (Official Video) | SAKURA.mp3",
         "SAIKO, Omar Montes", "YO LO SOÑÉ"),
        ("Aya Nakamura - Copines (Clip officiel).mp3", "Aya Nakamura", "Copines"),
        # Full-width CJK parentheses around the noise tag (YouTube Music JP).
        (
            "MISIA - Everything （Official HD Music Video）.mp3",
            "MISIA",
            "Everything",
        ),
        ("Nicki Minaj - Beez In The Trap (Explicit).mp3", "Nicki Minaj", "Beez In The Trap"),
        # …but a "| Title" with NO artist dash must NOT be pipe-trimmed (the pipe
        # may be the separator), and a legit parenthetical stays.
        ("Olivia Dean - So Easy (To Fall In Love).mp3", "Olivia Dean", "So Easy (To Fall In Love)"),
        # legit titles ending in those words are left untouched
        ("Artist - Video Games.mp3", "Artist", "Video Games"),
        ("Artist - Kill the Video.mp3", "Artist", "Kill the Video"),
        ("Artist - Live at Wembley.mp3", "Artist", "Live at Wembley"),
        # Non-Western shapes with NO "Artist - Title" dash:
        # K-pop "ARTIST 'TITLE' MV" (straight quotes) and "ARTIST \"TITLE\"" (double).
        ("aespa 'Whiplash' MV.mp3", "aespa", "Whiplash"),
        ('IVE "HEYA" Official MV.m4a', "IVE", "HEYA"),
        # A possessive apostrophe must NOT be read as a title quote.
        ("Destiny's Child Independent Women.mp3", "", "Destiny's Child Independent Women"),
        # Bollywood "Title | Movie | Cast | …" (≥3 segments → take the song).
        ("Kesariya | Brahmastra | Ranbir Kapoor | Alia Bhatt.mp3", "", "Kesariya"),
        # …but a single ambiguous "A | B" pipe is left intact.
        ("Some Song | Some Movie.mp3", "", "Some Song | Some Movie"),
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


def test_apple_stores_adds_region_then_us(monkeypatch):
    monkeypatch.setattr(svc, "_user_country", lambda: "ES")
    assert svc._apple_stores() == ["ES", None]  # regional store first, US after
    monkeypatch.setattr(svc, "_user_country", lambda: "US")
    assert svc._apple_stores() == [None]  # already the US default — no duplicate
    monkeypatch.setattr(svc, "_user_country", lambda: None)
    assert svc._apple_stores() == [None]  # unknown region → US default only


def test_itunes_search_queries_user_storefront(monkeypatch):
    # On a Spanish machine the ES storefront is queried *in addition* to the US
    # default, so regional-only releases surface. Both URLs are hit; an identical
    # hit from both stores is deduped to one.
    urls: list[str] = []

    def fake_urlopen(request, *a, **k):
        urls.append(request.full_url)
        return _FakeResponse({"results": [{"trackName": "Amén", "artistName": "Cruzzi"}]})

    monkeypatch.setattr(svc, "_user_country", lambda: "ES")
    monkeypatch.setattr(svc, "urlopen", fake_urlopen)
    results = svc._itunes_search("Cruzzi", "Amén")
    assert any("country=ES" in u for u in urls)  # regional store queried
    assert any("country=" not in u for u in urls)  # US default still queried too
    assert len(results) == 1  # identical hit from both stores deduped


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
    apple = [TagCandidate(title="A", artist="apple")]
    deezer = [TagCandidate(title="D", artist="deezer")]
    mb = [TagCandidate(title="M", artist="mb")]
    monkeypatch.setattr(svc, "_itunes_search", lambda *a, **k: apple)
    monkeypatch.setattr(svc, "_deezer_search", lambda *a, **k: deezer)
    monkeypatch.setattr(svc, "_musicbrainz_search", lambda *a, **k: mb)
    monkeypatch.setattr(svc.settings, "autotag_source", "apple")
    assert svc._search("a", "b") == apple
    monkeypatch.setattr(svc.settings, "autotag_source", "deezer")
    assert svc._search("a", "b") == deezer
    monkeypatch.setattr(svc.settings, "autotag_source", "musicbrainz")
    assert svc._search("a", "b") == mb
    monkeypatch.setattr(svc.settings, "autotag_source", "auto")
    assert svc._search("a", "b") == apple + deezer  # auto merges Apple + Deezer


def test_rank_puts_cleanest_match_first():
    cands = [
        TagCandidate(title="922 & Heartbreak (feat. X) [Remix]", artist="Finesse"),
        TagCandidate(title="922 & Heartbreak", artist="Cruz Cafuné"),
        TagCandidate(title="922 & Heartbreak (Remix)", artist="Finesse"),
    ]
    ranked = svc._rank(cands, "Cruz Cafuné", "922 & Heartbreak")
    # The clean original (exact title + matching artist) outranks the remixes.
    assert (ranked[0].artist, ranked[0].title) == ("Cruz Cafuné", "922 & Heartbreak")


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
    # Fast sources (Apple + Deezer) both empty → falls back to MusicBrainz.
    assert order == ["apple", "deezer", "mb"]


def test_auto_search_skips_a_failing_source(monkeypatch):
    deezer = [TagCandidate(title="D", artist="deezer")]

    def boom(*a, **k):
        raise svc.AutotagError("source down")

    monkeypatch.setattr(svc, "_itunes_search", boom)
    monkeypatch.setattr(svc, "_deezer_search", lambda *a, **k: deezer)
    monkeypatch.setattr(svc, "_musicbrainz_search", lambda *a, **k: [])
    assert svc._auto_search("a", "b") == deezer  # apple errored → deezer still used


def test_auto_search_merges_and_dedupes(monkeypatch):
    # Apple has only a remix; Deezer has the original (the real 922 & Heartbreak
    # case). Merging surfaces both; the shared duplicate is dropped once.
    apple = [TagCandidate(title="Song", artist="A")]
    deezer = [
        TagCandidate(title="song", artist="a"),  # dup of apple's (case-insensitive)
        TagCandidate(title="Original", artist="C"),
    ]
    monkeypatch.setattr(svc, "_itunes_search", lambda *a, **k: apple)
    monkeypatch.setattr(svc, "_deezer_search", lambda *a, **k: deezer)
    result = [(c.artist, c.title) for c in svc._auto_search("x", "y")]
    assert result == [("A", "Song"), ("C", "Original")]


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
@pytest.mark.parametrize("ext", ["mp3", "m4a", "flac"])
def test_write_embeds_lyrics(tmp_path, ext):
    path = tmp_path / f"track.{ext}"
    subprocess.run(
        [FFMPEG, "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=mono", "-t", "1", str(path)],
        check=True,
    )
    svc._write_tags(path, {"title": "T", "lyrics": "line one\nline two"}, None)

    if ext == "mp3":
        from mutagen.id3 import ID3

        text = ID3(str(path)).getall("USLT")[0].text
    elif ext == "m4a":
        from mutagen.mp4 import MP4

        text = MP4(str(path))["\xa9lyr"][0]
    else:
        from mutagen.flac import FLAC

        text = FLAC(str(path))["lyrics"][0]
    assert "line one" in text and "line two" in text


def test_write_lrc_sidecar(tmp_path):
    media = tmp_path / "song.mp3"
    media.write_bytes(b"x")
    svc._write_lrc_sidecar(media, "[00:01.00] line one\n[00:03.50] line two")
    lrc = tmp_path / "song.lrc"
    assert lrc.exists()
    assert lrc.read_text(encoding="utf-8").startswith("[00:01.00] line one")


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available to synth audio")
def test_apply_writes_lrc_when_enabled(tmp_path, monkeypatch):
    from app.core.config import settings as cfg
    from app.services.lyrics import Lyrics

    path = tmp_path / "track.mp3"
    subprocess.run(
        [FFMPEG, "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=mono", "-t", "1", str(path)],
        check=True,
    )
    monkeypatch.setattr(cfg, "fetch_lyrics", True)
    monkeypatch.setattr(cfg, "lyrics_lrc", True)
    monkeypatch.setattr(
        svc,
        "_lookup_lyrics",
        lambda p, r: Lyrics(plain="hello", synced="[00:01.00] hello", instrumental=False),
    )
    svc.apply(ApplyRequest(path=str(path), title="T", artist="A"), path)

    lrc = tmp_path / "track.lrc"
    assert lrc.exists() and lrc.read_text(encoding="utf-8") == "[00:01.00] hello"
    from mutagen.id3 import ID3  # plain still embedded in the tag

    assert ID3(str(path)).getall("USLT")[0].text == "hello"


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available to synth audio")
def test_apply_no_lrc_when_subtoggle_off(tmp_path, monkeypatch):
    from app.core.config import settings as cfg
    from app.services.lyrics import Lyrics

    path = tmp_path / "track.mp3"
    subprocess.run(
        [FFMPEG, "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=mono", "-t", "1", str(path)],
        check=True,
    )
    monkeypatch.setattr(cfg, "fetch_lyrics", True)
    monkeypatch.setattr(cfg, "lyrics_lrc", False)  # sub-toggle off
    monkeypatch.setattr(
        svc, "_lookup_lyrics",
        lambda p, r: Lyrics(plain="hi", synced="[00:01.00] hi", instrumental=False),
    )
    svc.apply(ApplyRequest(path=str(path), title="T", artist="A"), path)
    assert not (tmp_path / "track.lrc").exists()  # no sidecar


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


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available to synth audio")
def test_write_wav_tags_text_only(tmp_path):
    # WAV used to raise an unhandled TypeError (-> HTTP 500) via mutagen's Easy
    # interface. It must now write text tags through its ID3 chunk and, since WAV
    # has no reliable cover frame, report no embedded cover instead of crashing.
    from mutagen.wave import WAVE

    path = tmp_path / "track.wav"
    subprocess.run(
        [FFMPEG, "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=mono", "-t", "1", str(path)],
        check=True,
    )
    tags = {"title": "Disociando", "artist": "Artist", "album": "Album",
            "date": "2024", "tracknumber": 3}

    embedded = svc._write_tags(path, tags, FAKE_COVER)
    assert embedded is False

    reread = WAVE(str(path))
    assert str(reread.tags.get("TIT2")) == "Disociando"
    assert str(reread.tags.get("TPE1")) == "Artist"
    assert str(reread.tags.get("TALB")) == "Album"


# --- WebP → JPEG cover conversion ----------------------------------------

# Minimal valid WebP (1×1 red pixel, generated by ffmpeg).
_WEBP_1x1 = (
    b"RIFF\x3c\x00\x00\x00WEBPVP8 0\x00\x00\x00\xd0\x01\x00\x9d\x01*"
    b"\x01\x00\x01\x00\x02\x004%\xa0\x02t\xba\x01\xf8\x00\x03\xb0\x00"
    b"\xfe\xf0\xe8\xf7\xff \xb9au\xc8\xd7\xff ?\xe4\x07\xfc\x80\xff"
    b"\xf8\xf2\x00\x00\x00"
)


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available")
def test_webp_to_jpeg_converts():
    result = svc._webp_to_jpeg(_WEBP_1x1)
    assert result is not None
    # JPEG files start with ff d8.
    assert result[:2] == b"\xff\xd8"


def test_webp_to_jpeg_returns_none_without_ffmpeg(monkeypatch):
    # Point at a binary that doesn't exist → subprocess fails → None (no raise).
    monkeypatch.setattr(svc, "ffmpeg_path", lambda: "/nonexistent/ffmpeg-binary")
    assert svc._webp_to_jpeg(_WEBP_1x1) is None


def test_webp_to_jpeg_returns_none_on_bad_data():
    # Garbage with the right RIFF/WEBP magic but invalid payload.
    bad = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20
    result = svc._webp_to_jpeg(bad)
    # Should return None gracefully (ffmpeg exits non-zero), never raise.
    assert result is None


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available")
def test_fetch_cover_converts_webp(monkeypatch):
    """_fetch_cover detects WebP by magic bytes and converts to JPEG."""
    monkeypatch.setattr(
        svc, "fetch_public",
        lambda url, **kw: (_WEBP_1x1, "image/webp"),
    )
    result = svc._fetch_cover("https://example.com/cover.webp")
    assert result is not None
    data, mime = result
    assert mime == "image/jpeg"
    assert data[:2] == b"\xff\xd8"


def test_fetch_cover_passes_jpeg_through(monkeypatch):
    """JPEG data is returned as-is (no conversion)."""
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    monkeypatch.setattr(
        svc, "fetch_public",
        lambda url, **kw: (jpeg, "image/jpeg"),
    )
    result = svc._fetch_cover("https://example.com/cover.jpg")
    assert result is not None
    data, mime = result
    assert mime == "image/jpeg"
    assert data is jpeg  # exact same object, not re-encoded

