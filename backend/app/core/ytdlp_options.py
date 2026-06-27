"""Shared yt-dlp helpers used by both the metadata and download services.

Keeps URL normalization and cookie configuration in one place so the two
services behave identically.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any, Callable, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import settings

logger = logging.getLogger(__name__)
_T = TypeVar("_T")

# TikTok photo/slideshow posts are served by the video extractor under /video/.
_TIKTOK_PHOTO = re.compile(r"(tiktok\.com/@[^/]+)/photo/", re.IGNORECASE)

# YouTube autoplay/radio flags. With ``playnext=1`` a playlist resolves in
# "continue the radio from this video" mode, which drops the playlist's own
# thumbnails — so its cover wrongly falls back to the first track. They never
# identify the content, so strip them before extraction.
_YT_NOISE_PARAMS = frozenset({"playnext", "start_radio"})


def normalize_url(url: str) -> str:
    """Rewrite known URL quirks into a form yt-dlp's extractors accept."""
    url = _TIKTOK_PHOTO.sub(r"\1/video/", url)
    parts = urlsplit(url)
    if parts.query and any(p in parts.query for p in _YT_NOISE_PARAMS):
        kept = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k not in _YT_NOISE_PARAMS
        ]
        url = urlunsplit(parts._replace(query=urlencode(kept)))
    return url


@lru_cache(maxsize=1)
def _impersonate_target() -> Any | None:
    """A Chrome impersonation target if curl_cffi is available, else None.

    Browser impersonation (via curl_cffi) is what gets past Cloudflare/anti-bot
    TLS fingerprinting on many sites. It's transparent on sites that don't need
    it (verified: YouTube returns identical formats with or without it), so it's
    applied to every request. Degrades cleanly to None when the impersonate
    backend isn't installed, leaving plain requests untouched.
    """
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.networking.impersonate import ImpersonateTarget

        import curl_cffi  # noqa: F401 — ensure the impersonate backend exists.

        target = ImpersonateTarget("chrome")
        # Confirm a backend can actually satisfy the target. Importing curl_cffi
        # isn't enough — with incompatible wheels the target would be missing and
        # YoutubeDL(impersonate=...) would hard-raise on *every* request. If it's
        # unavailable, fall back to plain requests instead.
        with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            if not ydl._impersonate_target_available(target):
                return None
        return target
    except Exception:  # noqa: BLE001 — any import/availability issue → no impersonation.
        return None


def network_options(*, use_browser: bool = True) -> dict[str, Any]:
    """yt-dlp network options from settings: impersonation + cookies + proxy.

    Shared by the metadata and download services so both behave identically.
    `cookies_from_browser` wins over `cookies_file` when both are set. With
    ``use_browser=False`` the browser is skipped (used by the cookie fallback
    when reading the browser's cookie DB fails) — falling back to the cookies
    file if set, else no cookies.
    """
    options: dict[str, Any] = {}
    target = _impersonate_target()
    if target is not None:
        options["impersonate"] = target
    if use_browser and settings.cookies_from_browser:
        # Tuple form: (browser, profile, keyring, container) — only browser here.
        options["cookiesfrombrowser"] = (settings.cookies_from_browser,)
    elif settings.cookies_file:
        options["cookiefile"] = str(settings.cookies_file)
    if settings.proxy:
        options["proxy"] = settings.proxy
    return options


def with_cookie_fallback(run: Callable[[dict[str, Any]], _T]) -> _T:
    """Run ``run(network_options())``; if a **browser** cookie store is configured
    and the attempt fails, retry once with the browser dropped (cookies file, or
    none — impersonation already passes most anti-bot checks).

    Reading a browser's cookie store is by far the most fragile part of a request
    and its failure modes vary wildly by OS/browser/version (locked DB, DPAPI /
    app-bound decryption, a missing profile, …), with error strings we can't
    enumerate. So when a browser is set we retry on *any* first-attempt failure
    rather than trying to pattern-match the error — a genuinely unrelated failure
    simply fails again and propagates. No browser set → nothing to fall back from.
    """
    try:
        return run(network_options())
    except Exception as exc:  # noqa: BLE001 — retried (browser set) or re-raised
        if not settings.cookies_from_browser:
            raise
        logger.warning(
            "Request failed with %s cookies (%s); retrying without the browser.",
            settings.cookies_from_browser,
            type(exc).__name__,
        )
        return run(network_options(use_browser=False))
