"""`/api/autotag` — audio auto-tagging via the Apple Music (iTunes) catalogue.

identify/search → (the user picks a version + edits in the UI) → apply. The
endpoints are plain `def` so FastAPI runs the blocking network/file work in a
thread. File paths are confined to the download directory (path guard).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.models.autotag import (
    ApplyRequest,
    ApplyResponse,
    CandidateList,
    IdentifyRequest,
    SearchRequest,
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


@router.post("/identify", response_model=CandidateList, summary="Match a file")
def identify_endpoint(request: IdentifyRequest) -> CandidateList:
    path = _validate_audio_path(request.path)
    try:
        return identify(path)
    except AutotagError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/search", response_model=CandidateList, summary="Manual catalogue search")
def search_endpoint(request: SearchRequest) -> CandidateList:
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
