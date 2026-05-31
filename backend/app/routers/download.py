"""`/api/ws/download` — start a download and stream live progress over WS.

Protocol: the client connects, sends one JSON message matching
:class:`DownloadRequest`, and then receives a stream of event objects
(``progress`` … then a terminal ``completed`` or ``error``).
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.models.media import DownloadRequest, ErrorEvent
from app.services.download_service import download_events

router = APIRouter(tags=["download"])


@router.websocket("/ws/download")
async def download_ws(websocket: WebSocket) -> None:
    """Drive a single download job for the lifetime of the connection."""
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

    try:
        async for event in download_events(request):
            await websocket.send_json(event.model_dump())
    except WebSocketDisconnect:
        # Client went away; the in-flight job is left to finish on disk.
        return

    try:
        await websocket.close()
    except RuntimeError:
        # Socket already closed by the client.
        pass
