"""Download engine: run yt-dlp and stream typed progress events.

yt-dlp is blocking and its `progress_hooks` fire on the worker thread, so this
module runs the download via ``asyncio.to_thread`` and bridges hook callbacks
back to the event loop through an ``asyncio.Queue``. The public entry point,
:func:`download_events`, is an async iterator the WebSocket router can simply
``async for`` over.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from pathlib import Path
from typing import Any, AsyncIterator

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, download_range_func

from app.core.config import settings
from app.core.ffmpeg import ffmpeg_location
from app.core.humanize import humanize_bytes
from app.core.ytdlp_options import network_options, normalize_url
from app.services.threads_extractor import register as register_threads_ie
from app.services.vr import apply_vr, detect_vr
from app.models.media import (
    AudioFormat,
    CompletedEvent,
    DownloadRequest,
    ErrorEvent,
    ProgressEvent,
)

logger = logging.getLogger(__name__)

# Serializes downloads across the whole backend process. Yoink downloads one
# file at a time (concurrent downloads are an explicit non-goal); two jobs share
# one download folder and can resolve to the same ".part" file, so running them
# at once would corrupt each other. The frontend already serializes within a
# single client, but a second browser tab / LAN client could otherwise bypass
# that — this lock is the server-side backstop. A blocking acquire means a
# second job simply waits for the first to finish (the queue's sequential
# hand-off waits only milliseconds), rather than failing.
_download_lock = asyncio.Lock()

# Event objects pushed onto the bridge queue.
_Event = ProgressEvent | CompletedEvent | ErrorEvent

# Audio extraction settings per output format. Lossless formats (flac/wav)
# intentionally omit `preferredquality` — a bitrate target is meaningless and
# yt-dlp/ffmpeg would reject or ignore it.
_AUDIO_POSTPROCESSORS: dict[AudioFormat, dict[str, str]] = {
    "mp3": {"preferredcodec": "mp3", "preferredquality": "192"},
    "m4a": {"preferredcodec": "m4a", "preferredquality": "192"},
    "flac": {"preferredcodec": "flac"},
    "wav": {"preferredcodec": "wav"},
}


# Map a video-codec preference to a yt-dlp format-sort key (best-effort bias).
_VCODEC_SORT = {"h264": "h264", "vp9": "vp9", "av1": "av01"}


def _audio_postprocessor(audio_format: AudioFormat) -> dict[str, str]:
    """Build the FFmpegExtractAudio postprocessor for an output audio format."""
    pp = {"key": "FFmpegExtractAudio", **_AUDIO_POSTPROCESSORS[audio_format]}
    # Apply the user's bitrate to lossy formats only ("best" = no target;
    # lossless formats carry no preferredquality to override).
    if "preferredquality" in pp:
        if settings.audio_bitrate == "best":
            pp.pop("preferredquality")
        else:
            pp["preferredquality"] = settings.audio_bitrate
    return pp


class _DownloadCancelled(Exception):
    """Raised from the progress hook to abort an in-flight yt-dlp download."""


def _format_speed(bytes_per_second: float | None) -> str | None:
    """Render a download speed as e.g. '3.2 MB/s'."""
    if bytes_per_second is None:
        return None
    return f"{humanize_bytes(bytes_per_second)}/s"


def _format_eta(seconds: float | None) -> str | None:
    """Render an ETA in seconds as 'MM:SS' or 'H:MM:SS'."""
    if seconds is None or seconds < 0:
        # yt-dlp occasionally emits eta=-1 ("unknown"); treat it as no ETA
        # instead of formatting nonsense like "-1:59".
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
            min(round(downloaded / total * 100, 1), 100.0)
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


# SponsorBlock segment categories to act on (the ones users typically skip).
_SPONSORBLOCK_CATEGORIES = [
    "sponsor",
    "intro",
    "outro",
    "selfpromo",
    "interaction",
    "preview",
    "music_offtopic",
]


def _sponsorblock_postprocessors(action: str) -> list[dict[str, Any]]:
    """yt-dlp postprocessors that mark or remove SponsorBlock segments.

    Mirrors `--sponsorblock-mark`/`--sponsorblock-remove`: the SponsorBlock PP
    fetches the crowd-sourced segments and ModifyChapters either turns them into
    chapter markers ("mark") or cuts them out of the file ("remove").
    """
    return [
        {
            "key": "SponsorBlock",
            "when": "after_filter",
            "categories": _SPONSORBLOCK_CATEGORIES,
            "api": "https://sponsor.ajay.app",
        },
        {
            "key": "ModifyChapters",
            "remove_sponsor_segments": (
                _SPONSORBLOCK_CATEGORIES if action == "remove" else []
            ),
            "remove_chapters_patterns": [],
            "remove_ranges": [],
            "sponsorblock_chapter_title": "[SponsorBlock]: %(category_names)l",
            "force_keyframes": False,
        },
    ]


def _parse_rate_limit(value: str | None) -> float | None:
    """Parse a speed cap like '1M' / '500K' / '2G' into bytes/s.

    Returns None for unset, unparseable, or non-positive / non-finite values, so a
    hand-edited settings.json can't feed yt-dlp a bogus ratelimit.
    """
    if not value:
        return None
    text = value.strip().upper()
    units = {"K": 1024, "M": 1024**2, "G": 1024**3}
    try:
        if text and text[-1] in units:
            result = float(text[:-1]) * units[text[-1]]
        else:
            result = float(text)
    except ValueError:
        return None
    if not (result > 0) or result == float("inf"):
        return None
    return result


def _build_options(
    request: DownloadRequest, hook: Any, pp_hook: Any = None
) -> dict[str, Any]:
    """Assemble yt-dlp options for the requested kind/quality."""
    download_dir = settings.ensure_download_dir()
    # Filename template: the user-configured name part + the real extension.
    # Strip first (so a whitespace-only value falls back) and neutralise path
    # traversal / absolute paths so a template can't write outside download_dir.
    name_template = (settings.filename_template or "").strip() or "%(title)s"
    name_template = name_template.replace("\\", "/").replace("..", "").strip("/")
    name_template = name_template or "%(title)s"
    # Defense in depth: confirm the resolved template path stays inside the
    # download dir (the %(...)s fields are treated as literal segments here).
    try:
        (download_dir / name_template).resolve().relative_to(download_dir.resolve())
    except ValueError:
        name_template = "%(title)s"
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,
        # Retry transient failures (yt-dlp's CLI defaults) — sites flake often.
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 3,
        # Fetch HLS/DASH fragments in parallel — a big speed-up for segmented
        # streams (common for VR and most platforms), with a modest cap.
        "concurrent_fragment_downloads": 4,
        # Resume an interrupted .part on retry instead of restarting from zero.
        "continuedl": True,
        "outtmpl": str(download_dir / f"{name_template}.%(ext)s"),
        "progress_hooks": [hook],
        # Cancel is also honoured between post-processing steps (ffmpeg, …).
        "postprocessor_hooks": [pp_hook] if pp_hook else [],
        **network_options(),
    }

    # Optional download speed cap (yt-dlp expects bytes/s).
    rate = _parse_rate_limit(settings.rate_limit)
    if rate:
        options["ratelimit"] = rate

    # Use the bundled ffmpeg/ffprobe when packaged; otherwise yt-dlp uses PATH.
    location = ffmpeg_location()
    if location:
        options["ffmpeg_location"] = location

    # SponsorBlock postprocessors (mark/remove) must run before audio extraction
    # or subtitle/chapter embedding, so they prefix whichever list we build.
    sponsorblock: list[dict[str, Any]] = (
        _sponsorblock_postprocessors(settings.sponsorblock_action)
        if settings.sponsorblock_enabled
        else []
    )
    # SponsorBlock "mark" only computes chapter markers; an FFmpegMetadata PP is
    # what actually writes them to the file (yt-dlp's CLI auto-enables this for
    # --sponsorblock-mark). Without it, mark mode would be a silent no-op.
    mark_chapters = (
        settings.sponsorblock_enabled and settings.sponsorblock_action == "mark"
    )
    chapters_pp = {"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True}

    if request.kind == "audio":
        # For m4a, prefer a source already in an AAC/m4a container so the
        # FFmpegExtractAudio postprocessor can copy the stream (`-c copy`)
        # instead of re-encoding it; other formats fall back to bestaudio.
        if request.audio_format == "m4a":
            options["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        else:
            options["format"] = "bestaudio/best"
        audio_pps = [*sponsorblock, _audio_postprocessor(request.audio_format)]
        if mark_chapters:
            audio_pps.append(chapters_pp)
        options["postprocessors"] = audio_pps
    else:
        height = _parse_height(request.quality)
        if request.audio_multistreams:
            # Keep every audio track (multi-language) in the merged file.
            # `allow_multiple_audio_streams` is yt-dlp's API equivalent of the
            # `--audio-multistreams` flag, and `mergeall[vcodec=none]` merges all
            # audio-only formats on top of the best video (`bv*`, which may
            # already carry one audio track of its own).
            options["allow_multiple_audio_streams"] = True
            if height:
                options["format"] = f"bv*[height<={height}]+mergeall[vcodec=none]"
            else:
                options["format"] = "bv*+mergeall[vcodec=none]"
        elif height:
            options["format"] = (
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )
        else:
            options["format"] = "bestvideo+bestaudio/best"
        # Merge separate video+audio streams into the requested container via
        # ffmpeg (mp4 by default; multi-audio is offered only for mkv, which can
        # hold multiple audio tracks).
        options["merge_output_format"] = request.container

        # Prefer a specific video codec when set (best-effort: yt-dlp falls back
        # to the next codec if a quality has no stream in the preferred one).
        if settings.video_codec != "any":
            options["format_sort"] = [f"vcodec:{_VCODEC_SORT[settings.video_codec]}"]

        # Subtitles and chapters are video-only concerns; collect any FFmpeg
        # postprocessors needed to embed them into the merged output.
        postprocessors: list[dict[str, Any]] = list(sponsorblock)

        if request.embed_subs:
            # Fetch subtitles (auto-captions as a fallback) and embed them.
            # A null/"all" language requests every available track.
            options["writesubtitles"] = True
            options["writeautomaticsub"] = True
            options["subtitleslangs"] = (
                ["all"]
                if request.subtitle_lang in (None, "all")
                else [request.subtitle_lang]
            )
            postprocessors.append({"key": "FFmpegEmbedSubtitle"})

        if request.embed_chapters or mark_chapters:
            # Write chapter markers + source metadata into the container — needed
            # both for the embed-chapters toggle and for SponsorBlock "mark".
            postprocessors.append(chapters_pp)

        if postprocessors:
            options["postprocessors"] = postprocessors

    # Trim / clip: download only the requested time range (audio and video).
    # Treat a non-positive or inverted trim_end as "no end" so a stray 0 (or a UI
    # reset to 0) can't request a zero-length range that yields an empty file;
    # force_keyframes_at_cuts re-encodes cleanly at the marks.
    start = request.trim_start or 0.0
    end = (
        request.trim_end
        if (request.trim_end is not None and request.trim_end > start)
        else float("inf")
    )
    if start > 0 or end != float("inf"):
        options["download_ranges"] = download_range_func(None, [(start, end)])
        options["force_keyframes_at_cuts"] = True

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
    last_percent = 0.0

    def hook(raw: dict[str, Any]) -> None:
        nonlocal last_percent
        if cancel_event is not None and cancel_event.is_set():
            # Raising from the hook aborts the yt-dlp download.
            raise _DownloadCancelled
        event = _map_progress(raw)
        if event is None:
            return
        # total_bytes can flip from estimate to real mid-download, making percent
        # jump backward; clamp it so the progress bar never goes down.
        if event.status == "downloading":
            if event.percent < last_percent:
                event = event.model_copy(update={"percent": last_percent})
            else:
                last_percent = event.percent
        elif event.status == "processing":
            # A "finished" hook marks the end of one stream. A merged
            # video+audio download fetches two streams back-to-back, so the
            # second stream restarts at ~0%; reset the clamp baseline or the
            # bar would stay frozen at the first stream's 100%.
            last_percent = 0.0
        # Hook runs on the worker thread; hand off to the loop thread.
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def pp_hook(raw: dict[str, Any]) -> None:
        # Post-processing (ffmpeg merge / FLAC extract / SponsorBlock / embed)
        # runs after the download phase, where `hook` no longer fires. Check the
        # cancel flag at each post-processor boundary so "Cancel" isn't dead
        # while ffmpeg works (it aborts before/after the running step).
        if cancel_event is not None and cancel_event.is_set():
            raise _DownloadCancelled

    def blocking() -> str | None:
        options = _build_options(request, hook, pp_hook)
        with YoutubeDL(options) as ydl:
            register_threads_ie(ydl)  # Threads support (no native yt-dlp extractor)
            info = ydl.extract_info(normalize_url(str(request.url)), download=True)
            info = ydl.sanitize_info(info)
            path = _final_path(info) or ydl.prepare_filename(info)
            # Immersive (VR) tagging: add the projection name suffix + inject
            # spherical metadata. Runs here on the worker thread (it rewrites the
            # file) and updates the path so the completed event/history point at
            # the renamed output. Video-only; best-effort. The main panel sets
            # is_vr + vr_layout explicitly; the queue sets auto_vr (it has no
            # preview), so detect from the downloaded info and tag only if found.
            if path and request.kind == "video":
                layout: str | None = None
                if request.is_vr:
                    layout = request.vr_layout
                elif request.auto_vr:
                    detected, detected_layout = detect_vr(info)
                    if detected:
                        layout = detected_layout
                if layout is not None:
                    file = Path(path)
                    if file.exists():
                        path = str(apply_vr(file, layout))
            return path

    # Hold the process-wide lock for the whole job so a second download can't run
    # concurrently. Acquired before the worker thread starts (yt-dlp writes
    # immediately) and released in the finally below.
    await _download_lock.acquire()
    worker = asyncio.create_task(asyncio.to_thread(blocking))

    # Drain progress events until the worker finishes, then flush the queue.
    getter: asyncio.Task[ProgressEvent] | None = None
    try:
        while True:
            getter = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {getter, worker}, return_when=asyncio.FIRST_COMPLETED
            )
            if getter in done:
                yield getter.result()
                continue
            getter.cancel()
            getter = None
            while not queue.empty():
                yield queue.get_nowait()
            break

        if cancel_event is not None and cancel_event.is_set():
            # Cancelled by the client: stop (the finally tears down the worker).
            return

        try:
            path_str = worker.result()
        except _DownloadCancelled:
            return
        except DownloadError as exc:
            if cancel_event is not None and cancel_event.is_set():
                return
            logger.error("Download failed for %s: %s", request.url, exc)
            yield ErrorEvent(message=str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — surface any failure to the client.
            logger.exception("Unexpected download error for %s", request.url)
            yield ErrorEvent(message=f"Unexpected download error: {exc}")
            return

        if not path_str:
            logger.error("Download for %s produced no output file", request.url)
            yield ErrorEvent(message="Download finished but no output file was produced.")
            return

        path = Path(path_str)
        if not path.exists():
            # yt-dlp reported a name but the file isn't on disk (postprocessor
            # rename mismatch, race, …). Don't emit a "completed" pointing at a
            # missing file — the history entry and "Open" action would dangle.
            logger.error("Download for %s vanished after finishing: %s", request.url, path)
            yield ErrorEvent(message="Download finished but the output file is missing.")
            return
        logger.info("Downloaded %s -> %s", request.url, path.name)
        yield CompletedEvent(
            filename=path.name,
            filepath=str(path),
            total_bytes=path.stat().st_size,
        )
    finally:
        # Tear down the bridge on every exit path — including when the consumer
        # closes the generator early (client disconnect -> GeneratorExit at a
        # yield). Set cancel_event so the yt-dlp worker stops at its next hook
        # fire, drop a pending getter, and await the worker so its
        # result/_DownloadCancelled is retrieved (no "Task exception was never
        # retrieved" log) and nothing leaks.
        if cancel_event is not None:
            cancel_event.set()
        if getter is not None and not getter.done():
            getter.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        _download_lock.release()
