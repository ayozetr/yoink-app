"""Tests for the HTTP routes via FastAPI's TestClient.

Network-touching extraction is monkeypatched so these stay fast and offline.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models.media import InfoResponse, VideoInfo
from app.services import history_store

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_info_returns_video(monkeypatch):
    fake = InfoResponse(
        type="video",
        video=VideoInfo(id="abc", title="Clip", formats=[]),
    )
    monkeypatch.setattr("app.routers.info.extract_info", lambda url: fake)

    response = client.post("/api/info", json={"url": "https://example.com/v"})
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "video"
    assert body["video"]["title"] == "Clip"


def test_info_rejects_bad_url():
    response = client.post("/api/info", json={"url": "not-a-url"})
    assert response.status_code == 422


def test_info_extraction_error(monkeypatch):
    from app.services.ytdlp_service import MediaExtractionError

    def boom(url):
        raise MediaExtractionError("nope")

    monkeypatch.setattr("app.routers.info.extract_info", boom)
    response = client.post("/api/info", json={"url": "https://example.com/v"})
    assert response.status_code == 422
    assert "nope" in response.json()["detail"]


def test_history_list_and_clear(history_db):
    history_store.add_entry(
        title="One", url="http://x", kind="audio", status="completed", filesize=100
    )

    listed = client.get("/api/history")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    stats = client.get("/api/history/stats").json()
    assert stats["total_downloads"] == 1

    cleared = client.delete("/api/history")
    assert cleared.status_code == 204
    assert client.get("/api/history").json() == []


def test_open_folder(temp_dirs, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        "app.routers.history._open_folder", lambda folder: opened.append(str(folder))
    )

    # Default: opens the download dir.
    response = client.post("/api/open", json={})
    assert response.status_code == 200
    assert opened and opened[0].endswith("downloads")

    # A path outside the download dir is rejected.
    rejected = client.post("/api/open", json={"path": "/etc/passwd"})
    assert rejected.status_code == 403
