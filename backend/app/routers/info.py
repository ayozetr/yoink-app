# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""`/api/info` route — metadata extraction for a media URL."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Query, status

from app.core.safe_http import host_is_blocked
from app.core.ytdlp_options import normalize_url
from app.models.media import InfoRequest, InfoResponse, SearchResponse
from app.services import history_store
from app.services.download_service import friendly_download_error
from app.services.ytdlp_service import (
    MediaExtractionError,
    extract_info,
    search_youtube,
)

router = APIRouter(tags=["info"])

# Query params that say *where/how* a video was seen (playlist position, radio,
# timestamp, tracking) — not *which* one. Dropped when matching a playlist entry
# against the download history so the same video matches across contexts (e.g. a
# standalone download vs the same video inside a list).
_CONTEXT_PARAMS = frozenset(
    {"list", "index", "start_radio", "pp", "feature", "t", "si", "ab_channel"}
)


def _match_key(url: str) -> str:
    """A context-free key for playlist-sync matching (normalize + drop the params
    above)."""
    parts = urlsplit(normalize_url(url))
    if not parts.query:
        return urlunsplit(parts)
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in _CONTEXT_PARAMS
    ]
    return urlunsplit(parts._replace(query=urlencode(kept)))


@router.post(
    "/info",
    response_model=InfoResponse,
    summary="Extract media metadata without downloading",
)
def get_media_info(request: InfoRequest) -> InfoResponse:
    """Inspect a URL with yt-dlp (download=False) and return clean metadata.

    Returns either a single video (preview card + formats) or a flat playlist
    listing, depending on the URL.
    """
    # Defense-in-depth SSRF guard: yt-dlp fetches the URL outside safe_http, and
    # the desktop deep-link check is the only other barrier, so reject a target
    # that resolves to a non-public address here too (covers the web/server builds).
    url = str(request.url)
    if host_is_blocked(urlsplit(url).hostname):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This URL points to a non-public address.",
        )
    try:
        info = extract_info(url)
    except MediaExtractionError as exc:
        # Transient (anti-bot 403 / network blip, already retried) → 503 so the
        # client can offer a clean "try again"; permanent (unsupported/private
        # URL) → 422 with the reason.
        if exc.transient:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The source is temporarily unavailable. Please try again.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=friendly_download_error(str(exc)),
        ) from exc

    # Playlist sync: flag items you've already downloaded (matched by normalized
    # URL) so the card can pre-select only what's new.
    if info.type == "playlist" and info.playlist and info.playlist.entries:
        downloaded = {_match_key(u) for u in history_store.completed_urls()}
        for entry in info.playlist.entries:
            entry.already_downloaded = _match_key(entry.url) in downloaded
    return info


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Flat search (YouTube or SoundCloud) for the URL-field typeahead",
)
def search_media(
    q: str = Query(..., min_length=1, max_length=200, description="Search query."),
    source: str = Query(
        "youtube",
        pattern="^(youtube|soundcloud)$",
        description="Which platform to search.",
    ),
) -> SearchResponse:
    """Search the chosen platform (flat) and return matching tracks, best-first."""
    try:
        return SearchResponse(results=search_youtube(q, source=source))
    except MediaExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Search failed: {exc}",
        ) from exc
