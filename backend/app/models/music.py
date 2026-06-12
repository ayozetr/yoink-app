"""Models for the keyless music import (Spotify / Deezer / Apple Music / Tidal /
Amazon Music). Each source resolves a URL into the same shape; the YouTube match,
download and tagging downstream are source-agnostic."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MusicSource = Literal["spotify", "deezer", "apple", "tidal", "amazon"]
MusicKind = Literal["track", "album", "playlist"]


class MusicTrack(BaseModel):
    """One track resolved from a music-service URL — the metadata we tag with."""

    title: str
    artists: str = Field(description="Joined artist names, e.g. 'Tame Impala, JENNIE'.")
    duration_ms: int | None = None
    is_explicit: bool = False
    album: str | None = None
    year: str | None = None
    cover_url: str | None = None
    source_url: str = ""


class MusicImportInfo(BaseModel):
    """A resolved music-service URL: a single track, or an album/playlist."""

    source: MusicSource
    type: MusicKind
    name: str = Field(description="Track title, or the album/playlist name.")
    subtitle: str | None = Field(
        default=None, description="Playlist owner, or album/track artist."
    )
    cover_url: str | None = None
    tracks: list[MusicTrack]
    truncated: bool = Field(
        default=False,
        description="True if fewer tracks were resolved than the real total.",
    )


class MusicResolveRequest(BaseModel):
    url: str
