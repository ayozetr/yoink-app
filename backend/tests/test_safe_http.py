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
    assert ip_is_public("1.1.1.1")
    assert ip_is_public("2606:4700:4700::1111")  # public IPv6 (Cloudflare)
    assert not ip_is_public("127.0.0.1")
    assert not ip_is_public("10.0.0.5")
    assert not ip_is_public("192.168.1.1")
    assert not ip_is_public("172.16.0.1")  # private 172.16/12
    assert not ip_is_public("169.254.169.254")  # cloud metadata endpoint
    assert not ip_is_public("::1")
    assert not ip_is_public("fe80::1")  # IPv6 link-local
    assert not ip_is_public("0.0.0.0")  # unspecified
    assert not ip_is_public("224.0.0.1")  # multicast
    assert not ip_is_public("not-an-ip")


def test_host_is_blocked():
    assert host_is_blocked(None)
    assert host_is_blocked("")  # empty host
    assert host_is_blocked("localhost")  # → 127.0.0.1
    assert host_is_blocked("nonexistent.invalid.")  # resolution fails → blocked
    # Literal non-public addresses of every flavour (resolved locally, no DNS).
    assert host_is_blocked("::1")  # IPv6 loopback
    assert host_is_blocked("0.0.0.0")  # unspecified
    assert host_is_blocked("169.254.169.254")  # link-local (cloud metadata)
    assert host_is_blocked("224.0.0.1")  # multicast
    assert host_is_blocked("172.16.5.4")  # private
    assert not host_is_blocked("8.8.8.8")  # public literal IP
    assert not host_is_blocked("1.1.1.1")  # public literal IP


def test_host_is_blocked_when_any_address_is_private(monkeypatch):
    # A host resolving to one public *and* one private address is blocked — a single
    # non-public address is enough (closes a DNS-rebinding style bypass).
    import socket as _socket

    def fake_getaddrinfo(host, *args, **kwargs):
        return [
            (_socket.AF_INET, 0, 0, "", ("8.8.8.8", 0)),
            (_socket.AF_INET, 0, 0, "", ("127.0.0.1", 0)),
        ]

    monkeypatch.setattr("app.core.safe_http.socket.getaddrinfo", fake_getaddrinfo)
    assert host_is_blocked("rebind.example.com")


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
