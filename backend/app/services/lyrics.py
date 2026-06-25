"""Song lyrics from LRCLIB (https://lrclib.net) — free, keyless, SSRF-safe.

LRCLIB returns both plain text and synced (`.lrc`, timestamped) lyrics, and
flags instrumentals. We try the exact `/get` (artist+title+album+duration) and
fall back to `/search`. Everything goes through the IP-pinned safe-HTTP layer.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from dataclasses import dataclass
from typing import Any

from app.core.safe_http import SafeHTTPError, fetch_public

logger = logging.getLogger(__name__)

_BASE = "https://lrclib.net/api"
_HEADERS = {"User-Agent": "Yoink (https://github.com/ayozetr/yoink-app)"}


@dataclass
class Lyrics:
    """Plain + synced lyrics for a track (either may be None)."""

    plain: str | None
    synced: str | None  # ``.lrc`` body with [mm:ss.xx] timestamps
    instrumental: bool


def _get_json(url: str) -> Any | None:
    try:
        data, _ = fetch_public(url, headers=_HEADERS, timeout=10)
    except SafeHTTPError:
        return None
    try:
        return json.loads(data)
    except (ValueError, TypeError):
        return None


def _to_lyrics(record: dict[str, Any]) -> Lyrics | None:
    instrumental = bool(record.get("instrumental"))
    plain = (record.get("plainLyrics") or "").strip() or None
    synced = (record.get("syncedLyrics") or "").strip() or None
    if not instrumental and not plain and not synced:
        return None
    return Lyrics(plain=plain, synced=synced, instrumental=instrumental)


def fetch_lyrics(
    title: str,
    artist: str,
    album: str | None = None,
    duration: float | None = None,
) -> Lyrics | None:
    """Look up lyrics for a track. Returns None if nothing usable is found.

    With a duration, the exact `/get` endpoint is tried first (its signature
    match needs it); otherwise — and as a fallback — the first `/search` hit is
    used. Best-effort: any network/parse error yields None.
    """
    title = (title or "").strip()
    artist = (artist or "").strip()
    if not title:
        return None

    if duration:
        params: dict[str, str] = {"track_name": title, "artist_name": artist}
        if album:
            params["album_name"] = album
        params["duration"] = str(int(duration))
        got = _get_json(f"{_BASE}/get?{urllib.parse.urlencode(params)}")
        if isinstance(got, dict):
            found = _to_lyrics(got)
            if found is not None:
                return found

    query = urllib.parse.urlencode({"track_name": title, "artist_name": artist})
    hits = _get_json(f"{_BASE}/search?{query}")
    if isinstance(hits, list):
        for hit in hits:
            if isinstance(hit, dict):
                found = _to_lyrics(hit)
                if found is not None:
                    return found
    return None
