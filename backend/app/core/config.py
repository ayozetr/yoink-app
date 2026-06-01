"""Application configuration.

Settings are read from environment variables (optionally a local `.env`)
and fall back to sensible, OS-agnostic defaults so Yoink runs natively on
both Linux and Windows.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _music_dir() -> Path:
    """The user's Music folder, localized on Linux via XDG (e.g. ``~/Música``)."""
    if sys.platform.startswith("linux"):
        config = (
            Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
            / "user-dirs.dirs"
        )
        try:
            for line in config.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("XDG_MUSIC_DIR"):
                    value = line.split("=", 1)[1].strip().strip('"')
                    return Path(value.replace("$HOME", str(Path.home())))
        except OSError:
            pass
        return Path.home() / "Music"
    # Windows / macOS: the Music folder is always named "Music".
    return Path.home() / "Music"


def _default_download_dir() -> Path:
    """Default download location: the user's Music folder + ``Yoink``."""
    return _music_dir() / "Yoink"


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
    app_version: str = "0.8.2"
    api_prefix: str = "/api"

    # GitHub repo used to check for newer releases (owner/name).
    github_repo: str = "ayozetr/yoink-app"

    # Origins allowed to call the API: the local Vite dev server plus the
    # Tauri webview origins (tauri://localhost on Linux/macOS,
    # https://tauri.localhost on Windows).
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "tauri://localhost",
            "https://tauri.localhost",
        ]
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

    # User-editable defaults (persisted via the settings store / settings UI).
    default_kind: Literal["video", "audio"] = "video"
    default_quality: str = "1080p"

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
