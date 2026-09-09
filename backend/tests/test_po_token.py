"""Tests for PO token sourcing (off / manual / auto) + the minted-token cache."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import po_token


@pytest.fixture(autouse=True)
def _clean_cache():
    """Each test starts with an empty minted-token cache."""
    po_token.clear_cache()
    yield
    po_token.clear_cache()


def test_parse_manual_splits_and_trims():
    assert po_token._parse_manual(None) == []
    assert po_token._parse_manual("") == []
    assert po_token._parse_manual("  ") == []
    assert po_token._parse_manual("web.gvs+AAA, web.gvs+BBB ,, ") == [
        "web.gvs+AAA",
        "web.gvs+BBB",
    ]


def test_resolve_off_returns_nothing(monkeypatch):
    monkeypatch.setattr(settings, "po_token_mode", "off")
    monkeypatch.setattr(settings, "po_token", "web.gvs+AAA")
    assert po_token.resolve_tokens("vid123") == []


def test_resolve_manual_returns_pasted(monkeypatch):
    monkeypatch.setattr(settings, "po_token_mode", "manual")
    monkeypatch.setattr(settings, "po_token", "web.gvs+AAA,web.gvs+BBB")
    # The video id is irrelevant in manual mode.
    assert po_token.resolve_tokens("vid123") == ["web.gvs+AAA", "web.gvs+BBB"]
    assert po_token.resolve_tokens() == ["web.gvs+AAA", "web.gvs+BBB"]


def test_resolve_auto_falls_back_to_manual_when_minting_unavailable(monkeypatch):
    # The WebView bridge isn't wired (mint returns None), so auto degrades to the
    # pasted token instead of failing — the CLI relies on exactly this.
    monkeypatch.setattr(settings, "po_token_mode", "auto")
    monkeypatch.setattr(settings, "po_token", "web.gvs+FALLBACK")
    assert po_token.resolve_tokens("vid123") == ["web.gvs+FALLBACK"]
    # No video id → nothing to mint, still the manual fallback.
    assert po_token.resolve_tokens() == ["web.gvs+FALLBACK"]


def test_resolve_auto_uses_minted_token_prepended(monkeypatch):
    # Simulate a working WebView minter: the minted token leads, the manual one
    # (if any) trails as a fallback client/context.
    monkeypatch.setattr(settings, "po_token_mode", "auto")
    monkeypatch.setattr(settings, "po_token", "web.gvs+FALLBACK")
    monkeypatch.setattr(po_token, "_mint_via_webview", lambda vid: f"MINTED-{vid}")
    assert po_token.resolve_tokens("vid123") == [
        "web.gvs+MINTED-vid123",
        "web.gvs+FALLBACK",
    ]


def test_mint_caches_per_video(monkeypatch):
    calls: list[str] = []

    def fake_mint(video_id: str) -> str:
        calls.append(video_id)
        return f"MINTED-{video_id}"

    monkeypatch.setattr(po_token, "_mint_via_webview", fake_mint)
    assert po_token.mint("vid1") == "MINTED-vid1"
    assert po_token.mint("vid1") == "MINTED-vid1"  # served from cache
    assert po_token.mint("vid2") == "MINTED-vid2"
    # vid1 minted once (cached), vid2 minted once → two underlying calls total.
    assert calls == ["vid1", "vid2"]


def test_mint_expired_entry_is_reminted(monkeypatch):
    monkeypatch.setattr(po_token, "_mint_via_webview", lambda vid: f"T-{vid}")
    # A negative TTL makes any cached entry immediately stale.
    monkeypatch.setattr(po_token, "_TOKEN_TTL_SECONDS", -1)
    assert po_token.mint("vid1") == "T-vid1"
    assert po_token._cache_get("vid1") is None  # already expired → not served


def test_mint_returns_none_without_video_id(monkeypatch):
    monkeypatch.setattr(po_token, "_mint_via_webview", lambda vid: "SHOULD-NOT-RUN")
    assert po_token.mint("") is None


def test_mint_via_webview_stub_returns_none():
    # Until the bridge lands, the seam yields nothing (headless / unwired).
    assert po_token._mint_via_webview("vid123") is None
