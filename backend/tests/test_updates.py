"""Tests for the update / release-notes helpers + the `/release-notes` route."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models.media import ReleaseNotes, WhatsNew
from app.services import updates
from app.services.updates import _trim_notes, whats_new

client = TestClient(app)


def test_trim_notes_cuts_at_marker():
    body = "Intro.\n\n## Feature\n- x\n\n<!-- /whatsnew -->\n\n## Downloads\n| a |"
    assert _trim_notes(body) == "Intro.\n\n## Feature\n- x"


def test_trim_notes_falls_back_to_downloads():
    body = "Intro.\n\n## Feature\n\n## Downloads\n| a | b |"
    assert _trim_notes(body) == "Intro.\n\n## Feature"


def test_trim_notes_keeps_whole_body_when_no_marker():
    body = "Just some notes.\nMore."
    assert _trim_notes(body) == "Just some notes.\nMore."


def test_release_notes_endpoint(monkeypatch):
    monkeypatch.setattr(
        "app.routers.settings.updates.whats_new",
        lambda current, since: WhatsNew(
            entries=[ReleaseNotes(version=f"v{current}", notes="## Hi\n- a")]
        ),
    )
    response = client.get("/api/release-notes")
    assert response.status_code == 200
    body = response.json()
    entries = body["entries"]
    assert len(entries) == 1
    assert entries[0]["notes"] == "## Hi\n- a"
    assert entries[0]["version"].startswith("v")  # current version, tagged


def test_whats_new_single_when_no_since(temp_dirs, monkeypatch):
    """With no `since` (fresh install / same version) only the current release."""
    monkeypatch.setattr(
        updates,
        "release_notes",
        lambda tag, timeout=8.0: ReleaseNotes(version=tag, notes="## Now\n- x"),
    )
    # A list fetch would be a real network call — assert it's never reached.
    monkeypatch.setattr(
        updates, "_release_list", lambda timeout=8.0: _fail("should not fetch")
    )
    result = whats_new("3.4.0", since=None)
    assert [e.version for e in result.entries] == ["v3.4.0"]


def test_whats_new_is_cumulative_and_ordered(temp_dirs, monkeypatch):
    """`since < version <= current`, newest first; older/newer are dropped."""
    releases = [
        {"tag_name": "v3.5.0", "body": "## Next\n- too new"},   # > current, dropped
        {"tag_name": "v3.4.0", "body": "## 3.4\n- a\n\n## Downloads\n|x|"},
        {"tag_name": "v3.2.0", "body": "## 3.2\n- b"},
        {"tag_name": "v3.1.0", "body": "## 3.1\n- c"},
        {"tag_name": "v3.0.0", "body": "## 3.0\n- old"},         # == since, dropped
        {"tag_name": "ext-latest", "body": "extension"},          # not a version
    ]
    monkeypatch.setattr(updates, "_release_list", lambda timeout=8.0: releases)
    result = whats_new("3.4.0", since="3.0.0")
    assert [e.version for e in result.entries] == ["v3.4.0", "v3.2.0", "v3.1.0"]
    # Bodies are trimmed to the what's-new part (Downloads table stripped).
    assert result.entries[0].notes == "## 3.4\n- a"


def test_whats_new_falls_back_when_list_empty(temp_dirs, monkeypatch):
    """If the release list can't be fetched, degrade to the single current one."""
    monkeypatch.setattr(updates, "_release_list", lambda timeout=8.0: [])
    monkeypatch.setattr(
        updates,
        "release_notes",
        lambda tag, timeout=8.0: ReleaseNotes(version=tag, notes="## Only\n- x"),
    )
    result = whats_new("3.4.0", since="3.0.0")
    assert [e.version for e in result.entries] == ["v3.4.0"]


def _fail(message: str):
    raise AssertionError(message)


class _FakeResp:
    """Minimal stand-in for a urlopen() response (a context manager json can read)."""

    def __init__(self, payload):
        self._raw = __import__("json").dumps(payload).encode()

    def read(self, *_a):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_whats_new_caches_and_serves_without_refetch(temp_dirs, monkeypatch):
    """A released version's notes are immutable — fetch once, then serve cached."""
    calls = {"n": 0}

    def fake_list(timeout=8.0):
        calls["n"] += 1
        return [{"tag_name": "v3.4.0", "body": "## 3.4\n- a"}]

    monkeypatch.setattr(updates, "_release_list", fake_list)
    first = whats_new("3.4.0", since="3.0.0")
    second = whats_new("3.4.0", since="3.0.0")
    assert [e.version for e in first.entries] == ["v3.4.0"]
    assert [e.version for e in second.entries] == ["v3.4.0"]
    assert calls["n"] == 1  # the second call was served from cache, no GitHub hit


def test_check_for_updates_caches_then_skips_github(temp_dirs, monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(_req, timeout=None, context=None):
        calls["n"] += 1
        return _FakeResp({"tag_name": "v9.9.9", "html_url": "http://x/r"})

    monkeypatch.setattr(updates.urllib.request, "urlopen", fake_urlopen)
    first = updates.check_for_updates()
    second = updates.check_for_updates()  # within TTL → cached, no second hit
    assert first.latest == "v9.9.9" and second.latest == "v9.9.9"
    assert calls["n"] == 1


def test_check_for_updates_serves_stale_on_failure(temp_dirs, monkeypatch):
    monkeypatch.setattr(
        updates.urllib.request,
        "urlopen",
        lambda _req, timeout=None, context=None: _FakeResp(
            {"tag_name": "v9.9.9", "html_url": "http://x"}
        ),
    )
    updates.check_for_updates()  # prime the cache

    # Expire the cache and make GitHub fail — the stale value is served, no error.
    monkeypatch.setattr(updates, "_UPDATE_CHECK_TTL", -1)

    def boom(_req, timeout=None, context=None):
        raise updates.urllib.error.URLError("down")

    monkeypatch.setattr(updates.urllib.request, "urlopen", boom)
    result = updates.check_for_updates()
    assert result.latest == "v9.9.9" and result.error is None
