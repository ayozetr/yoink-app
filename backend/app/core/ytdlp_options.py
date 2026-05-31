"""Shared yt-dlp helpers used by both the metadata and download services.

Keeps URL normalization and cookie configuration in one place so the two
services behave identically.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.config import settings

# TikTok photo/slideshow posts are served by the video extractor under /video/.
_TIKTOK_PHOTO = re.compile(r"(tiktok\.com/@[^/]+)/photo/", re.IGNORECASE)


def normalize_url(url: str) -> str:
    """Rewrite known URL quirks into a form yt-dlp's extractors accept."""
    return _TIKTOK_PHOTO.sub(r"\1/video/", url)


def cookie_options() -> dict[str, Any]:
    """yt-dlp cookie options derived from settings (empty if unconfigured).

    `cookies_from_browser` wins over `cookies_file` when both are set.
    """
    if settings.cookies_from_browser:
        # Tuple form: (browser, profile, keyring, container) — only browser here.
        return {"cookiesfrombrowser": (settings.cookies_from_browser,)}
    if settings.cookies_file:
        return {"cookiefile": str(settings.cookies_file)}
    return {}
