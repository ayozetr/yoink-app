"""Download engine: run yt-dlp and stream typed progress events.

yt-dlp is blocking and its `progress_hooks` fire on the worker thread, so this
module runs the download via ``asyncio.to_thread`` and bridges hook callbacks
back to the event loop through an ``asyncio.Queue``. The public entry point,
:func:`download_events`, is an async iterator the WebSocket router can simply
``async for`` over.
"""

from __future__ import annotations

import asyncio
import re
import threading
from pathlib import Path
from typing import Any, AsyncIterator

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.core.config import settings
from app.core.humanize import humanize_bytes
from app.core.ytdlp_options import cookie_options, normalize_url
from app.models.media import (
    CompletedEvent,
    DownloadRequest,
    ErrorEvent,
    ProgressEvent,
)

# Event objects pushed onto the bridge queue.
_Event = ProgressEvent | CompletedEvent | ErrorEvent


class _DownloadCancelled(Exception):
    """Raised from the progress hook to abort an in-flight yt-dlp download."""


def _format_speed(bytes_per_second: float | None) -> str | None:
    """Render a download speed as e.g. '3.2 MB/s'."""
    if bytes_per_second is None:
        return None
    return f"{humanize_bytes(bytes_per_second)}/s"


def _format_eta(seconds: float | None) -> str | None:
    """Render an ETA in seconds as 'MM:SS' or 'H:MM:SS'."""
    if seconds is None:
        return None
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _parse_height(quality: str | None) -> int | None:
    """Turn a quality label like '1080p' into a pixel height."""
    if not quality:
        return None
    match = re.search(r"(\d+)", quality)
    return int(match.group(1)) if match else None


def _map_progress(raw: dict[str, Any]) -> ProgressEvent | None:
    """Translate a raw yt-dlp progress dict into a typed ProgressEvent."""
    status = raw.get("status")

    if status == "downloading":
        downloaded = raw.get("downloaded_bytes")
        total = raw.get("total_bytes") or raw.get("total_bytes_estimate")
        percent = (
            round(downloaded / total * 100, 1)
            if isinstance(downloaded, (int, float))
            and isinstance(total, (int, float))
            and total
            else 0.0
        )
        return ProgressEvent(
            status="downloading",
            percent=percent,
            downloaded_bytes=int(downloaded) if isinstance(downloaded, (int, float)) else None,
            total_bytes=int(total) if isinstance(total, (int, float)) else None,
            speed=_format_speed(raw.get("speed")),
            eta=_format_eta(raw.get("eta")),
            filename=_basename(raw.get("filename")),
        )

    if status == "finished":
        # The stream is fully fetched; ffmpeg merge / mp3 extraction may follow.
        total = raw.get("total_bytes") or raw.get("downloaded_bytes")
        return ProgressEvent(
            status="processing",
            percent=100.0,
            downloaded_bytes=int(total) if isinstance(total, (int, float)) else None,
            total_bytes=int(total) if isinstance(total, (int, float)) else None,
            filename=_basename(raw.get("filename")),
        )

    return None


def _basename(path: str | None) -> str | None:
    return Path(path).name if path else None


def _build_options(
    request: DownloadRequest, hook: Any
) -> dict[str, Any]:
    """Assemble yt-dlp options for the requested kind/quality."""
    download_dir = settings.ensure_download_dir()
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,
        "outtmpl": str(download_dir / "%(title)s.%(ext)s"),
        "progress_hooks": [hook],
        **cookie_options(),
    }

    if request.kind == "audio":
        options["format"] = "bestaudio/best"
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        height = _parse_height(request.quality)
        if height:
            options["format"] = (
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )
        else:
            options["format"] = "bestvideo+bestaudio/best"
        # Merge separate video+audio streams into a single MP4 via ffmpeg.
        options["merge_output_format"] = "mp4"

    return options


def _final_path(info: dict[str, Any]) -> str | None:
    """Resolve the path of the file actually written (post merge/extraction)."""
    downloads = info.get("requested_downloads")
    if isinstance(downloads, list) and downloads:
        first = downloads[0]
        if isinstance(first, dict):
            path = first.get("filepath")
            if isinstance(path, str):
                return path
    return None


async def download_events(
    request: DownloadRequest,
    cancel_event: threading.Event | None = None,
) -> AsyncIterator[_Event]:
    """Run the download, yielding progress events and a terminal event.

    Yields one or more :class:`ProgressEvent` followed by exactly one
    :class:`CompletedEvent` (success) or :class:`ErrorEvent` (failure). If
    ``cancel_event`` is set mid-flight, the download aborts and the iterator
    ends silently (no terminal event).
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()

    def hook(raw: dict[str, Any]) -> None:
        if cancel_event is not None and cancel_event.is_set():
            # Raising from the hook aborts the yt-dlp download.
            raise _DownloadCancelled
        event = _map_progress(raw)
        if event is not None:
            # Hook runs on the worker thread; hand off to the loop thread.
            loop.call_soon_threadsafe(queue.put_nowait, event)

    def blocking() -> str | None:
        options = _build_options(request, hook)
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(normalize_url(str(request.url)), download=True)
            info = ydl.sanitize_info(info)
            return _final_path(info) or ydl.prepare_filename(info)

    worker = asyncio.create_task(asyncio.to_thread(blocking))

    # Drain progress events until the worker finishes, then flush the queue.
    while True:
        getter = asyncio.create_task(queue.get())
        done, _ = await asyncio.wait(
            {getter, worker}, return_when=asyncio.FIRST_COMPLETED
        )
        if getter in done:
            yield getter.result()
            continue
        getter.cancel()
        while not queue.empty():
            yield queue.get_nowait()
        break

    if cancel_event is not None and cancel_event.is_set():
        # Cancelled by the client: swallow the worker's error and stop.
        worker.cancel()
        return

    try:
        path_str = worker.result()
    except _DownloadCancelled:
        return
    except DownloadError as exc:
        if cancel_event is not None and cancel_event.is_set():
            return
        yield ErrorEvent(message=str(exc))
        return
    except Exception as exc:  # noqa: BLE001 — surface any failure to the client.
        yield ErrorEvent(message=f"Unexpected download error: {exc}")
        return

    if not path_str:
        yield ErrorEvent(message="Download finished but no output file was produced.")
        return

    path = Path(path_str)
    size = path.stat().st_size if path.exists() else None
    yield CompletedEvent(
        filename=path.name,
        filepath=str(path),
        total_bytes=size,
    )
