"""YouTube PO token sourcing (off / manual / auto).

A PO (proof-of-origin) token lets yt-dlp satisfy YouTube's "confirm you're not a
bot" wall without cookies. ``AppSettings.po_token_mode`` picks where tokens come
from:

  - ``"off"``    — never send one.
  - ``"manual"`` — send the token(s) the user pasted in Settings
                   (``settings.po_token``) — the classic opt-in path.
  - ``"auto"``   — mint a fresh GVS token locally in the app's WebView (bgutils-js),
                   falling back to the manual token(s) when minting is unavailable
                   (the headless CLI has no WebView).

The web GVS PO token (for a logged-out download) is bound to the session's
``visitor_data``, not to the video — so one minted token is reused for every
video, and yt-dlp must be handed the *same* ``visitor_data`` alongside it. The
minter fetches ``visitor_data`` from youtube.com and mints against it; the pair is
cached here for the session. Auto-minting reuses the app's existing WebView as the
JS runtime, so nothing extra is bundled — see ``docs/po-token-webview.md``.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# The session token + visitor_data are reused for this long before re-minting.
# Kept under the integrity token's real lifetime (hours) so a cached one stays valid.
_TOKEN_TTL_SECONDS = 6 * 3600

# How long to wait for the WebView to mint before giving up (a cold mint runs the
# BotGuard attestation, ~1–4 s; a warm one is ~1 s). Bounded so a stuck WebView
# can't stall a download for long before the backoff below kicks in.
_MINT_TIMEOUT_SECONDS = 10.0

# After a mint failure (bgutils broke on a YouTube change, or a timeout), stop
# attempting for this long and just fall back — so a broken minter doesn't add a
# failed round-trip to every download. Reset the moment a mint succeeds.
_MINT_BACKOFF_SECONDS = 5 * 60

# The session's minted (token, visitor_data, expiry on the monotonic clock), or
# None. Guarded by ``_lock`` — download/metadata resolve off different threads.
_session: tuple[str, str, float] | None = None
_lock = threading.Lock()
# Monotonic time until which minting is skipped after a failure (0 = not backing off).
_backoff_until = 0.0


def _parse_manual(raw: str | None) -> list[str]:
    """Split the pasted ``po_token`` setting into a clean token list."""
    if not raw:
        return []
    return [token.strip() for token in raw.split(",") if token.strip()]


def _session_get() -> tuple[str, str] | None:
    """The cached, still-fresh (token, visitor_data) session pair, or None."""
    with _lock:
        if _session is not None and _session[2] > time.monotonic():
            return _session[0], _session[1]
    return None


def _session_set(token: str, visitor_data: str) -> None:
    global _session
    with _lock:
        _session = (token, visitor_data, time.monotonic() + _TOKEN_TTL_SECONDS)


def clear_cache() -> None:
    """Drop the cached session token + any backoff (settings change, and tests)."""
    global _session, _backoff_until
    with _lock:
        _session = None
        _backoff_until = 0.0


def _mint_via_webview() -> tuple[str, str] | None:
    """Mint a session GVS token + visitor_data in the app's WebView, via the bridge.

    Submits a mint job the WebView's background loop fulfills (fetching
    visitor_data + running bgutils-js, its network proxied through the backend) and
    blocks until it answers or times out. Skipped — returns ``None`` immediately —
    when no WebView has polled recently (the headless CLI) or during a post-failure
    backoff, so "auto" degrades to the manual token / cookies without a needless wait.
    """
    from app.services import po_token_bridge

    global _backoff_until
    if not po_token_bridge.broker.has_active_poller():
        logger.debug("auto-PO: no WebView minter polling; skipping mint")
        return None
    with _lock:
        backing_off = time.monotonic() < _backoff_until
    if backing_off:
        logger.debug("auto-PO: in post-failure backoff; skipping mint")
        return None
    result = po_token_bridge.broker.submit_mint(timeout=_MINT_TIMEOUT_SECONDS)
    token = (result or {}).get("token")
    visitor_data = (result or {}).get("visitor_data")
    ok = bool(token and visitor_data)
    with _lock:
        _backoff_until = 0.0 if ok else time.monotonic() + _MINT_BACKOFF_SECONDS
    if ok:
        logger.info("auto-PO: minted a session GVS token")
        return token, visitor_data  # type: ignore[return-value]
    logger.warning(
        "auto-PO: WebView mint failed/timed out; backing off %ds", _MINT_BACKOFF_SECONDS
    )
    return None


def mint_session() -> tuple[str, str] | None:
    """The session (token, visitor_data) pair — cached, minting once when needed."""
    cached = _session_get()
    if cached is not None:
        return cached
    minted = _mint_via_webview()
    if minted is not None:
        _session_set(*minted)
    return minted


# The web-based clients we hand the session GVS token to. yt-dlp applies a
# `<client>.gvs` token only when it actually uses that client, so listing several
# is harmless. `mweb` is the one that reliably yields the GVS-gated formats when
# logged out — the default `web` client degrades to images-only — which is why
# `youtube_extractor_args` also adds `mweb` to `player_client` (the logged-out
# defaults are visionos + web, and neither makes our token do anything on its own).
_WEB_CLIENTS = ("mweb", "web", "web_safari", "web_embedded")


# A YouTube video id inside a watch/shorts/embed/youtu.be URL.
_YT_ID_RE = re.compile(r"(?:v=|/shorts/|/embed/|/live/|youtu\.be/)([\w-]{11})")


def youtube_video_id(url: str) -> str | None:
    """Extract the 11-char YouTube video id from a URL, or None if it isn't one."""
    match = _YT_ID_RE.search(url)
    return match.group(1) if match else None


def resolve_tokens(video_id: str | None = None) -> list[str]:
    """The manual/off PO token(s) to hand yt-dlp. Used by ``network_options`` (which
    has no URL), so it never mints — ``off`` yields none, ``manual`` and ``auto``
    yield the pasted token(s). The per-download auto mint is
    :func:`youtube_extractor_args`, which also supplies the required visitor_data."""
    if settings.po_token_mode == "off":
        return []
    return _parse_manual(settings.po_token)


def youtube_extractor_args(url: str) -> dict[str, Any]:
    """Extra ``youtube`` extractor_args for a *download*: in auto mode, the minted
    session GVS token (bound to ``visitor_data``, which yt-dlp needs alongside it or
    it rejects the token), handed to the web-based clients, plus ``mweb`` added to
    the client list so a token-backed client is actually tried (the logged-out
    defaults are visionos + web, and `web` degrades to images-only). Empty for
    manual/off (``network_options`` already set the manual token) and non-YouTube URLs."""
    if settings.po_token_mode != "auto" or youtube_video_id(url) is None:
        return {}
    session = mint_session()
    if session is None:
        return {}
    token, visitor_data = session
    manual = _parse_manual(settings.po_token)
    return {
        "player_client": ["default", "mweb"],
        "po_token": [f"{client}.gvs+{token}" for client in _WEB_CLIENTS] + manual,
        "visitor_data": visitor_data,
    }
