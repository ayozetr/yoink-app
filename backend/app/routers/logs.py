# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""`/api/logs` route — tail the app's rotating log for the in-app Registro view."""

from __future__ import annotations

from collections import deque

from fastapi import APIRouter, Query

from app.core.config import settings
from app.models.media import LogsResponse

router = APIRouter(tags=["logs"])

_MAX_LINES = 5000


@router.get(
    "/logs",
    response_model=LogsResponse,
    summary="Recent application log lines (tail of ~/.yoink/logs/yoink.log)",
)
def get_logs(
    lines: int = Query(
        2000, ge=1, le=_MAX_LINES, description="How many trailing lines to return."
    ),
) -> LogsResponse:
    """Return the last ``lines`` lines of the rotating app log.

    The log lives at ``<data dir>/logs/yoink.log`` (see ``core/logging_config``).
    Reading is a bounded tail (a ``deque`` with ``maxlen``), so a large log never
    loads fully into memory.
    """
    log_path = settings.ensure_data_dir() / "logs" / "yoink.log"
    # Read one extra line so "truncated" is exact (more lines existed than we kept)
    # instead of a >= heuristic that lies when the file has exactly `lines` lines.
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            tail = deque(fh, maxlen=lines + 1)
    except OSError:
        # Missing log, or a read landing in the rotating handler's rollover window
        # (rename + recreate) — surface an empty view instead of a 500.
        return LogsResponse(path=str(log_path))
    truncated = len(tail) > lines
    if truncated:
        tail.popleft()
    return LogsResponse(
        path=str(log_path),
        content="".join(tail),
        lines=len(tail),
        truncated=truncated,
    )
