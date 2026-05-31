"""Application configuration.

Settings are read from environment variables (optionally a local `.env`)
and fall back to sensible, OS-agnostic defaults so Yoink runs natively on
both Linux and Windows.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_download_dir() -> Path:
    """Cross-platform default download location (`~/Downloads/Yoink`)."""
    return Path.home() / "Downloads" / "Yoink"


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
    api_prefix: str = "/api"

    # Origins allowed to call the API (the local Vite dev server by default).
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    # Where downloaded media is written. Kept as a pathlib.Path for OS-agnostic
    # handling across Linux and Windows.
    download_dir: Path = Field(default_factory=_default_download_dir)

    # Where app data (the SQLite history DB) lives.
    data_dir: Path = Field(default_factory=_default_data_dir)

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
