"""Keyless Spotify import (Option A in docs/spotify-import.md).

Resolves a Spotify track/album/playlist URL by scraping its **public embed
page** — no API key, no credentials — into a tracklist of authoritative
metadata (title / artist / duration / cover). The audio itself is never touched:
:func:`find_youtube_match` searches YouTube for each track and ranks the results
with the spotDL-ported matcher (:mod:`app.services.matching`); the caller then
downloads that YouTube URL through the normal pipeline and tags it with the
Spotify metadata.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast
from urllib.error import URLError
from urllib.request import Request, urlopen

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.core.ytdlp_options import network_options
from app.models.spotify import SpotifyImportInfo, SpotifyKind, SpotifyTrack
from app.services.matching import best_match

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# open.spotify.com/<kind>/<id>, /intl-xx/<kind>/<id>, or a spotify:<kind>:<id> URI.
_SPOTIFY_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z-]+/)?|spotify:)"
    r"(track|album|playlist)[/:]([A-Za-z0-9]+)",
    re.IGNORECASE,
)
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)
_SEARCH_N = 5  # YouTube candidates to rank per track


class SpotifyError(RuntimeError):
    """Raised when a Spotify URL can't be parsed or its embed can't be read."""


def is_spotify_url(url: str) -> bool:
    return bool(_SPOTIFY_RE.search(url))


def _parse_url(url: str) -> tuple[SpotifyKind, str]:
    match = _SPOTIFY_RE.search(url)
    if not match:
        raise SpotifyError("Not a recognised Spotify track/album/playlist URL.")
    return cast(SpotifyKind, match.group(1).lower()), match.group(2)


def _fetch_entity(kind: SpotifyKind, spotify_id: str) -> dict[str, Any]:
    """Scrape the public embed page and return its `entity` JSON object."""
    embed = f"https://open.spotify.com/embed/{kind}/{spotify_id}"
    try:
        request = Request(embed, headers={"User-Agent": _USER_AGENT})  # noqa: S310
        with urlopen(request, timeout=15) as response:  # noqa: S310
            html = response.read().decode("utf-8", "replace")
    except (URLError, OSError) as exc:
        raise SpotifyError(f"Could not reach Spotify: {exc}") from exc

    blob = _NEXT_DATA_RE.search(html)
    if not blob:
        raise SpotifyError("Spotify embed page changed shape (no __NEXT_DATA__).")
    try:
        data = json.loads(blob.group(1))
        entity = data["props"]["pageProps"]["state"]["data"]["entity"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SpotifyError("Could not parse the Spotify embed metadata.") from exc
    if not isinstance(entity, dict):
        raise SpotifyError("Unexpected Spotify embed metadata.")
    return entity


def _cover_of(entity: dict[str, Any]) -> str | None:
    visual = entity.get("visualIdentity") or {}
    images = visual.get("image") or []
    if images:
        return images[-1].get("url")
    sources = (entity.get("coverArt") or {}).get("sources") or []
    return sources[-1].get("url") if sources else None


def _year_of(entity: dict[str, Any]) -> str | None:
    rd = entity.get("releaseDate")
    if isinstance(rd, dict):
        rd = rd.get("isoString") or rd.get("year")
    if isinstance(rd, (str, int)):
        text = str(rd)
        return text[:4] if len(text) >= 4 else None
    return None


def _uri_to_url(uri: str) -> str:
    # "spotify:track:ID" -> "https://open.spotify.com/track/ID"
    parts = uri.split(":")
    if len(parts) == 3 and parts[0] == "spotify":
        return f"https://open.spotify.com/{parts[1]}/{parts[2]}"
    return uri


def resolve_spotify(url: str) -> SpotifyImportInfo:
    """Resolve a Spotify URL into a tracklist via the public embed (keyless).

    Raises:
        SpotifyError: on a bad URL or an unreadable/changed embed page.
    """
    kind, spotify_id = _parse_url(url)
    entity = _fetch_entity(kind, spotify_id)
    cover = _cover_of(entity)

    if kind == "track":
        track = SpotifyTrack(
            title=entity.get("name") or entity.get("title") or "",
            artists=", ".join(
                a.get("name", "") for a in entity.get("artists", []) if a.get("name")
            ),
            duration_ms=entity.get("duration"),
            is_explicit=bool(entity.get("isExplicit")),
            year=_year_of(entity),
            cover_url=cover,
            spotify_url=f"https://open.spotify.com/track/{spotify_id}",
        )
        return SpotifyImportInfo(
            type="track", name=track.title, cover_url=cover, tracks=[track]
        )

    raw_tracks = entity.get("trackList") or []
    tracks: list[SpotifyTrack] = []
    for item in raw_tracks:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        tracks.append(
            SpotifyTrack(
                title=item.get("title", ""),
                artists=item.get("subtitle", "") or "",
                duration_ms=item.get("duration"),
                is_explicit=bool(item.get("isExplicit")),
                cover_url=cover,  # per-track art isn't in the embed; use the set's
                spotify_url=_uri_to_url(item.get("uri", "")),
            )
        )
    # The embed exposes only the first page of a large playlist.
    total = entity.get("trackCount") or entity.get("totalCount")
    truncated = bool(isinstance(total, int) and total > len(tracks))
    return SpotifyImportInfo(
        type=kind,
        name=entity.get("name") or entity.get("title") or "",
        cover_url=cover,
        tracks=tracks,
        truncated=truncated,
    )


def find_youtube_match(track: SpotifyTrack) -> str | None:
    """Search YouTube for a Spotify track and return the best-ranked video URL.

    Returns None when nothing clears the match thresholds (caller can fall back
    to a manual search or skip the track).
    """
    query = f"{track.artists} {track.title}".strip()
    if not query:
        return None
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        **network_options(),
    }
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"ytsearch{_SEARCH_N}:{query}", download=False)
    except DownloadError:
        return None
    entries = (info or {}).get("entries") or []
    candidates = [
        {
            "title": e.get("title"),
            "channel": e.get("channel") or e.get("uploader"),
            "duration": e.get("duration"),
            "id": e.get("id"),
            "url": e.get("url") or e.get("webpage_url"),
        }
        for e in entries
        if isinstance(e, dict)
    ]
    best = best_match(
        track_title=track.title,
        track_artists=track.artists,
        track_duration_ms=track.duration_ms,
        candidates=candidates,
    )
    if not best:
        return None
    if best.get("id"):
        return f"https://www.youtube.com/watch?v={best['id']}"
    return best.get("url")
