"""Pydantic models for audio auto-tagging (Apple Music / iTunes).

The contract mirrored by the frontend's `src/types/autotag.ts`. The flow is
identify/search → (user picks a version + edits) → apply; nothing is written to
the file until `apply`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TagCandidate(BaseModel):
    """One catalogue match (an Apple Music track release) to tag a file with."""

    title: str = Field(..., description="Track title.")
    artist: str = Field(..., description="Track artist(s).")
    album: str | None = Field(default=None, description="Album / collection name.")
    year: str | None = Field(default=None, description="Release year (YYYY).")
    track_number: int | None = Field(default=None, description="Track number.")
    cover_url: str | None = Field(default=None, description="Cover art URL.")


class IdentifyRequest(BaseModel):
    """Look up matches for an already-downloaded audio file (by its filename)."""

    path: str = Field(..., description="Absolute path to the audio file.")


class SearchRequest(BaseModel):
    """Manual catalogue search."""

    artist: str = Field(default="", description="Artist to search for.")
    title: str = Field(..., description="Track title to search for.")


class CandidateList(BaseModel):
    """Matches returned by identify/search (best first; empty = nothing found)."""

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
    embed_lyrics: bool | None = Field(
        default=None,
        description="Embed lyrics for this track (None = use the global setting).",
    )


class ApplyResponse(BaseModel):
    ok: bool = Field(..., description="Whether the tags were written.")
    embedded_cover: bool = Field(
        default=False, description="Whether cover art was embedded."
    )


class LyricsRequest(BaseModel):
    """Preview-time lyrics lookup for the auto-tag card."""

    title: str = Field(..., description="Track title.")
    artist: str = Field(default="", description="Track artist(s).")
    album: str | None = Field(default=None)
    path: str | None = Field(
        default=None, description="Audio file, to probe its duration for a match."
    )


class LyricsResult(BaseModel):
    found: bool = Field(..., description="Whether any lyrics were found.")
    instrumental: bool = Field(default=False)
    has_synced: bool = Field(default=False, description="A timed .lrc is available.")
    plain: str | None = Field(default=None, description="The full plain lyrics.")
