"""Persisted, user-editable settings layered on top of the env defaults.

Overrides live in `<data_dir>/settings.json` and are applied onto the in-memory
`settings` singleton, so the rest of the app keeps reading `settings.*` and
automatically sees any changes made through the settings UI — no restart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.models.media import AppSettings


def _settings_path() -> Path:
    return settings.data_dir / "settings.json"


def _apply(data: dict[str, Any]) -> None:
    """Apply a raw overrides dict onto the in-memory settings singleton."""
    download_dir = data.get("download_dir")
    if download_dir:
        settings.download_dir = Path(download_dir)
    if data.get("default_kind") in ("video", "audio"):
        settings.default_kind = data["default_kind"]
    if data.get("default_quality"):
        settings.default_quality = str(data["default_quality"])
    if data.get("default_container") in ("mp4", "mov", "mkv"):
        settings.default_container = data["default_container"]
    if data.get("default_audio_format") in ("mp3", "m4a", "flac", "wav"):
        settings.default_audio_format = data["default_audio_format"]
    if isinstance(data.get("default_embed_subs"), bool):
        settings.default_embed_subs = data["default_embed_subs"]
    if isinstance(data.get("default_embed_chapters"), bool):
        settings.default_embed_chapters = data["default_embed_chapters"]
    if isinstance(data.get("nfo_sidecars"), bool):
        settings.nfo_sidecars = data["nfo_sidecars"]
    if isinstance(data.get("fetch_lyrics"), bool):
        settings.fetch_lyrics = data["fetch_lyrics"]
    if isinstance(data.get("lyrics_lrc"), bool):
        settings.lyrics_lrc = data["lyrics_lrc"]

    settings.cookies_from_browser = data.get("cookies_from_browser") or None
    cookies_file = data.get("cookies_file")
    settings.cookies_file = Path(cookies_file) if cookies_file else None
    settings.proxy = str(data["proxy"]) if data.get("proxy") else None

    if data.get("autotag_source") in ("auto", "apple", "deezer", "musicbrainz"):
        settings.autotag_source = data["autotag_source"]

    if isinstance(data.get("sponsorblock_enabled"), bool):
        settings.sponsorblock_enabled = data["sponsorblock_enabled"]
    if data.get("sponsorblock_action") in ("remove", "mark"):
        settings.sponsorblock_action = data["sponsorblock_action"]

    if data.get("filename_template"):
        settings.filename_template = str(data["filename_template"])
    settings.rate_limit = str(data["rate_limit"]) if data.get("rate_limit") else None
    if data.get("video_codec") in ("any", "h264", "vp9", "av1"):
        settings.video_codec = data["video_codec"]
    if data.get("audio_bitrate") in ("best", "320", "256", "192", "128"):
        settings.audio_bitrate = data["audio_bitrate"]


def load_overrides() -> None:
    """Load persisted overrides at startup (no-op if none/invalid)."""
    path = _settings_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(data, dict):
        _apply(data)


def get_current() -> AppSettings:
    """Snapshot the current effective settings."""
    return AppSettings(
        download_dir=str(settings.download_dir),
        default_kind=settings.default_kind,
        default_quality=settings.default_quality,
        default_container=settings.default_container,
        default_audio_format=settings.default_audio_format,
        default_embed_subs=settings.default_embed_subs,
        default_embed_chapters=settings.default_embed_chapters,
        nfo_sidecars=settings.nfo_sidecars,
        fetch_lyrics=settings.fetch_lyrics,
        lyrics_lrc=settings.lyrics_lrc,
        cookies_from_browser=settings.cookies_from_browser,
        cookies_file=str(settings.cookies_file) if settings.cookies_file else None,
        proxy=settings.proxy,
        autotag_source=settings.autotag_source,
        sponsorblock_enabled=settings.sponsorblock_enabled,
        sponsorblock_action=settings.sponsorblock_action,
        filename_template=settings.filename_template,
        rate_limit=settings.rate_limit,
        video_codec=settings.video_codec,
        audio_bitrate=settings.audio_bitrate,
    )


def update(payload: AppSettings) -> AppSettings:
    """Apply and persist new settings, returning the effective snapshot."""
    data = payload.model_dump()
    _apply(data)
    settings.ensure_data_dir()
    _settings_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    return get_current()
