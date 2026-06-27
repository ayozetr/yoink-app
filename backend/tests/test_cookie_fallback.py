"""Browser-cookie failure → fall back to the cookies file / none."""

from __future__ import annotations

import pytest

from app.core import ytdlp_options as opt
from app.core.config import settings


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


def test_fallback_retries_on_any_error_when_browser_set(monkeypatch):
    # Browser cookie failures surface as wildly different error strings across
    # OS/browser/version, so when a browser is set we retry on *any* first failure
    # rather than pattern-matching the message.
    monkeypatch.setattr(settings, "cookies_from_browser", "chrome")
    monkeypatch.setattr(settings, "cookies_file", None)
    calls: list[dict] = []

    def run(net):
        calls.append(net)
        if "cookiesfrombrowser" in net:
            raise RuntimeError("could not find chrome cookies database")  # unrecognized phrasing
        return "ok"

    assert opt.with_cookie_fallback(run) == "ok"
    assert len(calls) == 2
    assert "cookiesfrombrowser" not in calls[1]


def test_fallback_skipped_without_browser(monkeypatch):
    monkeypatch.setattr(settings, "cookies_from_browser", None)
    calls: list[dict] = []

    def run(net):
        calls.append(net)
        raise RuntimeError("Could not copy Chrome cookie database")

    with pytest.raises(RuntimeError):  # nothing to fall back from
        opt.with_cookie_fallback(run)
    assert len(calls) == 1  # no retry


def test_fallback_propagates_error_when_retry_also_fails(monkeypatch):
    # The browser wasn't the (only) problem — surface the cleaner without-browser
    # error so the user sees the real cause, not the cookie noise.
    monkeypatch.setattr(settings, "cookies_from_browser", "edge")
    monkeypatch.setattr(settings, "cookies_file", None)

    def run(net):
        if "cookiesfrombrowser" in net:
            raise RuntimeError("Could not copy Edge cookie database")
        raise RuntimeError("HTTP Error 403: Forbidden")

    with pytest.raises(RuntimeError, match="403"):
        opt.with_cookie_fallback(run)


def test_fallback_no_retry_on_success(monkeypatch):
    monkeypatch.setattr(settings, "cookies_from_browser", "edge")
    calls: list[dict] = []

    def run(net):
        calls.append(net)
        return "ok"

    assert opt.with_cookie_fallback(run) == "ok"
    assert len(calls) == 1
