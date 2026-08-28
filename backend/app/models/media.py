"""Pydantic models describing the metadata contract returned to the frontend.

These mirror the TypeScript types in `src/types/download.ts` so both sides of
the app agree on the JSON shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

MediaKind = Literal["video", "audio"]
HistoryStatus = Literal["completed", "error"]

# Output containers for a video download (merge target).
VideoContainer = Literal["mp4", "mov", "mkv"]
# Output formats for an audio-only download. mp3/m4a are lossy; flac/wav are
# lossless and only meaningful when the source itself is lossless.
AudioFormat = Literal["mp3", "m4a", "flac", "wav"]
AutotagSource = Literal["auto", "apple", "deezer", "musicbrainz"]
SponsorblockAction = Literal["remove", "mark"]
VideoCodec = Literal["any", "h264", "vp9", "av1"]
AudioBitrate = Literal["best", "320", "256", "192", "128"]
# Stereo + projection layout for immersive (VR) video.
VRLayout = Literal[
    "180_sbs",
    "180_tb",
    "180_mono",
    "360_sbs",
    "360_tb",
    "360_mono",
    "fisheye190",
    "fisheye200",
    "mkx200",
    "mkx220",
    "rf52",
]


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
    has_audio: bool = Field(
        default=True,
        description="False when the source exposes no audio at all (video-only — "
        "the download will be silent).",
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
    is_vr: bool = Field(
        default=False,
        description="Heuristically detected as immersive (VR) video.",
    )
    vr_layout: VRLayout = Field(
        default="180_sbs",
        description="Suggested stereo/projection layout (seeds the VR toggle).",
    )


class PlaylistEntry(BaseModel):
    """A lightweight (flat) listing of one item inside a playlist."""

    id: str = Field(..., description="Source-specific media id.")
    title: str = Field(..., description="Item title.")
    url: str = Field(..., description="URL used to download this item.")
    duration_string: str | None = Field(default=None)
    thumbnail_url: str | None = Field(default=None)
    uploader: str | None = Field(default=None)
    view_count: int | None = Field(default=None, description="View count, if known.")
    already_downloaded: bool = Field(
        default=False,
        description="This item's URL is already a completed download (playlist sync).",
    )


class PlaylistInfo(BaseModel):
    """Flat metadata for a playlist (entries are not fully resolved)."""

    id: str = Field(..., description="Playlist id.")
    title: str = Field(..., description="Playlist title.")
    uploader: str | None = Field(default=None, description="Playlist owner.")
    thumbnail_url: str | None = Field(
        default=None, description="Playlist cover (or the first entry's thumbnail)."
    )
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
    is_vr: bool = Field(
        default=False,
        description="Heuristically detected as a VR playlist (title/channel).",
    )
    vr_layout: VRLayout = Field(
        default="180_sbs",
        description="Suggested layout to tag the whole batch with.",
    )


class InfoResponse(BaseModel):
    """Unified `/api/info` result: either a single video or a playlist."""

    type: Literal["video", "playlist"] = Field(..., description="Kind of result.")
    video: VideoInfo | None = Field(default=None)
    playlist: PlaylistInfo | None = Field(default=None)


class SearchResponse(BaseModel):
    """Flat YouTube search hits for the URL-field typeahead (reuses PlaylistEntry)."""

    results: list[PlaylistEntry] = Field(
        default_factory=list, description="Matching videos, best-first."
    )


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
    trim_start: float | None = Field(
        default=None, ge=0, description="Clip start in seconds (download from here)."
    )
    trim_end: float | None = Field(
        default=None, ge=0, description="Clip end in seconds (download up to here)."
    )
    is_vr: bool = Field(
        default=False,
        description="Tag the output as immersive VR (name suffix + spherical metadata).",
    )
    vr_layout: VRLayout = Field(
        default="180_sbs",
        description="Stereo/projection layout to tag with when is_vr is set.",
    )
    auto_vr: bool = Field(
        default=False,
        description=(
            "Auto-detect VR during the download and tag it if found. Used by the "
            "queue, which has no preview/analysis step (the main panel sets is_vr "
            "explicitly instead). Ignored when is_vr is already set."
        ),
    )
    estimated_size: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Client-estimated final size in bytes (from the preview). Scales the "
            "pre-flight free-disk check beyond the fixed floor; ignored when "
            "absent (e.g. queue/playlist items)."
        ),
    )
    output_title: str | None = Field(
        default=None,
        description=(
            "Override the %(title)s used for the output filename. Set by the client "
            "for a single wrapped item (e.g. an Instagram story/post) so the file is "
            "named after the friendlier container title ('Story by X') instead of the "
            "item's own ('Video by X'). Ignored when absent."
        ),
    )

    @model_validator(mode="after")
    def _check_trim_range(self) -> "DownloadRequest":
        """Reject an inverted clip range up front (deterministic 422).

        ``trim_start``/``trim_end`` are each ``ge=0`` but nothing else stops
        ``trim_start=100, trim_end=10``, which would feed yt-dlp a degenerate
        range and surface as a generic download error. A bare ``trim_end=0`` (no
        start) is left to the download layer, which treats it as "no end".
        """
        if (
            self.trim_start is not None
            and self.trim_end is not None
            and self.trim_end <= self.trim_start
        ):
            raise ValueError("trim_end must be greater than trim_start")
        return self


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
    quality: str | None = Field(
        default=None, description="Resolution (video) or bitrate/format (audio)."
    )
    error_message: str | None = Field(
        default=None, description="Failure reason when status is 'error'."
    )
    created_at: str = Field(..., description="ISO-8601 UTC creation timestamp.")
    mtime: float | None = Field(
        default=None,
        description=(
            "Output file's last-modified time (epoch seconds), or None if the file "
            "is gone. Bumps when auto-tagging rewrites the file, so the UI can "
            "cache-bust the cover per row instead of refetching all of them."
        ),
    )


class HistoryStats(BaseModel):
    """Aggregate statistics across the download history."""

    total_downloads: int = Field(..., description="Count of successful downloads.")
    total_bytes: int = Field(..., description="Total bytes transferred.")
    transferred: str = Field(..., description="Human-readable total, e.g. '182 GB'.")


class AppSettings(BaseModel):
    """User-editable settings, persisted to `<data_dir>/settings.json`."""

    download_dir: str = Field(..., description="Where downloads are saved.")
    default_kind: MediaKind = Field(default="video", description="Default media kind.")
    default_quality: str = Field(
        default="best", description="Default video quality ('best' = no cap)."
    )
    default_container: VideoContainer = Field(
        default="mp4", description="Default video container (also the queue's)."
    )
    default_audio_format: AudioFormat = Field(
        default="mp3", description="Default audio format (also the queue's)."
    )
    default_embed_subs: bool = Field(
        default=False,
        description="Seed the subtitle picker to embed subs (when the container allows).",
    )
    default_embed_chapters: bool = Field(
        default=False, description="Seed new video downloads to embed chapter markers."
    )
    nfo_sidecars: bool = Field(
        default=False,
        description="Write a Kodi/Jellyfin-style .nfo metadata file per download.",
    )
    fetch_lyrics: bool = Field(
        default=False,
        description="Fetch + embed song lyrics (LRCLIB) during audio auto-tagging.",
    )
    lyrics_lrc: bool = Field(
        default=False,
        description="Also write a synced .lrc sidecar next to the audio.",
    )
    cookies_from_browser: str | None = Field(
        default=None, description="Browser to read cookies from (e.g. 'firefox')."
    )
    cookies_file: str | None = Field(
        default=None, description="Path to a Netscape cookies.txt file."
    )
    proxy: str | None = Field(
        default=None,
        description="Proxy URL (http/https/socks) for metadata + downloads.",
    )
    po_token: str | None = Field(
        default=None,
        description=(
            "Optional YouTube PO token(s) to pass through to yt-dlp "
            "(youtube:po_token extractor arg) — an anonymous proof-of-origin that "
            "can get past the 'confirm you're not a bot' wall without cookies. "
            "Comma-separated; each is CLIENT.CONTEXT+TOKEN. Empty = off."
        ),
    )
    autotag_source: AutotagSource = Field(
        default="auto", description="Catalogue for audio auto-tagging."
    )
    sponsorblock_enabled: bool = Field(
        default=False, description="Strip/mark SponsorBlock segments (YouTube)."
    )
    sponsorblock_action: SponsorblockAction = Field(
        default="remove", description="Remove the segments or just mark them."
    )
    filename_template: str = Field(
        default="%(title)s",
        description="yt-dlp output name template (extension appended).",
    )
    rate_limit: str | None = Field(
        default=None,
        description="Download speed cap like '1M'/'500K'; None means no cap.",
    )
    video_codec: VideoCodec = Field(
        default="any", description="Preferred video codec ('any' = no preference)."
    )
    audio_bitrate: AudioBitrate = Field(
        default="best", description="Lossy audio bitrate in kbps, or 'best'."
    )
    normalize_audio: bool = Field(
        default=False,
        description="Loudness-normalize audio to -14 LUFS so every track plays "
        "at the same volume (re-encodes the audio).",
    )
    check_updates: bool = Field(
        default=True,
        description="Check GitHub for a newer app release on launch (on by default; "
        "toggle off in Settings — the app only, yt-dlp stays owner-managed).",
    )
    notify_on_complete: bool = Field(
        default=True,
        description="Send a desktop notification when a download finishes "
        "(on by default; toggle off in Settings).",
    )
    minimize_to_tray: bool = Field(
        default=False,
        description="Desktop app: closing the window hides it to the system tray "
        "instead of quitting.",
    )
    launch_at_startup: bool = Field(
        default=False,
        description="Desktop app: launch Yoink automatically when the system starts.",
    )
    disable_global_hotkeys: bool = Field(
        default=False,
        description="Desktop app: disable the global shortcut (Ctrl/Cmd+Shift+Y). Off "
        "by default (global shortcuts are on); turn on to disable them if they clash "
        "with another app.",
    )


class VersionInfo(BaseModel):
    """Result of checking the installed version against the latest release."""

    current: str = Field(..., description="Installed app version.")
    latest: str | None = Field(default=None, description="Latest release tag, if known.")
    update_available: bool = Field(default=False, description="A newer release exists.")
    release_url: str | None = Field(default=None, description="Latest release page URL.")
    error: str | None = Field(default=None, description="Why the check failed, if it did.")


class ReleaseNotes(BaseModel):
    """A release's 'what's new' notes, for the in-app popup after an update."""

    version: str = Field(..., description="The release tag these notes are for.")
    notes: str | None = Field(
        default=None,
        description="Markdown notes, trimmed to the 'what's new' part.",
    )


class WhatsNew(BaseModel):
    """Release notes for the after-update popup — one entry per version, newest
    first. Cumulative: when the user skipped intermediate releases it carries all
    of them, not just the version they landed on."""

    entries: list[ReleaseNotes] = Field(
        default_factory=list,
        description="Notes for each new version since the last run, newest first.",
    )


class OpenRequest(BaseModel):
    """Body of POST /api/open — reveal a file/folder in the OS file manager."""

    path: str | None = Field(
        default=None,
        description="File or folder to reveal. Defaults to the download dir.",
    )
    open_file: bool = Field(
        default=False,
        description="Open the file itself (default app) instead of its folder.",
    )
