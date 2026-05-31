"""`/api/history` + `/api/open` — download history, stats and folder reveal."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.models.media import HistoryEntry, HistoryStats, OpenRequest
from app.services import history_store

router = APIRouter(tags=["history"])


@router.get("/history", response_model=list[HistoryEntry], summary="Recent downloads")
def list_history() -> list[HistoryEntry]:
    """Return recent download records, newest first."""
    return history_store.list_entries()


@router.get("/history/stats", response_model=HistoryStats, summary="Aggregate stats")
def history_stats() -> HistoryStats:
    """Return aggregate download statistics (count, total transferred)."""
    return history_store.get_stats()


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

    try:
        _open_folder(folder)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not open the file manager: {exc}",
        ) from exc

    return {"status": "ok", "opened": str(folder)}
