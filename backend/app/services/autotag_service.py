"""Audio auto-tagging: acoustic fingerprint → AcoustID → MusicBrainz → tags.

`identify()` fingerprints a file (Chromaprint/`fpcalc`), looks it up on AcoustID,
and resolves the song's metadata + candidate albums on MusicBrainz (the album is
ambiguous — a song can be on hundreds of releases — so we suggest the earliest
plain studio album but return the alternatives for the user to pick). `search()`
is a manual MusicBrainz fallback. `apply()` writes the (possibly user-edited)
tags + cover art into the file with mutagen. Nothing is written until `apply()`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import acoustid
import musicbrainzngs
import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TDRC, TIT2, TPE1, TRCK
from mutagen.mp4 import MP4, MP4Cover

from app.core.config import settings
from app.models.autotag import (
    AlbumOption,
    ApplyRequest,
    ApplyResponse,
    IdentifyResponse,
    SearchResponse,
    TagCandidate,
)

_USER_AGENT = f"Yoink/{settings.app_version} (https://github.com/ayozetr/yoink-app)"

musicbrainzngs.set_useragent(
    "Yoink", settings.app_version, "https://github.com/ayozetr/yoink-app"
)
musicbrainzngs.set_rate_limit()  # MusicBrainz requires ≤1 req/s

# Secondary release-group types that disqualify a "plain studio album".
_NON_STUDIO = {
    "Compilation", "Live", "Soundtrack", "Remix", "DJ-mix",
    "Mixtape/Street", "Demo", "Interview", "Audiobook",
}
# How many albums to date-lookup / return, to bound MusicBrainz calls.
_ALBUM_LIMIT = 8


class AutotagError(RuntimeError):
    """Raised for any auto-tagging failure surfaced to the client."""


# --- identify --------------------------------------------------------------

def identify(path: Path) -> IdentifyResponse:
    """Fingerprint + AcoustID + MusicBrainz → a proposed tagging (no write)."""
    api_key = settings.acoustid_api_key.strip()
    if not api_key:
        raise AutotagError(
            "No AcoustID API key configured — add one in Settings "
            "(free at acoustid.org/new-application)."
        )

    try:
        duration, fingerprint = acoustid.fingerprint_file(str(path))
    except acoustid.NoBackendError as exc:
        raise AutotagError("fpcalc (Chromaprint) is not available.") from exc
    except acoustid.FingerprintGenerationError as exc:
        raise AutotagError(f"Could not fingerprint the audio: {exc}") from exc

    try:
        response = acoustid.lookup(
            api_key, fingerprint, duration, meta="recordings releasegroups"
        )
    except acoustid.WebServiceError as exc:
        raise AutotagError(f"AcoustID lookup failed: {exc}") from exc

    recording, score = _best_recording(response)
    if recording is None:
        return IdentifyResponse(matched=False, candidate=None)

    albums = _album_options(recording.get("releasegroups", []))
    suggested = albums[0] if albums else None

    candidate = TagCandidate(
        title=recording.get("title") or "",
        artist=_join_artists(recording.get("artists", [])),
        album=suggested.title if suggested else None,
        year=suggested.year if suggested else None,
        cover_url=suggested.cover_url if suggested else None,
        recording_id=recording.get("id"),
        score=round(float(score), 3),
        album_options=albums,
    )
    return IdentifyResponse(matched=True, candidate=candidate)


def _best_recording(response: dict[str, Any]) -> tuple[dict[str, Any] | None, float]:
    """The highest-scoring AcoustID recording that actually has artist + title."""
    for result in sorted(
        response.get("results", []), key=lambda r: -r.get("score", 0.0)
    ):
        score = result.get("score", 0.0)
        for recording in result.get("recordings", []):
            if recording.get("title") and recording.get("artists"):
                return recording, score
    return None, 0.0


def _join_artists(artists: list[dict[str, Any]]) -> str:
    return ", ".join(a.get("name", "") for a in artists if a.get("name"))


def _cover_url(release_group_id: str) -> str:
    """Cover Art Archive front-image URL for a release group (may 404)."""
    return f"https://coverartarchive.org/release-group/{release_group_id}/front"


def _album_options(release_groups: list[dict[str, Any]]) -> list[AlbumOption]:
    """Rank candidate albums: earliest plain studio album first, others after.

    A recording can appear on hundreds of release groups, so we (1) split into
    plain studio albums vs everything else, (2) date-lookup only the studio ones
    (few; bounded by `_ALBUM_LIMIT`) and sort them oldest-first — the original
    album — and (3) append a few non-studio groups as extra manual choices.
    """
    studio: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for group in release_groups:
        secondary = set(group.get("secondarytypes", []))
        is_studio = group.get("type") == "Album" and not (secondary & _NON_STUDIO)
        (studio if is_studio else other).append(group)

    options = [
        _make_option(group, is_studio=True, year=_release_group_year(group["id"]))
        for group in studio[:_ALBUM_LIMIT]
    ]
    options.sort(key=lambda o: o.year or "9999")
    options += [
        _make_option(group, is_studio=False, year=None)
        for group in other[:_ALBUM_LIMIT]
    ]
    return options


def _make_option(
    group: dict[str, Any], *, is_studio: bool, year: str | None
) -> AlbumOption:
    return AlbumOption(
        title=group.get("title", ""),
        year=year,
        release_group_id=group["id"],
        primary_type=group.get("type"),
        is_studio_album=is_studio,
        cover_url=_cover_url(group["id"]),
    )


def _release_group_year(release_group_id: str) -> str | None:
    try:
        info = musicbrainzngs.get_release_group_by_id(release_group_id)
    except musicbrainzngs.MusicBrainzError:
        return None
    date = info.get("release-group", {}).get("first-release-date") or ""
    return date[:4] or None


# --- search (manual fallback) ----------------------------------------------

def search(artist: str, title: str) -> SearchResponse:
    """Manual MusicBrainz recording search for when fingerprinting doesn't fit."""
    try:
        result = musicbrainzngs.search_recordings(
            recording=title, artist=artist or None, limit=8
        )
    except musicbrainzngs.MusicBrainzError as exc:
        raise AutotagError(f"MusicBrainz search failed: {exc}") from exc

    candidates: list[TagCandidate] = []
    for recording in result.get("recording-list", []):
        releases = recording.get("release-list", [])
        first = releases[0] if releases else {}
        date = first.get("date", "")
        group_id = first.get("release-group", {}).get("id")
        candidates.append(
            TagCandidate(
                title=recording.get("title", ""),
                artist=_credit_name(recording.get("artist-credit", [])),
                album=first.get("title"),
                year=(date[:4] or None),
                cover_url=_cover_url(group_id) if group_id else None,
                recording_id=recording.get("id"),
                score=_int_or_zero(recording.get("ext:score")) / 100,
            )
        )
    return SearchResponse(results=candidates)


def _credit_name(artist_credit: list[Any]) -> str:
    return "".join(
        part["artist"]["name"] if isinstance(part, dict) else part
        for part in artist_credit
    )


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# --- apply -----------------------------------------------------------------

def apply(request: ApplyRequest, path: Path) -> ApplyResponse:
    """Write the chosen tags + cover art into the file."""
    cover = _fetch_cover(request.cover_url) if request.cover_url else None
    tags = {
        "title": request.title,
        "artist": request.artist,
        "album": request.album,
        "date": request.year,
        "tracknumber": request.track_number,
    }
    embedded = _write_tags(path, tags, cover)
    return ApplyResponse(ok=True, embedded_cover=embedded)


def _fetch_cover(url: str) -> tuple[bytes, str] | None:
    """Download cover art bytes + content-type (None on any failure)."""
    try:
        req = Request(url, headers={"User-Agent": _USER_AGENT})  # noqa: S310 — https CAA url
        with urlopen(req, timeout=15) as resp:  # noqa: S310
            data = resp.read()
            return data, (resp.headers.get_content_type() or "image/jpeg")
    except (URLError, OSError):
        return None


def _write_tags(
    path: Path, tags: dict[str, Any], cover: tuple[bytes, str] | None
) -> bool:
    """Dispatch to the per-format writer; returns whether a cover was embedded."""
    ext = path.suffix.lower()
    if ext == ".mp3":
        return _write_mp3(path, tags, cover)
    if ext in (".m4a", ".mp4", ".m4b"):
        return _write_mp4(path, tags, cover)
    if ext == ".flac":
        return _write_flac(path, tags, cover)
    return _write_generic(path, tags)  # opus/ogg/wav: text only, no cover frame


def _write_mp3(path: Path, tags: dict[str, Any], cover: tuple[bytes, str] | None) -> bool:
    try:
        audio = ID3(path)
    except ID3NoHeaderError:
        audio = ID3()
    frames = {"title": TIT2, "artist": TPE1, "album": TALB, "date": TDRC}
    for key, frame in frames.items():
        if tags.get(key):
            audio.setall(frame.__name__, [frame(encoding=3, text=str(tags[key]))])
    if tags.get("tracknumber"):
        audio.setall("TRCK", [TRCK(encoding=3, text=str(tags["tracknumber"]))])
    embedded = False
    if cover:
        data, ctype = cover
        audio.delall("APIC")
        audio.add(APIC(encoding=3, mime=ctype, type=3, desc="Cover", data=data))
        embedded = True
    audio.save(path)
    return embedded


def _write_mp4(path: Path, tags: dict[str, Any], cover: tuple[bytes, str] | None) -> bool:
    audio = MP4(path)
    mapping = {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb", "date": "\xa9day"}
    for key, atom in mapping.items():
        if tags.get(key):
            audio[atom] = [str(tags[key])]
    if tags.get("tracknumber"):
        audio["trkn"] = [(int(tags["tracknumber"]), 0)]
    embedded = False
    if cover:
        data, ctype = cover
        fmt = MP4Cover.FORMAT_PNG if "png" in ctype else MP4Cover.FORMAT_JPEG
        audio["covr"] = [MP4Cover(data, imageformat=fmt)]
        embedded = True
    audio.save()
    return embedded


def _write_flac(path: Path, tags: dict[str, Any], cover: tuple[bytes, str] | None) -> bool:
    audio = FLAC(path)
    for key in ("title", "artist", "album", "date", "tracknumber"):
        if tags.get(key):
            audio[key] = str(tags[key])
    embedded = False
    if cover:
        data, ctype = cover
        picture = Picture()
        picture.type = 3  # front cover
        picture.mime = ctype
        picture.data = data
        audio.clear_pictures()
        audio.add_picture(picture)
        embedded = True
    audio.save()
    return embedded


def _write_generic(path: Path, tags: dict[str, Any]) -> bool:
    """Best-effort text tags for opus/ogg/wav via mutagen's Easy interface."""
    audio = mutagen.File(path, easy=True)
    if audio is None:
        raise AutotagError("Unsupported audio format for tagging.")
    for key in ("title", "artist", "album", "date", "tracknumber"):
        if tags.get(key):
            audio[key] = str(tags[key])
    audio.save()
    return False
