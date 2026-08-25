"""Application configuration.

Settings are read from environment variables (optionally a local `.env`)
and fall back to sensible, OS-agnostic defaults so Yoink runs natively on
both Linux and Windows.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel `filename_template` value: name the audio file after the auto-tag
# metadata ("Artist - Title"). yt-dlp can't know the tags at download time, so the
# file downloads under a "%(title)s" fallback and the auto-tag apply step renames it.
AUTOTAG_FILENAME_TEMPLATE = "%(autotag)s"
# Same idea, but names the file "Title - Artist" instead of "Artist - Title".
AUTOTAG_FILENAME_TEMPLATE_REVERSED = "%(autotag_ta)s"


def _xdg_download_dir() -> Path | None:
    """The user's Downloads dir from XDG user-dirs (Linux) — localized, e.g.
    ``Descargas`` / ``Téléchargements``. None if unset (macOS/Windows have no
    such file, so they fall through to ~/Downloads)."""
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or str(home / ".config"))
    try:
        text = (config / "user-dirs.dirs").read_text(encoding="utf-8")
    except OSError:
        return None
    # e.g.  XDG_DOWNLOAD_DIR="$HOME/Descargas"
    match = re.search(
        r'^\s*XDG_DOWNLOAD_DIR\s*=\s*"?(.*?)"?\s*$', text, flags=re.MULTILINE
    )
    if not match:
        return None
    value = match.group(1).replace("$HOME", str(home))
    path = Path(os.path.expandvars(value)).expanduser()
    return path if path.is_absolute() else None


def _windows_download_dir() -> Path | None:
    """The user's Downloads known folder on Windows (honours a relocated one)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(
                key, "{374DE290-123F-4565-9164-39C4925E467B}"
            )
    except OSError:
        return None
    path = Path(os.path.expandvars(str(value)))
    return path if path.is_absolute() else None


def _downloads_dir() -> Path:
    """The OS user's real Downloads folder, regardless of UI language — localized
    on Linux (XDG) or relocated on Windows — falling back to ``~/Downloads``."""
    return _windows_download_dir() or _xdg_download_dir() or (Path.home() / "Downloads")


def _default_download_dir() -> Path:
    """Default download location: the user's Downloads folder + ``/Yoink``."""
    return _downloads_dir() / "Yoink"


def _default_data_dir() -> Path:
    """Cross-platform location for app data (SQLite history, etc.)."""
    return Path.home() / ".yoink"


class Settings(BaseSettings):
    """Strongly-typed runtime settings for the Yoink backend."""

    model_config = SettingsConfigDict(
        env_prefix="YOINK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Yoink Backend"
    app_version: str = "3.4.0"
    api_prefix: str = "/api"

    # GitHub repo used to check for newer releases (owner/name).
    github_repo: str = "ayozetr/yoink-app"

    # Origins allowed to call the API: the local Vite dev server (any port) and
    # the Tauri webview, whose origin scheme is per-platform — tauri://localhost
    # on Linux/macOS, http://tauri.localhost on Windows (WebView2). A regex keeps
    # the local API closed to remote web pages without breaking any local origin.
    cors_origin_regex: str = (
        r"^(tauri://localhost"
        r"|https?://tauri\.localhost"
        r"|https?://(localhost|127\.0\.0\.1)(:\d+)?)$"
    )

    # Where downloaded media is written. Kept as a pathlib.Path for OS-agnostic
    # handling across Linux and Windows.
    download_dir: Path = Field(default_factory=_default_download_dir)

    # Where app data (the SQLite history DB) lives.
    data_dir: Path = Field(default_factory=_default_data_dir)

    # Cookies for sites that require a signed-in session (optional). Set ONE of:
    #   YOINK_COOKIES_FROM_BROWSER=firefox   (read cookies straight from a browser)
    #   YOINK_COOKIES_FILE=/path/cookies.txt (Netscape-format cookies file)
    # Not needed for public content. `cookies_from_browser` takes precedence.
    cookies_from_browser: str | None = Field(default=None)
    cookies_file: Path | None = Field(default=None)

    # Optional proxy for metadata + downloads (e.g. "socks5://127.0.0.1:1080"
    # or "http://host:port"). Applied to every yt-dlp request when set.
    proxy: str | None = Field(default=None)

    # User-editable defaults (persisted via the settings store / settings UI).
    default_kind: Literal["video", "audio"] = "video"
    default_quality: str = "best"
    # Default output container/audio format — used to seed the cards and as the
    # queue's per-item format (the queue has no per-item picker).
    default_container: Literal["mp4", "mov", "mkv"] = "mp4"
    default_audio_format: Literal["mp3", "m4a", "flac", "wav"] = "mp3"
    # Whether new video downloads default to embedding subtitles (the "all"
    # languages option, applied only when the container can carry them) and
    # chapter markers. Container/audio already persist; these complete the set.
    default_embed_subs: bool = False
    default_embed_chapters: bool = False

    # Write a Kodi/Jellyfin-style ".nfo" metadata file next to each download.
    nfo_sidecars: bool = False

    # Fetch + embed song lyrics (from LRCLIB) during audio auto-tagging.
    fetch_lyrics: bool = False

    # Also write a synced ".lrc" sidecar next to the audio (needs fetch_lyrics).
    lyrics_lrc: bool = False

    # Filename template (the name part; ".%(ext)s" is appended at download time).
    # yt-dlp outtmpl fields, e.g. "%(title)s" or "%(uploader)s - %(title)s".
    filename_template: str = "%(title)s"

    # Optional download speed cap in yt-dlp format ("1M", "500K"); None = no cap.
    rate_limit: str | None = Field(default=None)

    # Preferred video codec: "any" = no preference, else bias the format sort.
    video_codec: Literal["any", "h264", "vp9", "av1"] = "any"

    # Audio bitrate for lossy formats (kbps), or "best" for no target (default).
    audio_bitrate: Literal["best", "320", "256", "192", "128"] = "best"

    # Loudness-normalize audio downloads to -14 LUFS (EBU R128) so every track
    # plays at the same volume. Off by default (it re-encodes the audio).
    normalize_audio: bool = False

    # Catalogue used by the audio auto-tagger ("auto" = cascade through all).
    autotag_source: Literal["auto", "apple", "deezer", "musicbrainz"] = "auto"

    # SponsorBlock (YouTube): strip or just mark sponsor / intro / outro segments.
    sponsorblock_enabled: bool = False
    sponsorblock_action: Literal["remove", "mark"] = "remove"

    # Send a desktop notification when a download finishes. Used by the frontend
    # (the backend only stores it so it persists + rides the settings contract).
    notify_on_complete: bool = True

    # Check GitHub for a newer app release on launch (the app only — yt-dlp stays
    # owner-managed). Stored here so the toggle persists across restarts.
    check_updates: bool = True

    # Desktop-only (Tauri) behaviours. The backend only stores them so they persist
    # and ride the settings contract; the Tauri shell reads + applies them.
    minimize_to_tray: bool = False
    launch_at_startup: bool = False
    # Global shortcuts are on by default; if the Ctrl/Cmd+Shift+Y combo clashes with
    # another app, the user turns this on to disable them.
    disable_global_hotkeys: bool = False

    def ensure_download_dir(self) -> Path:
        """Create the download directory if missing and return it."""
        self.download_dir.mkdir(parents=True, exist_ok=True)
        return self.download_dir

    def ensure_data_dir(self) -> Path:
        """Create the app-data directory if missing and return it."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir

    @property
    def db_path(self) -> Path:
        """Absolute path to the SQLite history database."""
        return self.data_dir / "history.db"


settings = Settings()
