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


def network_options() -> dict[str, Any]:
    """yt-dlp network options from settings: cookies + an optional proxy.

    Shared by the metadata and download services so both behave identically.
    `cookies_from_browser` wins over `cookies_file` when both are set.
    """
    options: dict[str, Any] = {}
    if settings.cookies_from_browser:
        # Tuple form: (browser, profile, keyring, container) — only browser here.
        options["cookiesfrombrowser"] = (settings.cookies_from_browser,)
    elif settings.cookies_file:
        options["cookiefile"] = str(settings.cookies_file)
    if settings.proxy:
        options["proxy"] = settings.proxy
    return options
