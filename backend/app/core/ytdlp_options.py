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


def is_browser_cookie_error(message: str) -> bool:
    """Whether an error is yt-dlp failing to read the *browser's* cookie store.

    On Windows a running Chromium browser locks its cookie DB (and newer ones
    encrypt it), so extraction fails with "Could not copy ... cookie database" /
    a decrypt error — which shouldn't sink the whole request when a cookies file
    (or plain impersonation) would work.
    """
    low = message.lower()
    if "cookie" not in low:
        return False
    return any(
        s in low
        for s in (
            "could not copy",
            "could not find",
            "could not open",
            "unable to read",
            "permission denied",
            "decrypt",
        )
    )


def with_cookie_fallback(run: Callable[[dict[str, Any]], _T]) -> _T:
    """Run ``run(network_options())``; if it fails because the *browser* cookie
    store couldn't be read, retry once with the browser dropped (cookies file or
    none). Non-cookie errors propagate unchanged.
    """
    try:
        return run(network_options())
    except Exception as exc:  # noqa: BLE001 — re-raised unless it's a cookie error
        if settings.cookies_from_browser and is_browser_cookie_error(str(exc)):
            logger.warning(
                "Could not read %s cookies (%s); retrying without the browser.",
                settings.cookies_from_browser,
                type(exc).__name__,
            )
            return run(network_options(use_browser=False))
        raise
