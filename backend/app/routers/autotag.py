"""`/api/autotag` — audio auto-tagging via the Apple Music (iTunes) catalogue.

identify/search → (the user picks a version + edits in the UI) → apply. The
endpoints are plain `def` so FastAPI runs the blocking network/file work in a
thread. File paths are confined to the download directory (path guard).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.config import (
    AUTOTAG_FILENAME_TEMPLATE,
    AUTOTAG_FILENAME_TEMPLATE_REVERSED,
    settings,
)
from app.models.autotag import (
    ApplyRequest,
    ApplyResponse,
    CandidateList,
    IdentifyRequest,
    LyricsRequest,
    LyricsResult,
    SearchRequest,
)
from app.services import history_store
from app.services.autotag_service import (
    AutotagError,
    apply,
    identify,
    lyrics_preview,
    rename_to_tagged,
    search,
)

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


@router.post("/lyrics", response_model=LyricsResult, summary="Preview lyrics")
def lyrics_endpoint(request: LyricsRequest) -> LyricsResult:
    # Best-effort lookup; an empty result is a normal (not error) response.
    if request.path:
        _validate_audio_path(request.path)  # confine the duration-probe path
    return lyrics_preview(request)


@router.post("/apply", response_model=ApplyResponse, summary="Write tags + cover art")
def apply_endpoint(request: ApplyRequest) -> ApplyResponse:
    path = _validate_audio_path(request.path)
    try:
        response = apply(request, path)
    except AutotagError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    # Reflect the chosen "Artist - Title" in the download history list.
    title = (request.title or "").strip()
    artist = (request.artist or "").strip()
    new_title = f"{artist} - {title}" if artist and title else title
    # "Auto-tag name" templates rename the file to the tagged name in the chosen
    # order (Artist - Title, or the reversed Title - Artist).
    renamed: str | None = None
    if artist and title:
        if settings.filename_template == AUTOTAG_FILENAME_TEMPLATE:
            renamed = f"{artist} - {title}"
        elif settings.filename_template == AUTOTAG_FILENAME_TEMPLATE_REVERSED:
            renamed = f"{title} - {artist}"
    if new_title:
        try:
            if renamed:
                new_path = rename_to_tagged(path, renamed)
                history_store.update_after_tag(
                    str(path), str(new_path), new_path.name, renamed
                )
            else:
                history_store.update_title(str(path), new_title)
        except sqlite3.Error:
            pass  # best-effort: the tags were written even if history can't update
    return response
