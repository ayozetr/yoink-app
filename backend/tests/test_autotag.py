"""Tests for the audio auto-tagging service.

The AcoustID/MusicBrainz network calls are not exercised here; we test the pure
selection logic (best recording, album-ranking heuristic, small helpers) and the
per-format tag writing round-trip (mp3/m4a/flac, skipped without ffmpeg).
"""

from __future__ import annotations

import shutil
import subprocess

import mutagen
import pytest

from app.services import autotag_service as svc

FFMPEG = shutil.which("ffmpeg")
# Arbitrary bytes — mutagen stores cover data verbatim, it doesn't decode it.
FAKE_COVER = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png")


# --- best-recording selection ---------------------------------------------

def test_best_recording_skips_metadataless_and_honours_score():
    response = {
        "results": [
            {"score": 0.95, "recordings": [{"id": "r1"}]},  # no title/artists
            {
                "score": 0.80,
                "recordings": [
                    {"id": "r2", "title": "Song", "artists": [{"name": "A"}]}
                ],
            },
        ]
    }
    rec, score = svc._best_recording(response)
    assert rec["id"] == "r2"
    assert score == 0.80


def test_best_recording_no_match():
    rec, score = svc._best_recording({"results": []})
    assert rec is None
    assert score == 0.0


# --- album ranking heuristic ----------------------------------------------

def test_album_options_studio_first_oldest_first(monkeypatch):
    years = {"old": "1980", "new": "2010", "comp": "1995"}
    monkeypatch.setattr(svc, "_release_group_year", lambda rgid: years.get(rgid))

    groups = [
        {"id": "new", "title": "New Album", "type": "Album", "secondarytypes": []},
        {"id": "comp", "title": "Greatest Hits", "type": "Album",
         "secondarytypes": ["Compilation"]},
        {"id": "old", "title": "Debut", "type": "Album", "secondarytypes": []},
    ]
    options = svc._album_options(groups)

    # Plain studio albums first, oldest first.
    assert options[0].title == "Debut"
    assert options[0].year == "1980"
    assert options[0].is_studio_album is True
    assert options[1].title == "New Album"
    # The compilation is included but flagged non-studio (and ranked after).
    comp = next(o for o in options if o.title == "Greatest Hits")
    assert comp.is_studio_album is False
    assert options.index(comp) > 1


def test_album_options_empty():
    assert svc._album_options([]) == []


# --- small helpers ---------------------------------------------------------

def test_helpers():
    assert svc._join_artists([{"name": "A"}, {"name": "B"}, {}]) == "A, B"
    assert svc._credit_name([{"artist": {"name": "X"}}, " feat. ",
                             {"artist": {"name": "Y"}}]) == "X feat. Y"
    assert svc._int_or_zero("42") == 42
    assert svc._int_or_zero(None) == 0
    assert svc._int_or_zero("nope") == 0
    assert svc._cover_url("abc").endswith("/release-group/abc/front")


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
    assert embedded is True  # mp3/m4a/flac all support cover art

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
    embedded = svc._write_tags(path, {"title": "Only Title"}, None)
    assert embedded is False
    assert mutagen.File(str(path), easy=True)["title"][0] == "Only Title"
