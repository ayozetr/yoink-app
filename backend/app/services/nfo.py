"""Kodi/Jellyfin-style ``.nfo`` metadata sidecars (movie / musicvideo).

Written at download time from yt-dlp's info, and re-written at audio
auto-tagging time from the *tagged* metadata (so the .nfo matches the file's
tags instead of carrying the raw YouTube uploader).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)


def build(
    *,
    kind: str,
    title: str,
    artist: str = "",
    album: str = "",
    plot: str = "",
    year: str = "",
    premiered: str = "",
    runtime: str = "",
    thumb: str = "",
    source: str = "",
    source_id: str = "",
) -> str:
    """A ``.nfo`` body (``musicvideo`` for audio, ``movie`` otherwise)."""
    root = "musicvideo" if kind == "audio" else "movie"

    def tag(name: str, value: str) -> str:
        return f"  <{name}>{escape(value)}</{name}>\n" if value else ""

    body = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<{root}>\n']
    body.append(tag("title", title))
    body.append(tag("artist" if kind == "audio" else "studio", artist))
    if kind == "audio":
        body.append(tag("album", album))
    body.append(tag("plot", plot))
    body.append(tag("year", year))
    body.append(tag("premiered", premiered))
    body.append(tag("runtime", runtime))
    body.append(tag("thumb", thumb))
    body.append(tag("source", source))
    if source_id:
        body.append(f'  <uniqueid type="yoink">{escape(source_id)}</uniqueid>\n')
    body.append(f"</{root}>\n")
    return "".join(body)


def from_info(info: dict[str, Any], kind: str) -> str:
    """Build an .nfo from yt-dlp's info dict (download time)."""
    upload_date = str(info.get("upload_date") or "")  # YYYYMMDD
    duration = info.get("duration")
    return build(
        kind=kind,
        title=str(info.get("title") or ""),
        artist=str(info.get("uploader") or ""),
        plot=str(info.get("description") or ""),
        year=upload_date[:4] if len(upload_date) >= 4 else "",
        premiered=(
            f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
            if len(upload_date) == 8
            else ""
        ),
        runtime=(
            str(int(duration // 60))
            if isinstance(duration, (int, float)) and duration > 0
            else ""
        ),
        thumb=str(info.get("thumbnail") or ""),
        source=str(info.get("webpage_url") or ""),
        source_id=str(info.get("id") or ""),
    )


def write(media_path: Path, body: str) -> None:
    """Write ``<name>.nfo`` next to the media (best-effort; never fatal)."""
    try:
        media_path.with_suffix(".nfo").write_text(body, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write .nfo for %s: %s", media_path.name, exc)
