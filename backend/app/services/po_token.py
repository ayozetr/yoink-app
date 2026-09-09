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
import re
import threading
import time

from app.core.config import settings

logger = logging.getLogger(__name__)

# A minted per-video token is reused for this long before re-minting, so repeated
# extractor calls for the same video don't each trigger a WebView round-trip.
# Kept well under the token's real lifetime (hours) so a cached one stays valid.
_TOKEN_TTL_SECONDS = 6 * 3600

# How long to wait for the WebView to mint a token before giving up (a cold mint
# runs the BotGuard attestation, ~1–4 s; a warm one, with the integrity token
# cached in the WebView, is ~1 s). Generous, but bounded so a stuck WebView can't
# stall a download for long before the backoff below kicks in.
_MINT_TIMEOUT_SECONDS = 10.0

# After a mint failure (bgutils broke on a YouTube change, or a timeout), stop
# attempting to mint for this long and just fall back — so a broken minter doesn't
# add a failed round-trip to *every* download. Reset the moment a mint succeeds.
_MINT_BACKOFF_SECONDS = 5 * 60

# video_id -> (token, expiry on the monotonic clock). Guarded by ``_lock`` — the
# metadata and download services can both resolve tokens off different threads.
_cache: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()
# Monotonic time until which minting is skipped after a failure (0 = not backing off).
_backoff_until = 0.0


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
    """Drop every cached minted token + any backoff (settings change, and tests)."""
    global _backoff_until
    with _lock:
        _cache.clear()
        _backoff_until = 0.0


def _mint_via_webview(video_id: str) -> str | None:
    """Mint a fresh per-video PO token in the app's WebView, via the bridge.

    Submits a mint job the WebView's background loop fulfills (running bgutils-js
    with its network proxied through the backend) and blocks until it answers or
    times out. Skipped — returns ``None`` immediately — when no WebView has polled
    recently (the headless CLI, or before the minter started), so "auto" mode
    degrades to the manual token / cookies without a needless wait.
    """
    from app.services import po_token_bridge

    global _backoff_until
    if not po_token_bridge.broker.has_active_poller():
        logger.debug("auto-PO: no WebView minter polling; skipping mint for %s", video_id)
        return None
    with _lock:
        backing_off = time.monotonic() < _backoff_until
    if backing_off:
        logger.debug("auto-PO: in post-failure backoff; skipping mint for %s", video_id)
        return None
    logger.debug("auto-PO: requesting a mint from the WebView for %s", video_id)
    token = po_token_bridge.broker.submit_mint(video_id, timeout=_MINT_TIMEOUT_SECONDS)
    with _lock:
        if token:
            _backoff_until = 0.0  # working again — clear any backoff
        else:
            _backoff_until = time.monotonic() + _MINT_BACKOFF_SECONDS
    if token:
        logger.info("auto-PO: minted a per-video token for %s", video_id)
    else:
        logger.warning(
            "auto-PO: WebView mint failed/timed out for %s; backing off %ds",
            video_id,
            _MINT_BACKOFF_SECONDS,
        )
    return token


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


# A YouTube video id inside a watch/shorts/embed/youtu.be URL.
_YT_ID_RE = re.compile(r"(?:v=|/shorts/|/embed/|/live/|youtu\.be/)([\w-]{11})")


def youtube_video_id(url: str) -> str | None:
    """Extract the 11-char YouTube video id from a URL, or None if it isn't one."""
    match = _YT_ID_RE.search(url)
    return match.group(1) if match else None


def resolve_tokens_for_url(url: str) -> list[str]:
    """PO token(s) for a specific URL. For a YouTube video in auto mode this mints
    a fresh per-video token (via the WebView bridge); otherwise it's the same as
    :func:`resolve_tokens` (manual / off), and non-YouTube URLs never mint."""
    return resolve_tokens(youtube_video_id(url))


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
