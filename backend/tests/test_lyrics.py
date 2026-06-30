"""LRCLIB lyrics lookup (mocked HTTP)."""

from __future__ import annotations

from app.services import lyrics as lyr


def test_get_returns_plain_and_synced(monkeypatch):
    monkeypatch.setattr(
        lyr,
        "_get_json",
        lambda url: (
            {"plainLyrics": "la la la", "syncedLyrics": "[00:01.00] la", "instrumental": False}
            if "/get?" in url
            else None
        ),
    )
    r = lyr.fetch_lyrics("Song", "Artist", "Album", 200)
    assert r is not None
    assert r.plain == "la la la"
    assert r.synced.startswith("[00:01")
    assert r.instrumental is False


def test_falls_back_to_search(monkeypatch):
    def fake(url: str):
        if "/get?" in url:
            return None  # exact match misses
        if "/search?" in url:
            return [{"plainLyrics": "found via search", "instrumental": False}]
        return None

    monkeypatch.setattr(lyr, "_get_json", fake)
    r = lyr.fetch_lyrics("Song", "Artist")
    assert r is not None and r.plain == "found via search"


def test_instrumental_flagged(monkeypatch):
    monkeypatch.setattr(
        lyr,
        "_get_json",
        lambda url: {"instrumental": True, "plainLyrics": None, "syncedLyrics": None},
    )
    r = lyr.fetch_lyrics("Song", "Artist", duration=100)
    assert r is not None and r.instrumental and r.plain is None


def test_none_when_nothing_found(monkeypatch):
    monkeypatch.setattr(lyr, "_get_json", lambda url: None)
    assert lyr.fetch_lyrics("Song", "Artist") is None


def test_title_duration_fallback_when_artist_differs(monkeypatch):
    # All artist-keyed lookups miss (the source's artist differs from LRCLIB's —
    # e.g. a renamed act or a YouTube channel name), but a title-only search
    # returns a same-title hit whose duration matches -> used.
    def fake(url: str):
        if "/get?" in url:
            return None
        if "artist_name=" in url:  # structured + (no) fuzzy artist matches miss
            return []
        if "/search?" in url:  # title-only search
            return [
                {"trackName": "Song", "artistName": "Other", "duration": 999,
                 "plainLyrics": "wrong duration", "instrumental": False},
                {"trackName": "Song", "artistName": "Real Name", "duration": 200,
                 "plainLyrics": "right one", "syncedLyrics": "[00:01.00] x",
                 "instrumental": False},
            ]
        return None

    monkeypatch.setattr(lyr, "_get_json", fake)
    r = lyr.fetch_lyrics("Song", "Wrong Artist", duration=200)
    assert r is not None and r.plain == "right one"  # duration picked the right hit

    # Without a duration the fallback can't run -> nothing from a title search.
    monkeypatch.setattr(
        lyr, "_get_json",
        lambda url: None if "/get?" in url else ([] if "artist_name=" in url else None),
    )
    assert lyr.fetch_lyrics("Song", "Wrong Artist") is None


def test_empty_title_short_circuits(monkeypatch):
    called = False

    def fake(url):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(lyr, "_get_json", fake)
    assert lyr.fetch_lyrics("", "Artist") is None
    assert called is False  # no network for an empty title


def test_falls_back_to_free_text_query(monkeypatch):
    # Structured track+artist search misses (e.g. multi-artist), but the fuzzy
    # free-text `q` search finds it.
    def fake(url: str):
        if "/get?" in url:
            return None
        if "track_name=" in url and "q=" not in url:
            return []  # strict search misses
        if "q=" in url:
            return [{"plainLyrics": "found via q", "instrumental": False}]
        return None

    monkeypatch.setattr(lyr, "_get_json", fake)
    r = lyr.fetch_lyrics("Qué Cruel", "Daniela Garsal, Cruz Cafuné")
    assert r is not None and r.plain == "found via q"


def test_retries_with_primary_artist(monkeypatch):
    # Apple Music's "& Cruzzi" misses on LRCLIB; the primary "Daniela Garsal" hits.
    def fake(url: str):
        if "/get?" in url:
            return None
        if "track_name=" in url and "q=" not in url:
            return []
        if "q=" in url:
            return [] if "Cruzzi" in url else [{"plainLyrics": "ok", "instrumental": False}]
        return None

    monkeypatch.setattr(lyr, "_get_json", fake)
    r = lyr.fetch_lyrics("QUÉ CRUEL", "Daniela Garsal & Cruzzi")
    assert r is not None and r.plain == "ok"
