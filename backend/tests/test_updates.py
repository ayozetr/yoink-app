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


def test_whats_new_single_when_no_since(monkeypatch):
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


def test_whats_new_is_cumulative_and_ordered(monkeypatch):
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


def test_whats_new_falls_back_when_list_empty(monkeypatch):
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
