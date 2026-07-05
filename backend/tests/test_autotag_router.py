"""Tests for the /api/autotag/* HTTP routes: path guard and error mapping.

The service layer is covered in test_autotag.py; here we exercise the router —
the download-dir confinement (403/404) and AutotagError → 422 — via TestClient,
with the service functions mocked.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import (
    AUTOTAG_FILENAME_TEMPLATE,
    AUTOTAG_FILENAME_TEMPLATE_REVERSED,
    settings,
)
from app.main import app
from app.models.autotag import ApplyResponse, CandidateList, TagCandidate
from app.services.autotag_service import AutotagError

client = TestClient(app)


def _make_audio(name: str = "song.mp3"):
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    audio = settings.download_dir / name
    audio.write_bytes(b"\x00")
    return audio


def test_identify_returns_candidates(temp_dirs, monkeypatch):
    audio = _make_audio()
    monkeypatch.setattr(
        "app.routers.autotag.identify",
        lambda path: CandidateList(results=[TagCandidate(title="T", artist="A")]),
    )
    response = client.post("/api/autotag/identify", json={"path": str(audio)})
    assert response.status_code == 200
    assert response.json()["results"][0]["title"] == "T"


def test_search_returns_candidates(monkeypatch):
    monkeypatch.setattr(
        "app.routers.autotag.search",
        lambda artist, title: CandidateList(
            results=[TagCandidate(title="T", artist="A")]
        ),
    )
    response = client.post("/api/autotag/search", json={"artist": "A", "title": "T"})
    assert response.status_code == 200
    assert response.json()["results"][0]["artist"] == "A"


def test_apply_writes_tags(temp_dirs, monkeypatch):
    audio = _make_audio()
    monkeypatch.setattr(
        "app.routers.autotag.apply",
        lambda request, path: ApplyResponse(ok=True, embedded_cover=True),
    )
    response = client.post(
        "/api/autotag/apply", json={"path": str(audio), "title": "T"}
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "embedded_cover": True}


def test_path_outside_download_dir_is_403(temp_dirs):
    response = client.post("/api/autotag/identify", json={"path": "/etc/passwd"})
    assert response.status_code == 403


def test_missing_file_is_404(temp_dirs):
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    nope = settings.download_dir / "nope.mp3"
    response = client.post("/api/autotag/identify", json={"path": str(nope)})
    assert response.status_code == 404


def test_autotag_error_maps_to_422(temp_dirs, monkeypatch):
    audio = _make_audio()

    def boom(path):
        raise AutotagError("catalogue down")

    monkeypatch.setattr("app.routers.autotag.identify", boom)
    response = client.post("/api/autotag/identify", json={"path": str(audio)})
    assert response.status_code == 422


def _apply_capturing_rename(monkeypatch, template):
    """Drive /apply with the given filename_template, capturing the rename name."""
    audio = _make_audio()
    monkeypatch.setattr(
        "app.routers.autotag.apply",
        lambda request, path: ApplyResponse(ok=True, embedded_cover=False),
    )
    captured = {}

    def fake_rename(path, new_title):
        captured["name"] = new_title
        return path.with_name(new_title + ".mp3")

    monkeypatch.setattr("app.routers.autotag.rename_to_tagged", fake_rename)
    monkeypatch.setattr(
        "app.routers.autotag.history_store.update_after_tag", lambda *a: None
    )
    monkeypatch.setattr(settings, "filename_template", template)
    resp = client.post(
        "/api/autotag/apply",
        json={"path": str(audio), "artist": "Quevedo", "title": "Punto G"},
    )
    assert resp.status_code == 200
    return captured.get("name")


def test_apply_autotag_template_renames_artist_title(temp_dirs, monkeypatch):
    assert (
        _apply_capturing_rename(monkeypatch, AUTOTAG_FILENAME_TEMPLATE)
        == "Quevedo - Punto G"
    )


def test_apply_reversed_template_renames_title_artist(temp_dirs, monkeypatch):
    assert (
        _apply_capturing_rename(monkeypatch, AUTOTAG_FILENAME_TEMPLATE_REVERSED)
        == "Punto G - Quevedo"
    )
