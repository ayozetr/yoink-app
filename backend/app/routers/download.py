"""`/api/ws/download` — start a download and stream live progress over WS.

Protocol: the client connects, sends one JSON message matching
:class:`DownloadRequest`, and then receives a stream of event objects
(``progress`` … then a terminal ``completed`` or ``error``). Closing the socket
mid-flight cancels the download. Completed/failed downloads are persisted to
the history store.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import threading
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.config import settings
from app.core.ffmpeg import ffprobe_path
from app.models.media import DownloadRequest, ErrorEvent
from app.services import history_store
from app.services.download_service import download_events

router = APIRouter(tags=["download"])


async def _watch_for_cancel(websocket: WebSocket, cancel_event: threading.Event) -> None:
    """Set the cancel flag as soon as the client closes the socket."""
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
    except (WebSocketDisconnect, RuntimeError):
        pass
    cancel_event.set()


def _title_from_url(url: str) -> str:
    """Best-effort human title for a failed download with no file yet."""
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return tail or url


def _audio_bitrate_kbps(filepath: str | None) -> int | None:
    """Real audio bitrate (kbps) of a file via ffprobe, or None if unknown."""
    if not filepath:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe_path(),
                "-v", "quiet",
                "-select_streams", "a:0",
                "-show_entries", "stream=bit_rate:format=bit_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filepath,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines():
        value = line.strip()
        if value.isdigit() and int(value) > 0:
            return round(int(value) / 1000)
    return None


def _quality_label(request: DownloadRequest, filepath: str | None) -> str | None:
    """A short quality badge for the history: resolution for video, and the
    audio bitrate for audio (the format already shows as its own badge, so we
    never repeat it). Lossy with a fixed target uses that; otherwise (lossless
    or "best") the real bitrate is probed from the file."""
    if request.kind == "audio":
        if (
            request.audio_format not in ("flac", "wav")
            and settings.audio_bitrate != "best"
        ):
            return f"{settings.audio_bitrate} kbps"
        kbps = _audio_bitrate_kbps(filepath)
        return f"{kbps} kbps" if kbps else None
    quality = request.quality
    return quality if quality and quality != "best" else None


@router.websocket("/ws/download")
async def download_ws(websocket: WebSocket) -> None:
    """Drive a single download job for the lifetime of the connection."""
    # Browsers always send Origin on a WS handshake and CORS isn't enforced on
    # WebSockets, so reject a cross-origin page trying to force downloads. A
    # missing Origin (non-browser client) is allowed — it isn't the web vector.
    origin = websocket.headers.get("origin")
    if origin is not None and not re.match(settings.cors_origin_regex, origin):
        await websocket.close(code=1008)  # policy violation
        return
    await websocket.accept()

    try:
        payload = await websocket.receive_json()
    except WebSocketDisconnect:
        return

    try:
        request = DownloadRequest.model_validate(payload)
    except ValidationError as exc:
        await websocket.send_json(
            ErrorEvent(message=f"Invalid download request: {exc}").model_dump()
        )
        await websocket.close()
        return

    cancel_event = threading.Event()
    watcher = asyncio.create_task(_watch_for_cancel(websocket, cancel_event))
    url = str(request.url)

    try:
        async for event in download_events(request, cancel_event):
            await websocket.send_json(event.model_dump())

            if event.type == "completed":
                # ffprobe (for audio bitrate) runs off the event loop.
                quality = await asyncio.to_thread(
                    _quality_label, request, event.filepath
                )
                await asyncio.to_thread(
                    history_store.add_entry,
                    title=Path(event.filename).stem,
                    url=url,
                    kind=request.kind,
                    status="completed",
                    filename=event.filename,
                    filepath=event.filepath,
                    filesize=event.total_bytes,
                    quality=quality,
                )
            elif event.type == "error":
                await asyncio.to_thread(
                    history_store.add_entry,
                    title=_title_from_url(url),
                    url=url,
                    kind=request.kind,
                    status="error",
                    error_message=event.message,
                )
    except WebSocketDisconnect:
        cancel_event.set()
        return
    finally:
        watcher.cancel()

    try:
        await websocket.close()
    except RuntimeError:
        pass
