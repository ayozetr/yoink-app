"""Models for the keyless Spotify import (scraped from the public embed page)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SpotifyKind = Literal["track", "album", "playlist"]


class SpotifyTrack(BaseModel):
    """One track resolved from a Spotify URL — the metadata we tag with."""

    title: str
    artists: str = Field(description="Joined artist names, e.g. 'Tame Impala, JENNIE'.")
    duration_ms: int | None = None
    is_explicit: bool = False
    album: str | None = None
    year: str | None = None
    cover_url: str | None = None
    spotify_url: str


class SpotifyImportInfo(BaseModel):
    """A resolved Spotify URL: a single track, or an album/playlist tracklist."""

    type: SpotifyKind
    name: str = Field(description="Track title, or the album/playlist name.")
    subtitle: str | None = Field(
        default=None, description="Playlist owner (or album/track artist)."
    )
    cover_url: str | None = None
    tracks: list[SpotifyTrack]
    truncated: bool = Field(
        default=False,
        description="True if the embed exposed fewer tracks than the real total.",
    )


class SpotifyResolveRequest(BaseModel):
    url: str
