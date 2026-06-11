"""Thin, strictly-typed wrapper around yt-dlp for metadata extraction.

This module only performs *information extraction* (`download=False`). The
actual download + progress-streaming logic will live alongside it later.
"""

from __future__ import annotations

import time
from typing import Any, cast

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.core.ytdlp_options import network_options, normalize_url
from app.services.threads_extractor import register as register_threads_ie
from app.services.vr import detect_vr
from app.models.media import (
    InfoResponse,
    MediaFormat,
    PlaylistEntry,
    PlaylistInfo,
    VideoInfo,
)

# Cap the number of playlist entries returned so huge playlists stay snappy.
_ENTRY_CAP = 200

# Audio codec name prefixes that denote lossless audio. Matched case-insensitively
# by startswith against a format's normalized `acodec`. Everything else (aac, mp3,
# opus, vorbis, ac3, eac3, …) is treated as lossy.
_LOSSLESS_ACODEC_PREFIXES: tuple[str, ...] = (
    "flac",
    "alac",
    "wav",
    "pcm",
    "tta",
    "wavpack",
    "ape",
)


def _is_lossless_acodec(acodec: Any) -> bool:
    """Return True if an audio codec name denotes a lossless codec.

    Matching is case-insensitive and uses startswith so codec variants like
    ``pcm_s16le`` or ``flac`` are recognized. Missing/"none" codecs are lossy.
    """
    if not isinstance(acodec, str):
        return False
    normalized = acodec.strip().lower()
    if not normalized or normalized == "none":
        return False
    return normalized.startswith(_LOSSLESS_ACODEC_PREFIXES)


def _audio_summary(raw_formats: Any) -> tuple[bool, float | None]:
    """Compute (source_lossless, best_audio_abr) across all audio-bearing formats.

    A format "has audio" when its `acodec` is present and not "none". The result
    flags whether any such format is lossless and reports the maximum `abr`
    (kbps) seen, or None if no audio bitrate is known. Defensive against missing
    or malformed entries.
    """
    if not isinstance(raw_formats, list):
        return False, None

    lossless = False
    best_abr: float | None = None
    for fmt in raw_formats:
        if not isinstance(fmt, dict):
            continue
        acodec = fmt.get("acodec")
        if not isinstance(acodec, str) or not acodec or acodec == "none":
            continue
        if _is_lossless_acodec(acodec):
            lossless = True
        abr = fmt.get("abr")
        if isinstance(abr, (int, float)):
            abr_value = float(abr)
            if best_abr is None or abr_value > best_abr:
                best_abr = abr_value
    return lossless, best_abr


class MediaExtractionError(RuntimeError):
    """Raised when yt-dlp cannot extract metadata for a URL.

    ``transient`` marks a likely-temporary failure (a network blip, an HTTP
    5xx/429, or an anti-bot 403) that's worth retrying — as opposed to a
    permanent one (an unsupported, private, or deleted URL) the caller should
    surface as a hard error.
    """

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


# Substrings in a yt-dlp error message that signal a *temporary* failure worth
# retrying, rather than a permanent one (unsupported/private/deleted URL).
# Deliberately *specific* HTTP codes + network signals — the generic "unable to
# download webpage" wrapper is avoided because it also fronts permanent 404s.
_TRANSIENT_MARKERS = (
    "http error 500",
    "http error 502",
    "http error 503",
    "http error 504",
    "http error 429",  # rate limited
    "http error 403",  # frequently a transient anti-bot challenge
    "timed out",
    "timeout",
    "connection reset",
    "connection refused",
    "connection aborted",
    "remote end closed",
    "temporary failure",  # e.g. "Temporary failure in name resolution"
    "sign in to confirm you're not a bot",
    "failed to extract any player response",
    "getaddrinfo failed",
)


def _is_transient_error(message: str) -> bool:
    """Heuristically classify a yt-dlp error message as temporary vs permanent."""
    low = message.lower()
    return any(marker in low for marker in _TRANSIENT_MARKERS)


# A transient failure is retried up to this many total attempts, with a short
# linear backoff between them (kept small — /api/info is interactive).
_INFO_MAX_ATTEMPTS = 3
_INFO_RETRY_BACKOFF_SECONDS = 0.6


def _format_duration(seconds: float | None) -> str | None:
    """Render a duration as a clock: 'M:SS', or 'H:MM:SS' past an hour.

    Always shows at least minutes:seconds. We format from the raw seconds rather
    than reusing yt-dlp's own ``duration_string`` because the latter collapses to
    bare seconds for clips under a minute (e.g. '5' for a 5-second video).
    """
    if seconds is None or seconds < 0:
        return None

    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _map_format(raw: dict[str, Any]) -> MediaFormat:
    """Convert a raw yt-dlp format dict into a typed MediaFormat."""
    vcodec = raw.get("vcodec")
    acodec = raw.get("acodec")
    has_video = bool(vcodec) and vcodec != "none"
    has_audio = bool(acodec) and acodec != "none"

    filesize = raw.get("filesize") or raw.get("filesize_approx")

    return MediaFormat(
        format_id=str(raw.get("format_id", "")),
        ext=str(raw.get("ext", "")),
        resolution=raw.get("resolution") or raw.get("format_note"),
        fps=raw.get("fps"),
        vcodec=vcodec if has_video else None,
        acodec=acodec if has_audio else None,
        filesize=int(filesize) if isinstance(filesize, (int, float)) else None,
        has_video=has_video,
        has_audio=has_audio,
    )


def _best_thumbnail(raw: dict[str, Any]) -> str | None:
    """Pick the highest-preference thumbnail URL from the info dict."""
    direct = raw.get("thumbnail")
    if isinstance(direct, str):
        return direct

    thumbnails = raw.get("thumbnails")
    if isinstance(thumbnails, list) and thumbnails:
        last = thumbnails[-1]
        if isinstance(last, dict):
            url = last.get("url")
            return url if isinstance(url, str) else None
    return None


def _audio_langs(info: dict[str, Any]) -> list[str]:
    """Distinct, sorted languages of the available audio tracks.

    Scans every format that carries audio (its ``acodec`` is present and not
    "none") and collects each non-null/non-empty ``language`` code. Many formats
    report ``language: null`` (and video-only tracks none at all); those are
    ignored. More than one distinct language means the source is multi-audio.
    Defensive against a missing/malformed ``formats`` list.
    """
    raw_formats = info.get("formats")
    if not isinstance(raw_formats, list):
        return []

    langs: set[str] = set()
    for fmt in raw_formats:
        if not isinstance(fmt, dict):
            continue
        acodec = fmt.get("acodec")
        if not isinstance(acodec, str) or not acodec or acodec == "none":
            continue
        language = fmt.get("language")
        if isinstance(language, str) and language:
            langs.add(language)
    return sorted(langs)


def _subtitle_langs(info: dict[str, Any]) -> list[str]:
    """Published (manual) subtitle language codes, sorted.

    yt-dlp exposes manual ``subtitles`` as a ``{lang: [...]}`` mapping. Defensive
    against it being missing or malformed.
    """
    tracks = info.get("subtitles")
    if not isinstance(tracks, dict):
        return []
    return sorted(code for code in tracks if isinstance(code, str))


def _auto_caption_langs(info: dict[str, Any], manual: list[str]) -> list[str]:
    """Auto-generated caption languages, excluding ones already published.

    yt-dlp lists ``automatic_captions`` separately (YouTube exposes ~100
    machine-translated tracks). They're returned apart from the manual subs so
    the UI can group them under their own heading. Codes already present as
    manual subtitles are dropped to avoid duplicates.
    """
    tracks = info.get("automatic_captions")
    if not isinstance(tracks, dict):
        return []
    seen = set(manual)
    return sorted(
        code for code in tracks if isinstance(code, str) and code not in seen
    )


def _build_video(info: dict[str, Any]) -> VideoInfo:
    """Build a fully-typed VideoInfo from a resolved yt-dlp info dict."""
    raw_formats = info.get("formats")
    formats: list[MediaFormat] = (
        [_map_format(fmt) for fmt in raw_formats if isinstance(fmt, dict)]
        if isinstance(raw_formats, list)
        else []
    )

    duration = info.get("duration")
    duration_value: float | None = (
        float(duration) if isinstance(duration, (int, float)) else None
    )

    source_lossless, best_audio_abr = _audio_summary(raw_formats)
    manual_subs = _subtitle_langs(info)
    is_vr, vr_layout = detect_vr(info)

    return VideoInfo(
        id=str(info.get("id", "")),
        title=str(info.get("title", "Untitled")),
        duration=duration_value,
        duration_string=_format_duration(duration_value),
        uploader=info.get("uploader"),
        thumbnail_url=_best_thumbnail(info),
        webpage_url=info.get("webpage_url"),
        extractor=info.get("extractor_key") or info.get("extractor"),
        formats=formats,
        source_lossless=source_lossless,
        best_audio_abr=best_audio_abr,
        subtitle_langs=manual_subs,
        auto_caption_langs=_auto_caption_langs(info, manual_subs),
        has_chapters=bool(info.get("chapters")),
        audio_langs=_audio_langs(info),
        is_vr=is_vr,
        vr_layout=vr_layout,
    )


def _build_entry(raw: dict[str, Any]) -> PlaylistEntry | None:
    """Build a flat PlaylistEntry, or None if it has no usable URL."""
    url = raw.get("url") or raw.get("webpage_url")
    if not isinstance(url, str):
        return None

    duration = raw.get("duration")
    duration_value = float(duration) if isinstance(duration, (int, float)) else None

    views = raw.get("view_count")
    return PlaylistEntry(
        id=str(raw.get("id", "")),
        title=str(raw.get("title") or raw.get("id") or "Untitled"),
        url=url,
        duration_string=_format_duration(duration_value),
        thumbnail_url=_best_thumbnail(raw),
        uploader=raw.get("uploader") or raw.get("channel"),
        view_count=views if isinstance(views, int) else None,
    )


def _build_playlist(
    info: dict[str, Any],
    source_lossless: bool = False,
    best_audio_abr: float | None = None,
) -> PlaylistInfo:
    """Build a (possibly capped) PlaylistInfo from a flat yt-dlp playlist dict."""
    raw_entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
    total = info.get("playlist_count")
    if not isinstance(total, int):
        total = len(raw_entries)

    entries = [
        entry
        for entry in (_build_entry(e) for e in raw_entries[:_ENTRY_CAP])
        if entry is not None
    ]

    # VR detection for a flat playlist relies on the playlist title/uploader (no
    # per-item formats), so it's weaker than a single video's — the batch toggle
    # lets the user confirm or correct it.
    is_vr, vr_layout = detect_vr(info)

    return PlaylistInfo(
        id=str(info.get("id", "")),
        title=str(info.get("title") or "Playlist"),
        uploader=info.get("uploader") or info.get("channel"),
        entry_count=total,
        entries=entries,
        # True if the listing is shorter than the reported total — whether from
        # the _ENTRY_CAP cap or entries dropped for missing a usable URL.
        truncated=len(entries) < total,
        source_lossless=source_lossless,
        best_audio_abr=best_audio_abr,
        is_vr=is_vr,
        vr_layout=vr_layout,
    )


def _probe_first_entry_audio(info: dict[str, Any]) -> tuple[bool, float | None]:
    """Resolve the first playlist entry to learn if the source is lossless.

    Playlists are listed flat (no per-item formats), so to gate FLAC/WAV like a
    single video we resolve just the first entry and assume the list is
    homogeneous in source quality. Best-effort: any failure → (False, None).
    """
    entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
    first_url = next(
        (
            e.get("url") or e.get("webpage_url")
            for e in entries
            if e.get("url") or e.get("webpage_url")
        ),
        None,
    )
    if not isinstance(first_url, str):
        return False, None

    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        **network_options(),
    }
    try:
        with YoutubeDL(options) as ydl:
            register_threads_ie(ydl)
            raw = ydl.extract_info(normalize_url(first_url), download=False)
            entry = cast(dict[str, Any], ydl.sanitize_info(raw))
    except DownloadError:
        return False, None
    return _audio_summary(entry.get("formats"))


def extract_info(url: str) -> InfoResponse:
    """Extract clean metadata for a URL — a single video or a playlist.

    Playlists are listed flat (entries are not individually resolved) so the
    response stays fast even for large lists.

    Raises:
        MediaExtractionError: if yt-dlp fails or returns no data.
    """
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        # Flatten items *inside* a playlist, but fully resolve a single video.
        "extract_flat": "in_playlist",
        **network_options(),
    }

    def _extract(opts: dict[str, Any]) -> dict[str, Any]:
        with YoutubeDL(opts) as ydl:
            register_threads_ie(ydl)  # Threads support (no native yt-dlp extractor)
            raw_info = ydl.extract_info(normalize_url(url), download=False)
            # sanitize_info makes the dict JSON-serializable and stable.
            return cast(dict[str, Any], ydl.sanitize_info(raw_info))

    def _attempt() -> dict[str, Any]:
        """One full extraction attempt: primary + tolerant fallback."""
        try:
            return _extract(options)
        except DownloadError as exc:
            # Some sites (e.g. behind anti-bot HLS) expose formats the default
            # selector rejects, raising "Requested format is not available"
            # before we even see the metadata. Retry once tolerating that so the
            # preview (and the VR badge) can still render; only the first try's
            # failure surfaces if this one fails too.
            try:
                tolerant = _extract({**options, "ignore_no_formats_error": True})
            except DownloadError:
                raise MediaExtractionError(
                    str(exc), transient=_is_transient_error(str(exc))
                ) from exc
            # The tolerant retry can succeed but yield a single video with no
            # usable formats — a preview that looks downloadable yet fails at
            # download time. Surface the original error instead of that
            # misleading state. Playlists (entries, not top-level formats) are
            # exempt.
            is_single_video = (
                tolerant.get("_type") != "playlist"
                and tolerant.get("entries") is None
            )
            if is_single_video and not tolerant.get("formats"):
                raise MediaExtractionError(
                    str(exc), transient=_is_transient_error(str(exc))
                ) from exc
            return tolerant

    # Retry only *transient* failures (a one-off anti-bot 403 / network blip),
    # with a short backoff, so a momentary glitch self-heals instead of failing
    # the analyze. Permanent errors (unsupported/private URL) raise immediately.
    info: dict[str, Any] = {}
    for attempt in range(_INFO_MAX_ATTEMPTS):
        try:
            info = _attempt()
            break
        except MediaExtractionError as exc:
            if not exc.transient or attempt == _INFO_MAX_ATTEMPTS - 1:
                raise
            time.sleep(_INFO_RETRY_BACKOFF_SECONDS * (attempt + 1))

    if not info:
        raise MediaExtractionError("yt-dlp returned no metadata for this URL.")

    if info.get("_type") == "playlist" or info.get("entries") is not None:
        lossless, abr = _probe_first_entry_audio(info)
        return InfoResponse(
            type="playlist",
            playlist=_build_playlist(
                info, source_lossless=lossless, best_audio_abr=abr
            ),
        )
    return InfoResponse(type="video", video=_build_video(info))


# Number of search hits to surface in the URL-field typeahead.
_SEARCH_CAP = 8


def search_youtube(query: str, limit: int = _SEARCH_CAP) -> list[PlaylistEntry]:
    """Flat YouTube search for the URL-field typeahead.

    Uses yt-dlp's ``ytsearch`` with ``extract_flat`` so results come back fast
    (no per-video resolution, ~1s). Reuses :func:`_build_entry` — a search hit
    has the same shape as a flat playlist entry — and falls back to the canonical
    YouTube thumbnail when the flat entry doesn't carry one.

    Raises:
        MediaExtractionError: if yt-dlp fails.
    """
    query = query.strip()
    if not query:
        return []

    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "socket_timeout": 8,  # fail fast — this feeds a typeahead
        **network_options(),
    }
    try:
        with YoutubeDL(options) as ydl:
            raw_info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            info = cast(dict[str, Any], ydl.sanitize_info(raw_info))
    except DownloadError as exc:
        raise MediaExtractionError(str(exc)) from exc

    if not info:
        return []

    results: list[PlaylistEntry] = []
    for raw in info.get("entries") or []:
        if not isinstance(raw, dict):
            continue
        entry = _build_entry(raw)
        if entry is None:
            continue
        if not entry.thumbnail_url and entry.id:
            entry.thumbnail_url = f"https://i.ytimg.com/vi/{entry.id}/mqdefault.jpg"
        results.append(entry)
    return results
