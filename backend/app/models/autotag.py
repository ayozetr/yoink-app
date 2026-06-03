"""Pydantic models for audio auto-tagging (AcoustID + MusicBrainz).

The contract mirrored by the frontend's `src/types/autotag.ts`. The flow is
identify → (user reviews/picks) → apply, so `identify`/`search` only *propose*
metadata; nothing is written until `apply`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlbumOption(BaseModel):
    """One candidate album (MusicBrainz release group) for a recording."""

    title: str = Field(..., description="Album title.")
    year: str | None = Field(default=None, description="First-release year (YYYY).")
    release_group_id: str = Field(..., description="MusicBrainz release-group MBID.")
    primary_type: str | None = Field(
        default=None, description="Album / EP / Single / …"
    )
    is_studio_album: bool = Field(
        default=False,
        description="A plain studio album (no Compilation/Live/Soundtrack tag).",
    )
    cover_url: str | None = Field(
        default=None, description="Cover Art Archive front-image URL, if any."
    )


class TagCandidate(BaseModel):
    """A proposed tagging for an audio file — the identified song + album picks."""

    title: str = Field(..., description="Track title.")
    artist: str = Field(..., description="Track artist(s).")
    album: str | None = Field(default=None, description="Suggested album title.")
    year: str | None = Field(default=None, description="Suggested release year.")
    track_number: int | None = Field(default=None, description="Track number.")
    cover_url: str | None = Field(default=None, description="Suggested cover URL.")
    recording_id: str | None = Field(
        default=None, description="MusicBrainz recording MBID."
    )
    score: float = Field(default=0.0, description="AcoustID match score (0–1).")
    album_options: list[AlbumOption] = Field(
        default_factory=list,
        description="Alternative albums the user can pick from (suggested first).",
    )


class IdentifyRequest(BaseModel):
    """Identify the song in an already-downloaded audio file."""

    path: str = Field(..., description="Absolute path to the audio file.")


class IdentifyResponse(BaseModel):
    matched: bool = Field(..., description="Whether AcoustID found a confident match.")
    candidate: TagCandidate | None = Field(
        default=None, description="The proposed tagging, when matched."
    )


class SearchRequest(BaseModel):
    """Manual MusicBrainz search, used when fingerprinting doesn't fit."""

    artist: str = Field(default="", description="Artist to search for.")
    title: str = Field(..., description="Track title to search for.")


class SearchResponse(BaseModel):
    results: list[TagCandidate] = Field(default_factory=list)


class ApplyRequest(BaseModel):
    """Write the (possibly user-edited) tags + cover into the file."""

    path: str = Field(..., description="Absolute path to the audio file.")
    title: str | None = Field(default=None)
    artist: str | None = Field(default=None)
    album: str | None = Field(default=None)
    year: str | None = Field(default=None)
    track_number: int | None = Field(default=None)
    cover_url: str | None = Field(default=None, description="Cover art to embed.")


class ApplyResponse(BaseModel):
    ok: bool = Field(..., description="Whether the tags were written.")
    embedded_cover: bool = Field(
        default=False, description="Whether cover art was embedded."
    )
