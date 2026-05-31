"""`/api/info` route — metadata extraction for a media URL."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models.media import InfoRequest, VideoInfo
from app.services.ytdlp_service import MediaExtractionError, extract_info

router = APIRouter(tags=["info"])


@router.post(
    "/info",
    response_model=VideoInfo,
    summary="Extract media metadata without downloading",
)
def get_media_info(request: InfoRequest) -> VideoInfo:
    """Inspect a URL with yt-dlp (download=False) and return clean metadata.

    The frontend calls this when the user pastes a URL, to populate the
    preview card (title, thumbnail, duration) and the available formats.
    """
    try:
        return extract_info(str(request.url))
    except MediaExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not extract media info: {exc}",
        ) from exc
