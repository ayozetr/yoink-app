"""Thin, strictly-typed wrapper around yt-dlp for metadata extraction.

This module only performs *information extraction* (`download=False`). The
actual download + progress-streaming logic will live alongside it later.
"""

from __future__ import annotations

from typing import Any, cast

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.models.media import MediaFormat, VideoInfo


class MediaExtractionError(RuntimeError):
    """Raised when yt-dlp cannot extract metadata for a URL."""


def _format_duration(seconds: float | None) -> str | None:
    """Render a duration in seconds as e.g. '1h 24m 18s' (OS-independent)."""
    if seconds is None:
        return None

    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if hours or minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


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


def extract_info(url: str) -> VideoInfo:
    """Extract clean metadata for a media URL without downloading it.

    Raises:
        MediaExtractionError: if yt-dlp fails or returns no data.
    """
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }

    try:
        with YoutubeDL(options) as ydl:
            raw_info = ydl.extract_info(url, download=False)
            # sanitize_info makes the dict JSON-serializable and stable.
            info = cast(dict[str, Any], ydl.sanitize_info(raw_info))
    except DownloadError as exc:
        raise MediaExtractionError(str(exc)) from exc

    if not info:
        raise MediaExtractionError("yt-dlp returned no metadata for this URL.")

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

    return VideoInfo(
        id=str(info.get("id", "")),
        title=str(info.get("title", "Untitled")),
        duration=duration_value,
        duration_string=info.get("duration_string") or _format_duration(duration_value),
        uploader=info.get("uploader"),
        thumbnail_url=_best_thumbnail(info),
        webpage_url=info.get("webpage_url"),
        extractor=info.get("extractor_key") or info.get("extractor"),
        formats=formats,
    )
