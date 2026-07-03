"""Tests for the update / release-notes helpers + the `/release-notes` route."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models.media import ReleaseNotes
from app.services.updates import _trim_notes

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
        "app.routers.settings.updates.release_notes",
        lambda tag: ReleaseNotes(version=tag, notes="## Hi\n- a"),
    )
    response = client.get("/api/release-notes")
    assert response.status_code == 200
    body = response.json()
    assert body["notes"] == "## Hi\n- a"
    assert body["version"].startswith("v")  # current version, tagged
