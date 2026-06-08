"""`/api/settings` — read and update user-editable settings."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from app.models.media import AppSettings, VersionInfo
from app.services import settings_store, updates

router = APIRouter(tags=["settings"])

# Browsers yt-dlp can read cookies from (its --cookies-from-browser allowlist).
_COOKIE_BROWSERS = frozenset(
    {"brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale"}
)
# Proxy URL schemes yt-dlp understands.
_PROXY_SCHEMES = frozenset({"http", "https", "socks4", "socks4a", "socks5", "socks5h"})


@router.get("/version", response_model=VersionInfo, summary="Version + update check")
def get_version() -> VersionInfo:
    """Return the current version and whether a newer GitHub release exists."""
    return updates.check_for_updates()


@router.get(
    "/ytdlp-version",
    response_model=VersionInfo,
    summary="Bundled yt-dlp version + update check",
)
def get_ytdlp_version() -> VersionInfo:
    """Return the bundled yt-dlp version and whether a newer one is published.

    Informational only: yt-dlp ships inside the sidecar, so an update arrives
    with the next Yoink release (no in-app yt-dlp update).
    """
    return updates.check_ytdlp_update()


@router.get("/settings", response_model=AppSettings, summary="Current settings")
def get_settings() -> AppSettings:
    """Return the effective settings (env defaults + persisted overrides)."""
    return settings_store.get_current()


@router.put("/settings", response_model=AppSettings, summary="Update settings")
def put_settings(payload: AppSettings) -> AppSettings:
    """Apply and persist new settings; returns the effective snapshot."""
    # Defense in depth (CORS already blocks remote callers): reject values a
    # hand-crafted PUT could persist to break every later download, or that
    # yt-dlp would choke on.
    if payload.cookies_file and not Path(payload.cookies_file).is_file():
        raise HTTPException(
            status_code=400, detail="cookies_file is not an existing file."
        )
    if payload.cookies_from_browser and (
        payload.cookies_from_browser.split(":", 1)[0].lower() not in _COOKIE_BROWSERS
    ):
        raise HTTPException(
            status_code=400, detail="cookies_from_browser is not a supported browser."
        )
    if payload.proxy and urlparse(payload.proxy).scheme.lower() not in _PROXY_SCHEMES:
        raise HTTPException(
            status_code=400, detail="proxy must be an http(s) or socks URL."
        )
    return settings_store.update(payload)
