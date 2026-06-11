"""`/api/info` route — metadata extraction for a media URL."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.models.media import InfoRequest, InfoResponse, SearchResponse
from app.services.ytdlp_service import (
    MediaExtractionError,
    extract_info,
    search_youtube,
)

router = APIRouter(tags=["info"])


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
    try:
        return extract_info(str(request.url))
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
            detail=f"Could not extract media info: {exc}",
        ) from exc


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Flat YouTube search for the URL-field typeahead",
)
def search_media(
    q: str = Query(..., min_length=1, max_length=200, description="Search query."),
) -> SearchResponse:
    """Search YouTube (flat) and return matching videos, best-first."""
    try:
        return SearchResponse(results=search_youtube(q))
    except MediaExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Search failed: {exc}",
        ) from exc
