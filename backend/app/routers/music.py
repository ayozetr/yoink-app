"""`/api/music` — keyless music import (Spotify / Deezer / Apple / Tidal / Amazon).

`resolve` turns a service URL into a tracklist (public APIs / embed scrapes, no
keys). `match` returns the best-ranked YouTube video for one track (one network
search, so the frontend calls it per track as it downloads).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.models.music import MusicImportInfo, MusicResolveRequest, MusicTrack
from app.services.music_import import MusicImportError, find_youtube_match, resolve

router = APIRouter(tags=["music"])


@router.post(
    "/music/resolve",
    response_model=MusicImportInfo,
    summary="Resolve a music-service URL into a tracklist (keyless)",
)
def resolve_endpoint(request: MusicResolveRequest) -> MusicImportInfo:
    """Parse a Spotify/Deezer/Apple/Tidal/Amazon URL → its tracklist + metadata."""
    try:
        return resolve(request.url)
    except MusicImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


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
