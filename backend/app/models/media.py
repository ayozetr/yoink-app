"""Pydantic models describing the metadata contract returned to the frontend.

These mirror the TypeScript types in `src/types/download.ts` so both sides of
the app agree on the JSON shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

MediaKind = Literal["video", "audio"]
HistoryStatus = Literal["completed", "error"]

# Output containers for a video download (merge target).
VideoContainer = Literal["mp4", "mov", "mkv"]
# Output formats for an audio-only download. mp3/m4a are lossy; flac/wav are
# lossless and only meaningful when the source itself is lossless.
AudioFormat = Literal["mp3", "m4a", "flac", "wav"]
AutotagSource = Literal["apple", "deezer"]


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
        default=None, description="Clock-formatted duration, e.g. '1:24:18' or '0:05'."
    )
    uploader: str | None = Field(default=None, description="Channel/uploader name.")
    thumbnail_url: str | None = Field(default=None, description="Best thumbnail URL.")
    webpage_url: str | None = Field(default=None, description="Canonical page URL.")
    extractor: str | None = Field(default=None, description="yt-dlp extractor used.")
    formats: list[MediaFormat] = Field(
        default_factory=list, description="Available downloadable formats."
    )
    source_lossless: bool = Field(
        default=False,
        description="True if the best audio source is lossless (flac/alac/wav/pcm/tta/…).",
    )
    best_audio_abr: float | None = Field(
        default=None, description="Highest audio bitrate available, in kbps."
    )
    subtitle_langs: list[str] = Field(
        default_factory=list,
        description="Published (manual) subtitle language codes.",
    )
    auto_caption_langs: list[str] = Field(
        default_factory=list,
        description="Auto-generated caption codes not already in subtitle_langs.",
    )
    has_chapters: bool = Field(
        default=False, description="Whether the source exposes chapter markers."
    )
    audio_langs: list[str] = Field(
        default_factory=list,
        description="Languages of the available audio tracks (>1 means multi-audio).",
    )


class PlaylistEntry(BaseModel):
    """A lightweight (flat) listing of one item inside a playlist."""

    id: str = Field(..., description="Source-specific media id.")
    title: str = Field(..., description="Item title.")
    url: str = Field(..., description="URL used to download this item.")
    duration_string: str | None = Field(default=None)
    thumbnail_url: str | None = Field(default=None)
    uploader: str | None = Field(default=None)


class PlaylistInfo(BaseModel):
    """Flat metadata for a playlist (entries are not fully resolved)."""

    id: str = Field(..., description="Playlist id.")
    title: str = Field(..., description="Playlist title.")
    uploader: str | None = Field(default=None, description="Playlist owner.")
    entry_count: int = Field(..., description="Total items reported by yt-dlp.")
    entries: list[PlaylistEntry] = Field(
        default_factory=list, description="Listed items (may be capped)."
    )
    truncated: bool = Field(
        default=False, description="True if entries were capped below entry_count."
    )
    # Probed from the first entry (playlists are flat, so this assumes the list
    # is homogeneous in source quality) to gate FLAC/WAV like a single video.
    source_lossless: bool = Field(
        default=False,
        description="Whether the first entry's best audio source is lossless.",
    )
    best_audio_abr: float | None = Field(
        default=None, description="Best audio bitrate (kbps) of the first entry."
    )


class InfoResponse(BaseModel):
    """Unified `/api/info` result: either a single video or a playlist."""

    type: Literal["video", "playlist"] = Field(..., description="Kind of result.")
    video: VideoInfo | None = Field(default=None)
    playlist: PlaylistInfo | None = Field(default=None)


class DownloadRequest(BaseModel):
    """What the frontend asks to download, sent over the WebSocket."""

    url: HttpUrl = Field(..., description="The media URL to download.")
    kind: MediaKind = Field(
        default="video", description="Whether to fetch video or audio."
    )
    quality: str | None = Field(
        default=None,
        description="Target video quality, e.g. '1080p'. Ignored for audio.",
    )
    container: VideoContainer = Field(
        default="mp4", description="Output container when kind=video (merge target)."
    )
    audio_format: AudioFormat = Field(
        default="mp3", description="Output format when kind=audio."
    )
    embed_subs: bool = Field(
        default=False,
        description="Embed subtitles into the video output when available.",
    )
    subtitle_lang: str | None = Field(
        default=None,
        description="Subtitle language to embed: a code like 'en'/'es', 'all', or None.",
    )
    embed_chapters: bool = Field(
        default=False,
        description="Embed chapter markers + metadata when the source has them.",
    )
    audio_multistreams: bool = Field(
        default=False,
        description="Include all audio tracks (multi-language) in the video output.",
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


class AppSettings(BaseModel):
    """User-editable settings, persisted to `<data_dir>/settings.json`."""

    download_dir: str = Field(..., description="Where downloads are saved.")
    default_kind: MediaKind = Field(default="video", description="Default media kind.")
    default_quality: str = Field(default="1080p", description="Default video quality.")
    cookies_from_browser: str | None = Field(
        default=None, description="Browser to read cookies from (e.g. 'firefox')."
    )
    cookies_file: str | None = Field(
        default=None, description="Path to a Netscape cookies.txt file."
    )
    autotag_source: AutotagSource = Field(
        default="apple", description="Catalogue for audio auto-tagging."
    )


class VersionInfo(BaseModel):
    """Result of checking the installed version against the latest release."""

    current: str = Field(..., description="Installed app version.")
    latest: str | None = Field(default=None, description="Latest release tag, if known.")
    update_available: bool = Field(default=False, description="A newer release exists.")
    release_url: str | None = Field(default=None, description="Latest release page URL.")
    error: str | None = Field(default=None, description="Why the check failed, if it did.")


class OpenRequest(BaseModel):
    """Body of POST /api/open — reveal a file/folder in the OS file manager."""

    path: str | None = Field(
        default=None,
        description="File or folder to reveal. Defaults to the download dir.",
    )
