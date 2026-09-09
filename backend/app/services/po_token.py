"""YouTube PO token sourcing (off / manual / auto).

A PO (proof-of-origin) token lets yt-dlp satisfy YouTube's "confirm you're not a
bot" wall without cookies. ``AppSettings.po_token_mode`` picks where tokens come
from:

  - ``"off"``    — never send one.
  - ``"manual"`` — send the token(s) the user pasted in Settings
                   (``settings.po_token``) — the classic opt-in path.
  - ``"auto"``   — mint a fresh token **per video** locally, in the app's hidden
                   WebView (bgutils-js), falling back to the manual token(s) when
                   minting is unavailable (the headless CLI has no WebView).

Web GVS/Player PO tokens are bound to the video id, so a single pasted token is
of limited use across videos — hence "auto". Auto-minting reuses the app's
**existing** WebView (webkit2gtk / WebView2) as the JS runtime, so nothing extra
is bundled; the round-trip is described in ``docs/po-token-webview.md``.

This module owns the mode logic and a small cache of minted per-video tokens.
The WebView round-trip itself lands in a later phase — :func:`_mint_via_webview`
is the seam, and returns ``None`` for now, so "auto" degrades gracefully to the
manual token / cookies rather than failing a download.
"""

from __future__ import annotations

import logging
import threading
import time

from app.core.config import settings

logger = logging.getLogger(__name__)

# A minted per-video token is reused for this long before re-minting, so repeated
# extractor calls for the same video don't each trigger a WebView round-trip.
# Kept well under the token's real lifetime (hours) so a cached one stays valid.
_TOKEN_TTL_SECONDS = 6 * 3600

# video_id -> (token, expiry on the monotonic clock). Guarded by ``_lock`` — the
# metadata and download services can both resolve tokens off different threads.
_cache: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def _parse_manual(raw: str | None) -> list[str]:
    """Split the pasted ``po_token`` setting into a clean token list."""
    if not raw:
        return []
    return [token.strip() for token in raw.split(",") if token.strip()]


def _cache_get(video_id: str) -> str | None:
    """A cached, still-fresh minted token for ``video_id``, or None."""
    with _lock:
        hit = _cache.get(video_id)
        if hit is None:
            return None
        token, expiry = hit
        if expiry > time.monotonic():
            return token
        del _cache[video_id]  # expired — drop it
        return None


def _cache_set(video_id: str, token: str) -> None:
    with _lock:
        _cache[video_id] = (token, time.monotonic() + _TOKEN_TTL_SECONDS)


def clear_cache() -> None:
    """Drop every cached minted token (on a settings change, and in tests)."""
    with _lock:
        _cache.clear()


def _mint_via_webview(video_id: str) -> str | None:
    """Mint a fresh per-video PO token in the app's hidden WebView.

    Not yet wired: the bridge (backend → a Tauri command → the hidden WebView
    running bgutils-js → the minted token) is a later phase — see
    ``docs/po-token-webview.md``. It returns ``None`` until then, so "auto" mode
    degrades to the manual token / cookies instead of failing a download. The
    headless CLI has no WebView and always returns ``None`` here.
    """
    return None


def mint(video_id: str) -> str | None:
    """A minted per-video token (cached), or None if minting is unavailable."""
    if not video_id:
        return None
    cached = _cache_get(video_id)
    if cached is not None:
        return cached
    token = _mint_via_webview(video_id)
    if token:
        _cache_set(video_id, token)
    return token


def resolve_tokens(video_id: str | None = None) -> list[str]:
    """The PO token(s) to hand yt-dlp for this request, per ``po_token_mode``.

    - ``"off"``: none.
    - ``"manual"``: the pasted token(s).
    - ``"auto"``: a freshly minted per-video token when the video id is known and
      the WebView can mint it; otherwise the pasted token(s) as a fallback (so a
      configured manual token still works on the CLI / before the bridge lands).

    ``network_options`` has no video id, so it only ever sources the manual /
    off tokens here; the per-video "auto" path is driven by the yt-dlp GetPOT
    provider (a later phase), which calls this with the request's video id.
    """
    mode = settings.po_token_mode
    if mode == "off":
        return []
    manual = _parse_manual(settings.po_token)
    if mode == "manual":
        return manual
    # auto
    if video_id:
        minted = mint(video_id)
        if minted:
            # yt-dlp's youtube:po_token wants CLIENT.CONTEXT+TOKEN entries; a
            # freshly minted token is bound to the web GVS context.
            return [f"web.gvs+{minted}", *manual]
    return manual  # can't mint (no id / no WebView) — fall back to the manual token(s)
