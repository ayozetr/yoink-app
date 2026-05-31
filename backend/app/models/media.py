"""Pydantic models describing the metadata contract returned to the frontend.

These mirror the TypeScript types in `src/types/download.ts` so both sides of
the app agree on the JSON shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

MediaKind = Literal["video", "audio"]
HistoryStatus = Literal["completed", "error"]


class InfoRequest(BaseModel):
    """Body of a POST /api/info request."""

    url: HttpUrl = Field(..., description="The media URL to inspect.")


class MediaFormat(BaseModel):
    """A single downloadable format reported by yt-dlp."""

    format_id: str = Field(..., description="yt-dlp format identifier.")
    ext: str = Field(..., description="Container/extension, e.g. 'mp4', 'm4a'.")
    resolution: str | None = Field(
        default=None, description="Human-readable resolution, e.g. '1080p'."
    )
    fps: float | None = Field(default=None, description="Frames per second, if video.")
    vcodec: str | None = Field(default=None, description="Video codec, or None for audio-only.")
    acodec: str | None = Field(default=None, description="Audio codec, or None for video-only.")
    filesize: int | None = Field(default=None, description="Approximate size in bytes.")
    has_video: bool = Field(default=False, description="Whether the format carries video.")
    has_audio: bool = Field(default=False, description="Whether the format carries audio.")


class VideoInfo(BaseModel):
    """Clean metadata for a media URL (extracted with download=False)."""

    id: str = Field(..., description="Source-specific media id.")
    title: str = Field(..., description="Media title.")
    duration: float | None = Field(default=None, description="Duration in seconds.")
    duration_string: str | None = Field(
        default=None, description="Human-readable duration, e.g. '1h 24m 18s'."
    )
    uploader: str | None = Field(default=None, description="Channel/uploader name.")
    thumbnail_url: str | None = Field(default=None, description="Best thumbnail URL.")
    webpage_url: str | None = Field(default=None, description="Canonical page URL.")
    extractor: str | None = Field(default=None, description="yt-dlp extractor used.")
    formats: list[MediaFormat] = Field(
        default_factory=list, description="Available downloadable formats."
    )


class DownloadRequest(BaseModel):
    """What the frontend asks to download, sent over the WebSocket."""

    url: HttpUrl = Field(..., description="The media URL to download.")
    kind: MediaKind = Field(
        default="video", description="Whether to fetch video (MP4) or audio (MP3)."
    )
    quality: str | None = Field(
        default=None,
        description="Target video quality, e.g. '1080p'. Ignored for audio.",
    )


class ProgressEvent(BaseModel):
    """Streamed repeatedly while yt-dlp downloads (mirrors progress_hooks)."""

    type: Literal["progress"] = "progress"
    status: Literal["downloading", "processing"] = "downloading"
    percent: float = Field(..., description="Completion percentage, 0–100.")
    downloaded_bytes: int | None = Field(default=None)
    total_bytes: int | None = Field(default=None)
    speed: str | None = Field(default=None, description="Human-readable, e.g. '3.2 MB/s'.")
    eta: str | None = Field(default=None, description="Human-readable, e.g. '00:42'.")
    filename: str | None = Field(default=None, description="Output file name.")


class CompletedEvent(BaseModel):
    """Sent once the file (post-merge / post-extraction) is ready on disk."""

    type: Literal["completed"] = "completed"
    filename: str = Field(..., description="Final file name on disk.")
    filepath: str = Field(..., description="Absolute path to the saved file.")
    total_bytes: int | None = Field(default=None, description="Final size in bytes.")


class ErrorEvent(BaseModel):
    """Sent when the download fails; terminal."""

    type: Literal["error"] = "error"
    message: str = Field(..., description="Human-readable failure reason.")


class HistoryEntry(BaseModel):
    """A persisted record of a completed or failed download."""

    id: int = Field(..., description="Auto-increment primary key.")
    title: str = Field(..., description="Media title (or file name).")
    url: str = Field(..., description="Source URL of the download.")
    kind: MediaKind = Field(..., description="Whether it was video or audio.")
    status: HistoryStatus = Field(..., description="Final outcome.")
    filename: str | None = Field(default=None, description="Output file name.")
    filepath: str | None = Field(default=None, description="Absolute path on disk.")
    filesize: int | None = Field(default=None, description="Final size in bytes.")
    created_at: str = Field(..., description="ISO-8601 UTC creation timestamp.")


class HistoryStats(BaseModel):
    """Aggregate statistics across the download history."""

    total_downloads: int = Field(..., description="Count of successful downloads.")
    total_bytes: int = Field(..., description="Total bytes transferred.")
    transferred: str = Field(..., description="Human-readable total, e.g. '182 GB'.")


class OpenRequest(BaseModel):
    """Body of POST /api/open — reveal a file/folder in the OS file manager."""

    path: str | None = Field(
        default=None,
        description="File or folder to reveal. Defaults to the download dir.",
    )
