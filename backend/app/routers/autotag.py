"""`/api/autotag` — audio auto-tagging (AcoustID + MusicBrainz).

identify → (the user reviews/edits/picks in the UI) → apply. The endpoints are
plain `def` so FastAPI runs the blocking fingerprint/network work in a thread.
File paths are constrained to the download directory (SSRF/path guard).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.models.autotag import (
    ApplyRequest,
    ApplyResponse,
    IdentifyRequest,
    IdentifyResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.autotag_service import AutotagError, apply, identify, search

router = APIRouter(prefix="/autotag", tags=["autotag"])


def _validate_audio_path(path_str: str) -> Path:
    """Resolve a client-supplied path and confine it to the download dir."""
    try:
        resolved = Path(path_str).expanduser().resolve()
        download_dir = settings.download_dir.resolve()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path."
        ) from exc
    if resolved != download_dir and download_dir not in resolved.parents:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File is outside the download directory.",
        )
    if not resolved.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found."
        )
    return resolved


@router.post("/identify", response_model=IdentifyResponse, summary="Identify a song")
def identify_endpoint(request: IdentifyRequest) -> IdentifyResponse:
    path = _validate_audio_path(request.path)
    try:
        return identify(path)
    except AutotagError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/search", response_model=SearchResponse, summary="Manual MusicBrainz search")
def search_endpoint(request: SearchRequest) -> SearchResponse:
    try:
        return search(request.artist, request.title)
    except AutotagError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/apply", response_model=ApplyResponse, summary="Write tags + cover art")
def apply_endpoint(request: ApplyRequest) -> ApplyResponse:
    path = _validate_audio_path(request.path)
    try:
        return apply(request, path)
    except AutotagError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
