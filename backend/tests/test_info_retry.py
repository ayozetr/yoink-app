"""Transient-vs-permanent classification + the /api/info retry loop."""

from __future__ import annotations

import pytest
from yt_dlp.utils import DownloadError

import app.services.ytdlp_service as svc


def test_is_transient_error_classification():
    assert svc._is_transient_error("ERROR: HTTP Error 403: Forbidden")
    assert svc._is_transient_error("HTTP Error 429: Too Many Requests")
    assert svc._is_transient_error("HTTP Error 503: Service Unavailable")
    assert svc._is_transient_error("Read timed out")
    assert svc._is_transient_error("Unable to download webpage: getaddrinfo failed")
    # Permanent — must NOT be retried:
    assert not svc._is_transient_error("Unsupported URL: https://x/y")
    assert not svc._is_transient_error("Video unavailable")
    assert not svc._is_transient_error("Private video.")
    # A 404 fronted by the generic wrapper is permanent, not transient — the
    # broad "unable to download webpage" marker must not catch it.
    assert not svc._is_transient_error(
        "Unable to download webpage: HTTP Error 404: Not Found"
    )


def _patch_failing_ydl(monkeypatch, message: str):
    """Replace YoutubeDL with a fake whose extract_info always raises `message`."""
    calls = {"n": 0}

    class FakeYDL:
        def __init__(self, opts):  # noqa: D401, ANN001
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def add_info_extractor(self, _ie):
            pass

        def extract_info(self, _url, download=False):  # noqa: ANN001
            calls["n"] += 1
            raise DownloadError(message)

        def sanitize_info(self, x):  # noqa: ANN001
            return x

    monkeypatch.setattr(svc, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(svc, "register_threads_ie", lambda _ydl: None)
    monkeypatch.setattr(svc, "register_embedded_vr", lambda _ydl: None)
    monkeypatch.setattr(svc.time, "sleep", lambda _s: None)  # no real backoff delay
    return calls


def test_permanent_error_is_not_retried(monkeypatch):
    calls = _patch_failing_ydl(monkeypatch, "Unsupported URL: https://x/y")
    with pytest.raises(svc.MediaExtractionError) as err:
        svc.extract_info("https://x/y")
    assert err.value.transient is False
    # One attempt only: primary + tolerant fallback = 2 extract_info calls.
    assert calls["n"] == 2


def test_transient_error_is_retried_then_gives_up(monkeypatch):
    calls = _patch_failing_ydl(monkeypatch, "HTTP Error 403: Forbidden")
    with pytest.raises(svc.MediaExtractionError) as err:
        svc.extract_info("https://youtu.be/x")
    assert err.value.transient is True
    # Retried up to _INFO_MAX_ATTEMPTS, each attempt = 2 extract_info calls.
    assert calls["n"] == 2 * svc._INFO_MAX_ATTEMPTS
