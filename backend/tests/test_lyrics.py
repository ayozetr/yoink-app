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


def test_empty_title_short_circuits(monkeypatch):
    called = False

    def fake(url):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(lyr, "_get_json", fake)
    assert lyr.fetch_lyrics("", "Artist") is None
    assert called is False  # no network for an empty title
