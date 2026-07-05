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
import shutil
import threading
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, download_range_func

from app.core.config import (
    AUTOTAG_FILENAME_TEMPLATE,
    AUTOTAG_FILENAME_TEMPLATE_REVERSED,
    settings,
)
from app.core.ffmpeg import ffmpeg_location
from app.core.humanize import humanize_bytes
from app.core.ytdlp_options import (
    network_options,
    normalize_url,
    with_cookie_fallback,
)
from app.services.embedded_vr_extractor import register as register_embedded_vr
from app.services.threads_extractor import register as register_threads_ie
from app.services import audio_normalize, nfo
from app.services.vr import apply_vr, detect_vr
from app.models.media import (
    AudioFormat,
    CompletedEvent,
    DownloadRequest,
    ErrorEvent,
    ProgressEvent,
)

logger = logging.getLogger(__name__)

# Refuse a download when less than this is free on the target disk (~500 MB).
_MIN_FREE_DISK_BYTES = 500 * 1024 * 1024

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


class _DownloadCancelled(BaseException):
    """Raised from the progress hook to abort an in-flight yt-dlp download.

    Subclasses ``BaseException`` (not ``Exception``) so the cookie fallback's
    ``except Exception`` retry can't swallow a cancel and re-download the file;
    the explicit ``except _DownloadCancelled`` below still catches it.
    """


# yt-dlp's range/HLS downloader shells out to ffmpeg, which can exit non-zero on a
# transient network blip (most often "ffmpeg exited with code 8"). Unlike an HTTP
# fetch, yt-dlp's own `retries` don't cover an ffmpeg subprocess exit, so retry the
# whole job a couple of times when that's the failure.
_TRANSIENT_FFMPEG_RE = re.compile(r"ffmpeg exited with code", re.IGNORECASE)


def _with_transient_retry(
    run: Callable[[], str | None],
    *,
    should_retry: Callable[[], bool],
    attempts: int = 3,
) -> str | None:
    """Run ``run()``; retry on a transient ffmpeg exit, up to ``attempts`` times.

    Retries only while ``should_retry()`` is true — the worker passes the same
    "no bytes on disk yet" guard the cookie fallback uses, so a mid-stream blip
    never silently re-downloads. A non-ffmpeg error (or a repeat on the retry)
    propagates immediately.
    """
    for attempt in range(1, attempts + 1):
        try:
            return run()
        except DownloadError as exc:
            if (
                attempt >= attempts
                or not _TRANSIENT_FFMPEG_RE.search(str(exc))
                or not should_retry()
            ):
                raise
            logger.warning(
                "Transient ffmpeg failure (%s); retrying (%d/%d).",
                exc,
                attempt,
                attempts - 1,
            )
    raise AssertionError("unreachable")  # pragma: no cover


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
    request: DownloadRequest,
    hook: Any,
    pp_hook: Any = None,
    *,
    net: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble yt-dlp options for the requested kind/quality.

    ``net`` overrides the network options (cookies/proxy/impersonation) — used by
    the cookie fallback to rebuild without the browser.
    """
    download_dir = settings.ensure_download_dir()
    # Filename template: the user-configured name part + the real extension.
    # Strip first (so a whitespace-only value falls back) and neutralise path
    # traversal / absolute paths so a template can't write outside download_dir.
    name_template = (settings.filename_template or "").strip() or "%(title)s"
    # The "auto-tag name" options download under %(title)s; the auto-tag apply step
    # renames the file to "Artist - Title" (or reversed) once the metadata is known.
    if name_template in (
        AUTOTAG_FILENAME_TEMPLATE,
        AUTOTAG_FILENAME_TEMPLATE_REVERSED,
    ):
        name_template = "%(title)s"
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
        **(network_options() if net is None else net),
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
        # Embed the source thumbnail as a *fallback* cover (formats that can hold
        # cover art; WAV can't). Auto-tagging later overrides it when it finds
        # real album art and preserves it when it doesn't, so the thumbnail only
        # ever shows when nothing better is available. Runs after extraction.
        if request.audio_format in ("mp3", "m4a", "flac"):
            options["writethumbnail"] = True
            # YouTube thumbnails are WebP; Windows/most players can't display
            # WebP as embedded cover art (only JPEG/PNG). Convert before embed.
            audio_pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})
            audio_pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
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
                options["format"] = (
                    f"bv*[height<={height}]+mergeall[vcodec=none]/"
                    f"bv*[height<={height}]/bv*"
                )
            else:
                options["format"] = "bv*+mergeall[vcodec=none]/bv*"
        elif height:
            # The `/bv*…/b*` tail keeps the download from failing format selection
            # when the source has no separate audio: some clips expose only a muxed
            # h264 whose `acodec` is "unknown" (neither `bestvideo` nor `best` match
            # those), or are genuinely video-only. The preview warns when no audio
            # was detected.
            options["format"] = (
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best/"
                f"bv*[height<={height}]/bv*/b*"
            )
        else:
            options["format"] = "bestvideo+bestaudio/best/bv*/b*"
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
            # Fetch subtitles and embed them. A null/"all" language requests
            # every available real track; we deliberately skip auto-captions
            # there, since "all" would pull an auto-generated copy of every
            # language and bloat the output. For a specific language, include
            # its auto-captions as a fallback when no real track exists.
            options["writesubtitles"] = True
            if request.subtitle_lang in (None, "all"):
                options["subtitleslangs"] = ["all"]
            else:
                options["writeautomaticsub"] = True
                options["subtitleslangs"] = [request.subtitle_lang]
            postprocessors.append({"key": "FFmpegEmbedSubtitle"})

        if request.embed_chapters or mark_chapters:
            # Write chapter markers + source metadata into the container — needed
            # both for the embed-chapters toggle and for SponsorBlock "mark".
            postprocessors.append(chapters_pp)

        if postprocessors:
            options["postprocessors"] = postprocessors

    # Trim / clip: download only the requested time range (audio and video).
    # Treat a non-positive or inverted trim_end as "no end" so a stray 0 (or a UI
    # reset to 0) can't request a zero-length range that yields an empty file.
    start = request.trim_start or 0.0
    end = (
        request.trim_end
        if (request.trim_end is not None and request.trim_end > start)
        else float("inf")
    )
    if start > 0 or end != float("inf"):
        options["download_ranges"] = download_range_func(None, [(start, end)])
        # force_keyframes_at_cuts re-encodes at the marks for a frame-accurate cut,
        # but that re-encode fails for the VP9 streams VR videos ship (ffmpeg exits
        # 234 muxing VP9 into mp4 at a forced keyframe). VR is tagged as mp4 with
        # injected spherical boxes, so fall back to a keyframe-accurate stream-copy
        # cut there instead of failing the whole download.
        options["force_keyframes_at_cuts"] = not (request.is_vr or request.auto_vr)

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


# A substring (matched against the lowercased raw yt-dlp error) → a clearer,
# user-facing message. Most-specific first; the first match wins.
_ERROR_HINTS: tuple[tuple[str, str], ...] = (
    (
        "confirm you're not a bot",
        "The site is blocking automated access. Try again later, or point Yoink "
        "at your browser in Settings → cookies.",
    ),
    ("http error 429", "The site is rate-limiting downloads — wait a bit and try again."),
    (
        "http error 403",
        "Access was forbidden (403), often an anti-bot block. Try again, or set "
        "your browser in Settings → cookies.",
    ),
    (
        "forbidden",
        "Access was forbidden (403), often an anti-bot block. Try again, or set "
        "your browser in Settings → cookies.",
    ),
    (
        "requested format is not available",
        "Couldn't get a downloadable format. Some videos are protected by the "
        "source and can't be downloaded — try another quality or video.",
    ),
    (
        "private video",
        "This is a private video — it needs an account with access (Settings → cookies).",
    ),
    (
        "members-only",
        "This video is members-only — it needs an account (Settings → cookies).",
    ),
    ("video unavailable", "This video is unavailable."),
    ("not available in your country", "This video is geo-blocked in your region."),
    ("unable to extract", "Couldn't read this page — the site may have changed or the link is wrong."),
    ("unsupported url", "This URL isn't supported."),
    ("no video formats found", "No downloadable formats were found for this URL."),
)


def friendly_download_error(raw: str) -> str:
    """Turn a raw yt-dlp error into a concise, user-facing message.

    Drops yt-dlp's ``ERROR:`` / ``[extractor]`` prefix and the "Please report
    this issue …" boilerplate, maps well-known failures to clearer guidance,
    and otherwise returns the cleaned first line (capped).
    """
    text = re.split(
        r"\bplease report this issue\b", raw.strip(), maxsplit=1, flags=re.IGNORECASE
    )[0].strip()
    low = text.lower()
    for marker, message in _ERROR_HINTS:
        if marker in low:
            return message
    text = re.sub(r"^ERROR:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)  # drop a "[youtube]" extractor tag
    # Drop a leading media id like "dQw4w9WgXcQ:". Require a digit in the token so
    # a legit word prefix ("Postprocessing:", "ffmpeg:") is left intact.
    text = re.sub(r"^(?=[\w-]*\d)[\w-]{6,}:\s*", "", text)
    lines = text.splitlines()
    first = lines[0].strip() if lines else text
    return first[:300] or raw.strip()


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
    # Don't start a download that can't fit: surface low disk space up front
    # instead of failing mid-write with a cryptic yt-dlp/ffmpeg error.
    try:
        free = shutil.disk_usage(settings.ensure_download_dir()).free
    except OSError:
        free = None
    # The fixed floor, or 1.2x the client's size estimate when that's bigger — a
    # multi-GB 4K/VR capture that clears the floor would otherwise fail mid-write.
    needed = max(_MIN_FREE_DISK_BYTES, int((request.estimated_size or 0) * 1.2))
    if free is not None and free < needed:
        yield ErrorEvent(
            message=f"Not enough free disk space — only {humanize_bytes(free)} left."
        )
        return

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
    last_percent = 0.0
    # Set once the download is past extraction/auth and bytes are flowing. The
    # browser-cookie store is read before that point, so a fired progress hook
    # means the cookies were fine — the cookie fallback must not then re-download.
    started = threading.Event()

    def hook(raw: dict[str, Any]) -> None:
        nonlocal last_percent
        if cancel_event is not None and cancel_event.is_set():
            # Raising from the hook aborts the yt-dlp download.
            raise _DownloadCancelled
        event = _map_progress(raw)
        if event is None:
            return
        started.set()
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

    def _run(net: dict[str, Any]) -> str | None:
        options = _build_options(request, hook, pp_hook, net=net)
        with YoutubeDL(options) as ydl:
            register_threads_ie(ydl)  # Threads support (no native yt-dlp extractor)
            register_embedded_vr(ydl)  # player-config sources (overrides stale ones)
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
                    detected, detected_layout = detect_vr(info, strict=True)
                    if detected:
                        layout = detected_layout
                if layout is not None:
                    file = Path(path)
                    if file.exists():
                        path = str(apply_vr(file, layout))
            # Loudness-normalize audio to -14 LUFS so every track plays at the
            # same volume. Re-encodes in place (best-effort); runs before auto-
            # tagging, which then writes tags onto the normalized file.
            if path and request.kind == "audio" and settings.normalize_audio:
                audio_file = Path(path)
                if audio_file.exists():
                    audio_normalize.normalize(
                        audio_file, request.audio_format, settings.audio_bitrate
                    )
            # Optional Kodi/Jellyfin .nfo sidecar, next to the final file. Audio
            # auto-tagging rewrites it later with the tagged metadata.
            if path and settings.nfo_sidecars:
                nfo.write(Path(path), nfo.from_info(info, request.kind))
            return path

    def blocking() -> str | None:
        # A locked/unreadable browser cookie store fails at the start (before any
        # bytes), so retry without the browser — cookies file or none. But only
        # at start-of-job: once bytes are on disk, a mid-stream/transient error
        # must not silently re-run the whole download (now without the cookies it
        # needs), so skip the retry once the first progress hook has fired. The
        # outer wrapper retries the same way on a transient ffmpeg exit.
        not_started = lambda: not started.is_set()  # noqa: E731
        return _with_transient_retry(
            lambda: with_cookie_fallback(_run, should_retry=not_started),
            should_retry=not_started,
        )

    # Hold the process-wide lock for the whole job so a second download can't run
    # concurrently. Acquired before the worker thread starts (yt-dlp writes
    # immediately) and released in the finally below.
    await _download_lock.acquire()
    lock_held = True
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
            yield ErrorEvent(message=friendly_download_error(str(exc)))
            return
        except Exception as exc:  # noqa: BLE001 — surface any failure to the client.
            logger.exception("Unexpected download error for %s", request.url)
            yield ErrorEvent(message=f"Unexpected download error: {exc}")
            return

        # The worker finished and the file is written — release the lock before
        # the remaining checks and the completed yield, so the consumer's
        # post-completion work (ffprobe + history write, while the generator is
        # suspended at the yield) doesn't hold up the next queued download.
        _download_lock.release()
        lock_held = False

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
        # Release the lock *before* reaping the worker: on a cancel mid-merge the
        # worker stays blocked until the running ffmpeg finishes (it can't be
        # interrupted), so don't make the next download wait on a job we no longer
        # care about — a cancelled job writes its own output file and can't collide.
        if lock_held:
            _download_lock.release()
            lock_held = False
        await asyncio.gather(worker, return_exceptions=True)
