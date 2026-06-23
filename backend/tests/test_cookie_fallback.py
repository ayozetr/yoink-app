"""Browser-cookie failure → fall back to the cookies file / none."""

from __future__ import annotations

import pytest

from app.core import ytdlp_options as opt
from app.core.config import settings


def test_is_browser_cookie_error():
    assert opt.is_browser_cookie_error("ERROR: Could not copy Chrome cookie database")
    assert opt.is_browser_cookie_error("Failed to decrypt the cookie with DPAPI")
    assert opt.is_browser_cookie_error("Could not find Edge cookies database")
    # Unrelated errors are not cookie errors.
    assert not opt.is_browser_cookie_error("HTTP Error 403: Forbidden")
    assert not opt.is_browser_cookie_error("Could not copy the output file")  # no cookie


def test_network_options_use_browser_toggle(monkeypatch):
    monkeypatch.setattr(settings, "cookies_from_browser", "edge")
    monkeypatch.setattr(settings, "cookies_file", "/tmp/cookies.txt")
    monkeypatch.setattr(settings, "proxy", None)
    # Default: the browser wins over the file.
    assert "cookiesfrombrowser" in opt.network_options()
    assert "cookiefile" not in opt.network_options()
    # use_browser=False: the browser is dropped, the file is used.
    nb = opt.network_options(use_browser=False)
    assert "cookiesfrombrowser" not in nb
    assert nb.get("cookiefile") == "/tmp/cookies.txt"


def test_fallback_retries_without_browser(monkeypatch):
    monkeypatch.setattr(settings, "cookies_from_browser", "edge")
    monkeypatch.setattr(settings, "cookies_file", "/tmp/c.txt")
    calls: list[dict] = []

    def run(net):
        calls.append(net)
        if "cookiesfrombrowser" in net:
            raise RuntimeError("Could not copy Edge cookie database")
        return "ok"

    assert opt.with_cookie_fallback(run) == "ok"
    assert len(calls) == 2  # browser, then fallback
    assert "cookiesfrombrowser" in calls[0]
    assert "cookiesfrombrowser" not in calls[1]


def test_fallback_skipped_without_browser(monkeypatch):
    monkeypatch.setattr(settings, "cookies_from_browser", None)

    def run(net):
        raise RuntimeError("Could not copy Chrome cookie database")

    with pytest.raises(RuntimeError):  # nothing to fall back from
        opt.with_cookie_fallback(run)


def test_fallback_reraises_non_cookie_error(monkeypatch):
    monkeypatch.setattr(settings, "cookies_from_browser", "edge")

    def run(net):
        raise RuntimeError("HTTP Error 403: Forbidden")

    with pytest.raises(RuntimeError):
        opt.with_cookie_fallback(run)


def test_fallback_no_retry_on_success(monkeypatch):
    monkeypatch.setattr(settings, "cookies_from_browser", "edge")
    calls: list[dict] = []

    def run(net):
        calls.append(net)
        return "ok"

    assert opt.with_cookie_fallback(run) == "ok"
    assert len(calls) == 1
