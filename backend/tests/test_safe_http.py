"""Tests for the SSRF-safe HTTP guard + the auto-tag cover fetch that uses it.

All offline: the guard rejects non-public/bad-scheme URLs before any socket is
opened, so resolving localhost/literal IPs is the only network touched.
"""

from __future__ import annotations

import pytest

from app.core.safe_http import (
    SafeHTTPError,
    fetch_public,
    host_is_blocked,
    ip_is_public,
)


def test_ip_is_public():
    assert ip_is_public("8.8.8.8")
    assert not ip_is_public("127.0.0.1")
    assert not ip_is_public("10.0.0.5")
    assert not ip_is_public("192.168.1.1")
    assert not ip_is_public("169.254.169.254")  # cloud metadata endpoint
    assert not ip_is_public("::1")
    assert not ip_is_public("not-an-ip")


def test_host_is_blocked():
    assert host_is_blocked(None)
    assert host_is_blocked("localhost")  # → 127.0.0.1
    assert host_is_blocked("nonexistent.invalid.")  # resolution fails → blocked
    assert not host_is_blocked("8.8.8.8")  # public literal IP


def test_fetch_public_rejects_bad_scheme():
    for url in ("file:///etc/passwd", "ftp://example.com/x", "gopher://x"):
        with pytest.raises(SafeHTTPError):
            fetch_public(url)


def test_fetch_public_rejects_internal_hosts():
    for url in (
        "http://127.0.0.1:8756/api/version",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/",
        "http://10.0.0.1/",
    ):
        with pytest.raises(SafeHTTPError):
            fetch_public(url)


def test_autotag_cover_fetch_blocks_ssrf():
    # The endpoint that this fix closes: a client-supplied cover_url must not be
    # turnable into an internal read/probe — _fetch_cover returns None, no fetch.
    from app.services.autotag_service import _fetch_cover

    assert _fetch_cover("http://127.0.0.1:8756/api/version") is None
    assert _fetch_cover("http://169.254.169.254/") is None
    assert _fetch_cover("file:///etc/passwd") is None
    assert _fetch_cover("http://localhost/") is None
