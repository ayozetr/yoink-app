"""Tests for the /api/po-token/* endpoints (the WebView minting bridge)."""

from __future__ import annotations

import base64
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.po_token_bridge import broker

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_broker():
    broker._reset()
    yield
    broker._reset()


def test_pending_returns_204_when_empty():
    r = client.get("/api/po-token/pending")
    assert r.status_code == 204


def test_pending_then_result_round_trip():
    result: dict[str, str | None] = {}

    def requester():
        result["token"] = broker.submit_mint("vidROUTE", timeout=3.0)

    t = threading.Thread(target=requester)
    t.start()

    r = client.get("/api/po-token/pending")
    assert r.status_code == 200
    job = r.json()
    assert job["video_id"] == "vidROUTE"

    r2 = client.post(
        "/api/po-token/result", json={"id": job["id"], "token": "TOK-123"}
    )
    assert r2.status_code == 200 and r2.json()["ok"] is True

    t.join(timeout=3.0)
    assert result["token"] == "TOK-123"


def test_result_for_unknown_job_reports_not_delivered():
    r = client.post("/api/po-token/result", json={"id": "nope", "token": "x"})
    assert r.status_code == 200 and r.json()["ok"] is False


def test_proxy_rejects_non_google_host():
    r = client.post("/api/po-token/proxy", json={"url": "https://evil.example.com/x"})
    assert r.status_code == 400


def test_proxy_rejects_bad_scheme():
    r = client.post("/api/po-token/proxy", json={"url": "file:///etc/passwd"})
    assert r.status_code == 400


def test_proxy_forwards_allowed_host(monkeypatch):
    # Stub the shared opener so no real network call is made.
    class _Resp:
        status = 200
        headers = {"Content-Type": "application/json"}

        def read(self, _n):
            return b'{"ok":true}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "app.routers.po_token.OPENER.open", lambda *a, **k: _Resp()
    )
    r = client.post(
        "/api/po-token/proxy",
        json={"url": "https://jnn-pa.googleapis.com/$rpc/x", "method": "POST"},
    )
    assert r.status_code == 200
    body = base64.b64decode(r.json()["body_b64"])
    assert body == b'{"ok":true}'
    assert r.json()["status"] == 200
