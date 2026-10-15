# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""`/api/history` + `/api/open` — download history, stats and folder reveal."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, status

from app.core.config import settings
from app.models.media import HistoryEntry, HistoryStats, OpenRequest
from app.services import history_store

router = APIRouter(tags=["history"])

# Files the /open endpoint will launch with the OS default app. Anything else
# (e.g. a .desktop / .bat that a prior download dropped in the dir) only gets the
# containing folder revealed, never executed.
_OPENABLE_SUFFIXES = {
    ".mp3", ".m4a", ".flac", ".wav", ".opus", ".ogg", ".aac",
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v",
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".srt", ".vtt", ".lrc", ".nfo",
}


@router.get("/history", response_model=list[HistoryEntry], summary="Recent downloads")
def list_history() -> list[HistoryEntry]:
    """Return recent download records, newest first."""
    try:
        return history_store.list_entries()
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="History is temporarily unavailable.",
        ) from exc


@router.get("/history/stats", response_model=HistoryStats, summary="Aggregate stats")
def history_stats() -> HistoryStats:
    """Return aggregate download statistics (count, total transferred)."""
    try:
        return history_store.get_stats()
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="History is temporarily unavailable.",
        ) from exc


@router.delete(
    "/history",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear the download history",
)
def clear_history() -> Response:
    """Delete all download history records."""
    try:
        history_store.clear()
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="History is temporarily unavailable.",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _open_folder(folder: Path) -> None:
    """Open a folder in the native file manager (Linux/macOS/Windows)."""
    if sys.platform.startswith("win"):
        import os

        os.startfile(str(folder))  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])  # noqa: S603, S607
    else:
        subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603, S607


@router.post("/open", summary="Reveal a file or folder in the OS file manager")
def open_in_file_manager(request: OpenRequest) -> dict[str, str]:
    """Open the download folder (or the folder containing a given file).

    The target is constrained to the configured download directory so the
    endpoint cannot be used to browse arbitrary locations on disk.
    """
    download_dir = settings.ensure_download_dir().resolve()
    target = Path(request.path).resolve() if request.path else download_dir

    if target != download_dir and download_dir not in target.parents:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path is outside the download directory.",
        )

    folder = target if target.is_dir() else target.parent
    if not folder.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found."
        )

    # Open the file itself (with its default app) only when asked AND it's a known
    # media/sidecar type; otherwise reveal the folder — never launch an arbitrary
    # (possibly executable) file sitting in the download dir.
    to_open = (
        target
        if (
            request.open_file
            and target.is_file()
            and target.suffix.lower() in _OPENABLE_SUFFIXES
        )
        else folder
    )
    try:
        _open_folder(to_open)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not open the file manager: {exc}",
        ) from exc

    return {"status": "ok", "opened": str(to_open)}
