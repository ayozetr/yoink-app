"""`/api/music` — keyless music import (Spotify / Deezer / Apple / Tidal / Amazon).

`resolve` turns a service URL into a tracklist (public APIs / embed scrapes, no
keys). `match` returns the best-ranked YouTube video for one track (one network
search, so the frontend calls it per track as it downloads).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.models.music import MusicImportInfo, MusicResolveRequest, MusicTrack
from app.services.music_import import (
    MusicImportError,
    find_youtube_match,
    resolve,
    track_meta,
)

router = APIRouter(tags=["music"])


@router.post(
    "/music/resolve",
    response_model=MusicImportInfo,
    summary="Resolve a music-service URL into a tracklist (keyless)",
)
def resolve_endpoint(request: MusicResolveRequest) -> MusicImportInfo:
    """Parse a Spotify/Deezer/Apple/Tidal/Amazon URL → its tracklist + metadata.

    Returned *without* the per-track Deezer cover/duration backfill so a big
    playlist appears instantly; the frontend then fills each track's cover lazily
    via ``/music/cover``.
    """
    try:
        return resolve(request.url, enrich=False)
    except MusicImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


class TrackMetaResponse(BaseModel):
    cover_url: str | None = None
    duration_ms: int | None = None


@router.post(
    "/music/cover",
    response_model=TrackMetaResponse,
    summary="Look up one track's cover art + duration (keyless, for lazy fill)",
)
def cover_endpoint(track: MusicTrack) -> TrackMetaResponse:
    """One keyless Deezer lookup for a track → its cover art + duration. Paced
    server-side, so the frontend can fire one per visible row without tripping
    Deezer's rate limit."""
    cover, duration_ms = track_meta(track.title, track.artists)
    return TrackMetaResponse(cover_url=cover, duration_ms=duration_ms)


class MatchResponse(BaseModel):
    youtube_url: str | None = None


@router.post(
    "/music/match",
    response_model=MatchResponse,
    summary="Find the best-ranked YouTube video for a track",
)
def match_endpoint(track: MusicTrack) -> MatchResponse:
    """Rank YouTube results for the track; None if nothing clears the thresholds."""
    return MatchResponse(youtube_url=find_youtube_match(track))
