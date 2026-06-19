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


def test_info_transient_error_maps_to_503(monkeypatch):
    from app.services.ytdlp_service import MediaExtractionError

    def boom(url):
        raise MediaExtractionError("HTTP Error 403: Forbidden", transient=True)

    monkeypatch.setattr("app.routers.info.extract_info", boom)
    response = client.post("/api/info", json={"url": "https://youtu.be/x"})
    assert response.status_code == 503
    # Friendly, retryable message — not the raw yt-dlp error.
    assert "temporarily unavailable" in response.json()["detail"].lower()


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


def test_settings_get_and_put(temp_dirs):
    body = client.get("/api/settings").json()
    assert "download_dir" in body and body["default_kind"] in ("video", "audio")

    payload = {
        **body,
        "default_kind": "audio",
        "default_quality": "480p",
        "default_container": "mkv",
        "default_audio_format": "flac",
        "default_embed_subs": True,
        "default_embed_chapters": True,
        "nfo_sidecars": True,
        "cookies_from_browser": "firefox",
        "cookies_file": None,
        "download_dir": str(temp_dirs / "dl"),
        "filename_template": "%(uploader)s - %(title)s",
        "rate_limit": "1M",
        "video_codec": "h264",
        "audio_bitrate": "320",
        "proxy": "socks5://127.0.0.1:1080",
    }
    saved = client.put("/api/settings", json=payload)
    assert saved.status_code == 200
    assert saved.json()["default_kind"] == "audio"
    assert saved.json()["default_container"] == "mkv"
    assert saved.json()["default_audio_format"] == "flac"
    assert saved.json()["default_embed_subs"] is True
    assert saved.json()["default_embed_chapters"] is True
    assert saved.json()["nfo_sidecars"] is True
    assert saved.json()["cookies_from_browser"] == "firefox"
    assert saved.json()["filename_template"] == "%(uploader)s - %(title)s"
    assert saved.json()["rate_limit"] == "1M"
    assert saved.json()["video_codec"] == "h264"
    assert saved.json()["audio_bitrate"] == "320"
    assert saved.json()["proxy"] == "socks5://127.0.0.1:1080"
    # Persisted to disk.
    assert (temp_dirs / "data" / "settings.json").exists()


def test_settings_put_rejects_bad_values(temp_dirs):
    base = client.get("/api/settings").json()

    # Unsupported browser for cookies.
    bad_browser = {**base, "cookies_from_browser": "netscape", "cookies_file": None}
    assert client.put("/api/settings", json=bad_browser).status_code == 400

    # Proxy with an unsupported scheme.
    bad_proxy = {**base, "cookies_from_browser": None, "proxy": "ftp://x:1"}
    assert client.put("/api/settings", json=bad_proxy).status_code == 400

    # A known browser with a profile suffix (e.g. "firefox:work") is accepted.
    ok = {**base, "cookies_from_browser": "firefox:work", "cookies_file": None, "proxy": None}
    assert client.put("/api/settings", json=ok).status_code == 200


def test_quality_label(monkeypatch):
    from app.core.config import settings
    from app.models.media import DownloadRequest
    from app.routers.download import _quality_label

    video = DownloadRequest(url="https://x.com/v", kind="video", quality="1080p")
    assert _quality_label(video, None) == "1080p"
    best_video = DownloadRequest(url="https://x.com/v", kind="video", quality="best")
    assert _quality_label(best_video, None) is None

    # Audio with a fixed bitrate target uses it directly (no ffprobe needed) and
    # never repeats the format (which already shows as its own badge).
    monkeypatch.setattr(settings, "audio_bitrate", "192")
    audio = DownloadRequest(url="https://x.com/a", kind="audio", audio_format="mp3")
    assert _quality_label(audio, None) == "192 kbps"

    # "best" with no probeable file falls back to no label (not the format).
    monkeypatch.setattr(settings, "audio_bitrate", "best")
    assert _quality_label(audio, None) is None


def test_version_endpoint(monkeypatch):
    from app.models.media import VersionInfo

    monkeypatch.setattr(
        "app.routers.settings.updates.check_for_updates",
        lambda: VersionInfo(
            current="0.5.0",
            latest="v0.6.0",
            update_available=True,
            release_url="https://github.com/ayozetr/yoink-app/releases/tag/v0.6.0",
        ),
    )
    body = client.get("/api/version").json()
    assert body["current"] == "0.5.0"
    assert body["update_available"] is True
    assert body["latest"] == "v0.6.0"


def test_thumbnail_rejects_non_http_scheme():
    # SSRF guard: only http(s) URLs are proxied; other schemes are rejected
    # before any network access happens.
    for bad in ("file:///etc/passwd", "ftp://example.com/img.jpg"):
        response = client.get("/api/thumbnail", params={"url": bad})
        assert response.status_code == 400


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


def test_thumbnail_rejects_internal_and_non_http_hosts():
    # SSRF guard: the proxy must refuse loopback/private/link-local/metadata
    # hosts and non-http(s) schemes, before any network fetch.
    for target in (
        "http://127.0.0.1:8756/x.jpg",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/x.jpg",
        "http://192.168.1.1/x.jpg",
        "file:///etc/passwd",
    ):
        resp = client.get("/api/thumbnail", params={"url": target})
        assert resp.status_code == 400, target


def test_cover_path_guards(temp_dirs):
    # Outside the download dir → 403; inside but nonexistent → 404.
    assert client.get("/api/cover", params={"path": "/etc/passwd"}).status_code == 403
    inside = str(temp_dirs / "downloads" / "nope.mp3")
    assert client.get("/api/cover", params={"path": inside}).status_code == 404


def test_search_returns_results(monkeypatch):
    from app.models.media import PlaylistEntry

    fake = [
        PlaylistEntry(
            id="abc",
            title="A Song",
            url="https://youtu.be/abc",
            duration_string="3:21",
            thumbnail_url="https://i.ytimg.com/vi/abc/mqdefault.jpg",
            uploader="A Channel",
        )
    ]
    monkeypatch.setattr(
        "app.routers.info.search_youtube", lambda q, source="youtube": fake
    )
    resp = client.get("/api/search", params={"q": "a song"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"][0]["title"] == "A Song"
    assert body["results"][0]["url"] == "https://youtu.be/abc"


def test_search_requires_a_query():
    # q is required with min_length=1 → empty query is a 422.
    assert client.get("/api/search", params={"q": ""}).status_code == 422


def test_search_source_is_forwarded(monkeypatch):
    # The `source` param is validated and passed through to the service.
    seen: dict[str, str] = {}

    def fake(q: str, source: str = "youtube"):
        seen["source"] = source
        return []

    monkeypatch.setattr("app.routers.info.search_youtube", fake)
    assert (
        client.get("/api/search", params={"q": "x", "source": "soundcloud"}).status_code
        == 200
    )
    assert seen["source"] == "soundcloud"
    # An unknown source is rejected by the pattern guard.
    assert (
        client.get("/api/search", params={"q": "x", "source": "vimeo"}).status_code
        == 422
    )


def test_ytdlp_version_endpoint(monkeypatch):
    from app.models.media import VersionInfo

    monkeypatch.setattr(
        "app.routers.settings.updates.check_ytdlp_update",
        lambda: VersionInfo(
            current="2024.01.01", latest="2024.02.02", update_available=True
        ),
    )
    resp = client.get("/api/ytdlp-version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"] == "2024.01.01"
    assert body["update_available"] is True
