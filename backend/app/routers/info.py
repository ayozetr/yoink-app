"""`/api/info` route — metadata extraction for a media URL."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models.media import InfoRequest, InfoResponse
from app.services.ytdlp_service import MediaExtractionError, extract_info

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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not extract media info: {exc}",
        ) from exc
