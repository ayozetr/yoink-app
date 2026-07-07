"""Integration tests for the download WebSocket (WS /api/ws/download).

The yt-dlp job (``download_events``) is mocked so these stay fast and offline;
we assert the typed event stream, request validation, and the Origin guard.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.models.media import CompletedEvent, ProgressEvent

client = TestClient(app)


def test_ws_streams_progress_then_completed(monkeypatch):
    async def fake_events(request, cancel_event, disconnect_signal=None):
        yield ProgressEvent(status="downloading", percent=42.0)
        yield CompletedEvent(
            filename="song.mp3", filepath="/tmp/song.mp3", total_bytes=123
        )

    monkeypatch.setattr("app.routers.download.download_events", fake_events)

    with client.websocket_connect("/api/ws/download") as ws:
        ws.send_json({"url": "https://example.com/watch?v=x", "kind": "audio"})
        first = ws.receive_json()
        assert first["type"] == "progress"
        assert first["percent"] == 42.0
        second = ws.receive_json()
        assert second["type"] == "completed"
        assert second["filename"] == "song.mp3"


def test_ws_invalid_request_sends_error():
    with client.websocket_connect("/api/ws/download") as ws:
        ws.send_json({"url": "not-a-valid-url"})
        event = ws.receive_json()
        assert event["type"] == "error"


def test_ws_rejects_cross_origin():
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/api/ws/download", headers={"origin": "https://evil.example.com"}
        ) as ws:
            ws.receive_json()
