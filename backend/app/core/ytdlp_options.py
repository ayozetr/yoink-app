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
    if parts.query:
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        kept = [(k, v) for k, v in pairs if k not in _YT_NOISE_PARAMS]
        # Only rewrite when a noise param was actually present as a query *key*
        # (not merely a substring of some value), to avoid needless re-encoding.
        if len(kept) != len(pairs):
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


def _parse_cookiesfrombrowser(spec: str) -> tuple[str, str | None, str | None, str | None]:
    """Parse a ``--cookies-from-browser`` spec into yt-dlp's 4-tuple.

    Accepts yt-dlp's CLI syntax ``BROWSER[+KEYRING][:PROFILE][::CONTAINER]`` and
    returns ``(browser, profile, keyring, container)`` — browser lowercased,
    keyring uppercased, the rest ``None`` when absent. A bare browser name yields
    ``(browser, None, None, None)``. Passing the raw spec as a 1-tuple instead
    would make yt-dlp raise ``ValueError`` on anything but a plain browser name.
    """
    rest = spec.strip()
    # ``::`` (container) before ``:`` (profile) so the container's double colon
    # isn't mistaken for a profile separator.
    rest, _, container = rest.partition("::")
    rest, _, profile = rest.partition(":")
    rest, _, keyring = rest.partition("+")
    return (
        rest.strip().lower(),
        profile.strip() or None,
        keyring.strip().upper() or None,
        container.strip() or None,
    )


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
        # 4-tuple (browser, profile, keyring, container) parsed from the spec.
        options["cookiesfrombrowser"] = _parse_cookiesfrombrowser(
            settings.cookies_from_browser
        )
    elif settings.cookies_file:
        options["cookiefile"] = str(settings.cookies_file)
    if settings.proxy:
        options["proxy"] = settings.proxy
    # Optional YouTube PO token(s): passed straight through as the native
    # `youtube:po_token` extractor arg (no plugin needed). An anonymous
    # proof-of-origin that can satisfy the "confirm you're not a bot" wall
    # without cookies. Off (nothing added) unless the user configured one.
    if settings.po_token:
        tokens = [t.strip() for t in settings.po_token.split(",") if t.strip()]
        if tokens:
            options["extractor_args"] = {"youtube": {"po_token": tokens}}
    return options


def with_cookie_fallback(
    run: Callable[[dict[str, Any]], _T],
    *,
    should_retry: Callable[[], bool] | None = None,
) -> _T:
    """Run ``run(network_options())``; if a **browser** cookie store is configured
    and the attempt fails, retry once with the browser dropped (cookies file, or
    none — impersonation already passes most anti-bot checks).

    Reading a browser's cookie store is by far the most fragile part of a request
    and its failure modes vary wildly by OS/browser/version (locked DB, DPAPI /
    app-bound decryption, a missing profile, …), with error strings we can't
    enumerate. So when a browser is set we retry on *any* first-attempt failure
    rather than trying to pattern-match the error — a genuinely unrelated failure
    simply fails again and propagates. No browser set → nothing to fall back from.

    ``should_retry`` is an optional guard the caller can use to veto the retry
    after the fact: the download worker passes one that returns ``False`` once
    bytes are on disk, so a mid-stream failure doesn't re-run the whole download
    without the cookies it needs (the browser-read failure happens before any
    bytes, so this never blocks the case the fallback is meant for).
    """
    try:
        return run(network_options())
    except Exception as exc:  # noqa: BLE001 — retried (browser set) or re-raised
        if not settings.cookies_from_browser:
            raise
        if should_retry is not None and not should_retry():
            raise
        logger.warning(
            "Request failed with %s cookies (%s); retrying without the browser.",
            settings.cookies_from_browser,
            type(exc).__name__,
        )
        return run(network_options(use_browser=False))
