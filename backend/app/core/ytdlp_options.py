"""Shared yt-dlp helpers used by both the metadata and download services.

Keeps URL normalization and cookie configuration in one place so the two
services behave identically.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from app.core.config import settings

# TikTok photo/slideshow posts are served by the video extractor under /video/.
_TIKTOK_PHOTO = re.compile(r"(tiktok\.com/@[^/]+)/photo/", re.IGNORECASE)


def normalize_url(url: str) -> str:
    """Rewrite known URL quirks into a form yt-dlp's extractors accept."""
    return _TIKTOK_PHOTO.sub(r"\1/video/", url)


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


def network_options() -> dict[str, Any]:
    """yt-dlp network options from settings: impersonation + cookies + proxy.

    Shared by the metadata and download services so both behave identically.
    `cookies_from_browser` wins over `cookies_file` when both are set.
    """
    options: dict[str, Any] = {}
    target = _impersonate_target()
    if target is not None:
        options["impersonate"] = target
    if settings.cookies_from_browser:
        # Tuple form: (browser, profile, keyring, container) — only browser here.
        options["cookiesfrombrowser"] = (settings.cookies_from_browser,)
    elif settings.cookies_file:
        options["cookiefile"] = str(settings.cookies_file)
    if settings.proxy:
        options["proxy"] = settings.proxy
    return options
