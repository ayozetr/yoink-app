"""Tests for PO token sourcing (off / manual / auto) + the session-token cache."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import po_token


@pytest.fixture(autouse=True)
def _clean_cache():
    """Each test starts with an empty session-token cache."""
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
    assert po_token.resolve_tokens() == []


def test_resolve_manual_returns_pasted(monkeypatch):
    monkeypatch.setattr(settings, "po_token_mode", "manual")
    monkeypatch.setattr(settings, "po_token", "web.gvs+AAA,web.gvs+BBB")
    assert po_token.resolve_tokens() == ["web.gvs+AAA", "web.gvs+BBB"]


def test_resolve_auto_returns_manual_fallback(monkeypatch):
    # resolve_tokens() never mints (it has no URL / visitor_data) — auto here just
    # yields the pasted token(s), same as manual. The session mint is separate.
    monkeypatch.setattr(settings, "po_token_mode", "auto")
    monkeypatch.setattr(settings, "po_token", "web.gvs+FALLBACK")
    assert po_token.resolve_tokens() == ["web.gvs+FALLBACK"]


def test_extractor_args_auto_uses_minted_session(monkeypatch):
    # A working minter → the GVS token is handed to every web-based client, the
    # manual one (if any) trails, the bound visitor_data rides alongside (yt-dlp
    # needs both), and mweb is added so a token-backed client is actually tried.
    monkeypatch.setattr(settings, "po_token_mode", "auto")
    monkeypatch.setattr(settings, "po_token", "web.gvs+FALLBACK")
    monkeypatch.setattr(po_token, "_mint_via_webview", lambda: ("MINTED", "VDATA"))
    args = po_token.youtube_extractor_args("https://youtu.be/dQw4w9WgXcQ")
    assert args["player_client"] == ["default", "mweb"]
    assert args["visitor_data"] == "VDATA"
    assert args["po_token"] == [
        "mweb.gvs+MINTED",
        "web.gvs+MINTED",
        "web_safari.gvs+MINTED",
        "web_embedded.gvs+MINTED",
        "web.gvs+FALLBACK",
    ]


def test_extractor_args_empty_for_non_youtube(monkeypatch):
    monkeypatch.setattr(settings, "po_token_mode", "auto")
    monkeypatch.setattr(po_token, "_mint_via_webview", lambda: ("X", "Y"))
    assert po_token.youtube_extractor_args("https://soundcloud.com/a/b") == {}


def test_extractor_args_empty_for_manual_and_off(monkeypatch):
    # Manual/off don't mint here — network_options already carries the manual token.
    monkeypatch.setattr(po_token, "_mint_via_webview", lambda: ("X", "Y"))
    for mode in ("manual", "off"):
        monkeypatch.setattr(settings, "po_token_mode", mode)
        assert po_token.youtube_extractor_args("https://youtu.be/dQw4w9WgXcQ") == {}


def test_extractor_args_empty_when_mint_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "po_token_mode", "auto")
    monkeypatch.setattr(settings, "po_token", None)
    monkeypatch.setattr(po_token, "_mint_via_webview", lambda: None)
    assert po_token.youtube_extractor_args("https://youtu.be/dQw4w9WgXcQ") == {}


def test_mint_session_caches(monkeypatch):
    calls: list[int] = []

    def fake_mint():
        calls.append(1)
        return ("TOK", "VD")

    monkeypatch.setattr(po_token, "_mint_via_webview", fake_mint)
    assert po_token.mint_session() == ("TOK", "VD")
    assert po_token.mint_session() == ("TOK", "VD")  # served from cache
    assert calls == [1]  # minted once


def test_mint_session_expired_is_reminted(monkeypatch):
    monkeypatch.setattr(po_token, "_mint_via_webview", lambda: ("TOK", "VD"))
    # A negative TTL makes any cached entry immediately stale.
    monkeypatch.setattr(po_token, "_TOKEN_TTL_SECONDS", -1)
    assert po_token.mint_session() == ("TOK", "VD")
    assert po_token._session_get() is None  # already expired → not served


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/abcdefghijk", "abcdefghijk"),
        ("https://www.youtube.com/embed/abcdefghijk", "abcdefghijk"),
        ("https://soundcloud.com/artist/track", None),
        ("https://vimeo.com/12345", None),
    ],
)
def test_youtube_video_id(url, expected):
    assert po_token.youtube_video_id(url) == expected


def test_mint_via_webview_skips_without_a_poller(monkeypatch):
    # No WebView has polled → don't submit a job / block; return None immediately.
    from app.services import po_token_bridge

    monkeypatch.setattr(po_token_bridge.broker, "has_active_poller", lambda: False)
    assert po_token._mint_via_webview() is None


def test_mint_via_webview_returns_pair(monkeypatch):
    from app.services import po_token_bridge

    monkeypatch.setattr(po_token_bridge.broker, "has_active_poller", lambda: True)
    monkeypatch.setattr(
        po_token_bridge.broker,
        "submit_mint",
        lambda timeout: {"token": "TOK", "visitor_data": "VD"},
    )
    assert po_token._mint_via_webview() == ("TOK", "VD")


def test_mint_via_webview_none_on_partial_result(monkeypatch):
    # A result missing either half is treated as a failure (yt-dlp needs both).
    from app.services import po_token_bridge

    monkeypatch.setattr(po_token_bridge.broker, "has_active_poller", lambda: True)
    monkeypatch.setattr(
        po_token_bridge.broker, "submit_mint", lambda timeout: {"token": "TOK"}
    )
    assert po_token._mint_via_webview() is None


def test_mint_failure_backs_off_then_recovers(monkeypatch):
    # A failed mint stops further attempts for a while, so a broken minter doesn't
    # add a failed round-trip to every download; a success clears the backoff.
    from app.services import po_token_bridge

    monkeypatch.setattr(po_token_bridge.broker, "has_active_poller", lambda: True)
    calls: list[int] = []

    def submit(timeout):
        calls.append(1)
        return None  # mint fails

    monkeypatch.setattr(po_token_bridge.broker, "submit_mint", submit)
    assert po_token._mint_via_webview() is None
    assert calls == [1]
    # Now in backoff: the next request is skipped without hitting the broker.
    assert po_token._mint_via_webview() is None
    assert calls == [1]  # not called again

    # Clearing the backoff (as a success would) lets minting resume.
    po_token.clear_cache()
    monkeypatch.setattr(
        po_token_bridge.broker,
        "submit_mint",
        lambda timeout: {"token": "TOK", "visitor_data": "VD"},
    )
    assert po_token._mint_via_webview() == ("TOK", "VD")
