"""`/api/spotify` — keyless Spotify import: resolve a URL, match a track.

`resolve` scrapes the public embed page into a tracklist (fast, no API key).
`match` searches YouTube for one track and returns the best-ranked video URL
(one network search, so the frontend calls it per track as it downloads).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.models.spotify import SpotifyImportInfo, SpotifyResolveRequest, SpotifyTrack
from app.services.spotify_service import (
    SpotifyError,
    find_youtube_match,
    resolve_spotify,
)

router = APIRouter(tags=["spotify"])


@router.post(
    "/spotify/resolve",
    response_model=SpotifyImportInfo,
    summary="Resolve a Spotify URL into a tracklist (keyless embed scrape)",
)
def resolve_endpoint(request: SpotifyResolveRequest) -> SpotifyImportInfo:
    """Parse a Spotify track/album/playlist URL → its tracklist + metadata."""
    try:
        return resolve_spotify(request.url)
    except SpotifyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


class MatchResponse(BaseModel):
    youtube_url: str | None = None


@router.post(
    "/spotify/match",
    response_model=MatchResponse,
    summary="Find the best-ranked YouTube video for a Spotify track",
)
def match_endpoint(track: SpotifyTrack) -> MatchResponse:
    """Rank YouTube results for the track; None if nothing clears the thresholds."""
    return MatchResponse(youtube_url=find_youtube_match(track))
