"""Audio auto-tagging via Apple Music (iTunes), Deezer or MusicBrainz.

`identify()` searches the catalogue for the file's "Artist - Title" (parsed from
its filename); `search()` is the manual version. Neither writes anything —
`apply()` writes the chosen tags + cover into the file with mutagen.

The catalogue source is user-selectable (`settings.autotag_source`), all free and
key-less: Apple Music (iTunes Search API), Deezer, or MusicBrainz (with cover art
from the Cover Art Archive). Deezer and MusicBrainz reach recent or niche
releases the iTunes Search API hasn't indexed yet; MusicBrainz is rate-limited to
~1 request/second, so it's slower for large playlist batches.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TDRC, TIT2, TPE1, TRCK
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE

from app.core.config import settings
from app.models.autotag import (
    ApplyRequest,
    ApplyResponse,
    CandidateList,
    TagCandidate,
)

_USER_AGENT = f"Yoink/{settings.app_version} (https://github.com/ayozetr/yoink-app)"
_ITUNES_URL = "https://itunes.apple.com/search"
_DEEZER_URL = "https://api.deezer.com/search"
_MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording"
_COVERART_URL = "https://coverartarchive.org/release"


class AutotagError(RuntimeError):
    """Raised for any auto-tagging failure surfaced to the client."""


# --- identify / search -----------------------------------------------------

def identify(path: Path) -> CandidateList:
    """Catalogue matches for a downloaded file, keyed on its filename."""
    artist, title = guess_from_filename(path.name)
    results = _search(artist, title) if title else []
    return CandidateList(results=results)


def search(artist: str, title: str) -> CandidateList:
    """Manual catalogue search."""
    return CandidateList(results=_search(artist, title))


def _search(artist: str, title: str) -> list[TagCandidate]:
    """Search the selected catalogue (auto / Apple Music / Deezer / MusicBrainz)."""
    source = settings.autotag_source
    if source == "auto":
        return _auto_search(artist, title)
    if source == "deezer":
        return _deezer_search(artist, title)
    if source == "musicbrainz":
        return _musicbrainz_search(artist, title)
    return _itunes_search(artist, title)


def _auto_search(artist: str, title: str) -> list[TagCandidate]:
    """Try each catalogue in turn, returning the first non-empty match.

    Apple Music and Deezer go first (fast, hi-res covers); MusicBrainz last
    (broad coverage but rate-limited). A source that errors (network / rate
    limit) is treated as "no match" so the next source is still tried.
    """
    for source in (_itunes_search, _deezer_search, _musicbrainz_search):
        try:
            results = source(artist, title)
        except AutotagError:
            continue
        if results:
            return results
    return []


def _itunes_search(artist: str, title: str, limit: int = 8) -> list[TagCandidate]:
    term = f"{artist} {title}".strip()
    if not term:
        return []
    query = urlencode({"term": term, "entity": "song", "limit": limit})
    try:
        request = Request(  # noqa: S310 — fixed https host
            f"{_ITUNES_URL}?{query}", headers={"User-Agent": _USER_AGENT}
        )
        with urlopen(request, timeout=15) as response:  # noqa: S310
            data = json.loads(response.read())
    except (URLError, OSError, ValueError) as exc:
        raise AutotagError(f"Apple Music search failed: {exc}") from exc

    candidates: list[TagCandidate] = []
    for item in data.get("results", []):
        artwork = item.get("artworkUrl100") or ""
        date = item.get("releaseDate") or ""
        candidates.append(
            TagCandidate(
                title=item.get("trackName", ""),
                artist=item.get("artistName", ""),
                album=_clean_album(item.get("collectionName")),
                year=(date[:4] or None),
                track_number=item.get("trackNumber"),
                # bump the 100px thumb to a 1000px cover
                cover_url=artwork.replace("100x100bb", "1000x1000bb") or None,
            )
        )
    return candidates


def _deezer_search(artist: str, title: str, limit: int = 8) -> list[TagCandidate]:
    term = f"{artist} {title}".strip()
    if not term:
        return []
    query = urlencode({"q": term, "limit": limit})
    try:
        request = Request(  # noqa: S310 — fixed https host
            f"{_DEEZER_URL}?{query}", headers={"User-Agent": _USER_AGENT}
        )
        with urlopen(request, timeout=15) as response:  # noqa: S310
            data = json.loads(response.read())
    except (URLError, OSError, ValueError) as exc:
        raise AutotagError(f"Deezer search failed: {exc}") from exc

    candidates: list[TagCandidate] = []
    for item in data.get("data", []):
        album = item.get("album") or {}
        performer = item.get("artist") or {}
        candidates.append(
            TagCandidate(
                title=item.get("title", ""),
                artist=performer.get("name", ""),
                album=album.get("title") or None,
                # Deezer's /search returns no release date or track number.
                year=None,
                track_number=None,
                cover_url=album.get("cover_xl") or album.get("cover_big") or None,
            )
        )
    return candidates


def _mb_escape(value: str) -> str:
    """Escape Lucene specials so the query value matches literally."""
    return re.sub(r'(["\\])', r"\\\1", value)


def _musicbrainz_search(artist: str, title: str, limit: int = 8) -> list[TagCandidate]:
    if not title.strip():
        return []
    # Lucene query; quote the values so multi-word names match as phrases.
    terms = [f'recording:"{_mb_escape(title)}"']
    if artist.strip():
        terms.insert(0, f'artist:"{_mb_escape(artist)}"')
    query = urlencode({"query": " AND ".join(terms), "fmt": "json", "limit": limit})
    try:
        request = Request(  # noqa: S310 — fixed https host
            f"{_MUSICBRAINZ_URL}?{query}", headers={"User-Agent": _USER_AGENT}
        )
        with urlopen(request, timeout=15) as response:  # noqa: S310
            data = json.loads(response.read())
    except (URLError, OSError, ValueError) as exc:
        raise AutotagError(f"MusicBrainz search failed: {exc}") from exc

    candidates: list[TagCandidate] = []
    for rec in data.get("recordings", []):
        credit = rec.get("artist-credit") or []
        name = "".join(c.get("name", "") + (c.get("joinphrase") or "") for c in credit)
        release = (rec.get("releases") or [{}])[0]
        mbid = release.get("id")
        date = release.get("date") or ""
        candidates.append(
            TagCandidate(
                title=rec.get("title", ""),
                artist=name,
                album=release.get("title") or None,
                year=(date[:4] or None),
                track_number=None,
                # Cover Art Archive serves the front cover by release MBID — it
                # 307-redirects to the image, or 404s when there's none (the UI
                # then falls back to a placeholder).
                cover_url=f"{_COVERART_URL}/{mbid}/front-500" if mbid else None,
            )
        )
    return candidates


def _clean_album(name: str | None) -> str | None:
    """Drop Apple's ' - Single' / ' - EP' suffixes from a collection name."""
    if not name:
        return None
    return re.sub(r"\s*-\s*(Single|EP)$", "", name).strip() or None


_FILENAME_TAGS = re.compile(
    r"\s*[([][^)\]]*?"
    r"\b(?:official|video|audio|lyrics?|visualizer|visualiser|hd|4k|mv|prod)\b"
    r"[^)\]]*[)\]]",
    re.IGNORECASE,
)


# A trailing "feat./ft./featuring …" (bracketed or not) and stray emoji muddy
# the catalogue query, so they're dropped from the parsed artist/title.
_FEAT = re.compile(
    r"\s*[([]?\s*\b(?:feat|ft|featuring)\b\.?\s+[^)\]]+[)\]]?\s*$", re.IGNORECASE
)
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff"
    "\U00002190-\U000021ff\U00002300-\U000023ff\U0000fe00-\U0000fe0f]+"
)


# Trailing un-bracketed YouTube noise — "| VIDEO", "- Official Video",
# "Music Video", "Audio", "Visualizer", "MV", "HD/4K"… — muddies the catalogue
# query. Only matched after a separator (|/-) or a qualifier word, so legit
# titles ending in "Video"/"Audio" (e.g. "Video Games") are left untouched.
_TRAILING_NOISE = re.compile(
    r"\s*(?:"
    r"[|\-–—]\s*(?:official\s+|full\s+|music\s+|lyrics?\s+)*"
    r"|(?:official\s+|full\s+|music\s+|lyrics?\s+)+"
    r")"
    r"(?:video|audio|visualizer|visualiser|mv|hd|4k|hq)\b\s*$",
    re.IGNORECASE,
)


def _strip_noise(text: str) -> str:
    text = _EMOJI.sub("", text)
    text = _FEAT.sub("", text)
    # Peel off stacked trailing noise ("… | Official Video | HD").
    prev = None
    while prev != text:
        prev = text
        text = _TRAILING_NOISE.sub("", text).strip()
    return re.sub(r"\s{2,}", " ", text).strip()


def guess_from_filename(name: str) -> tuple[str, str]:
    """Best-effort (artist, title) from a download filename.

    Strips the extension, trailing tags like "(Official Video)"/"(prod. …)", a
    trailing "feat. …" and stray emoji, then splits on the first " - ". Returns
    ("", base) when there's no dash.
    """
    base = re.sub(r"\.[^.]+$", "", name)
    base = _FILENAME_TAGS.sub("", base).strip()
    match = re.match(r"^(.+?)\s[-–—]\s(.+)$", base)
    if match:
        return _strip_noise(match.group(1)), _strip_noise(match.group(2))
    return "", _strip_noise(base)


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
    try:
        embedded = _write_tags(path, tags, cover)
    except (mutagen.MutagenError, ValueError, KeyError, TypeError) as exc:
        # Corrupt / mistyped / partial audio file, or a format mutagen can't tag
        # cleanly: surface as a clean 422 rather than an unhandled 500.
        raise AutotagError(f"Could not write tags to the file: {exc}") from exc
    return ApplyResponse(ok=True, embedded_cover=embedded)


def extract_cover(path: Path) -> tuple[bytes, str] | None:
    """Read embedded cover art (bytes, mime) from an audio file, or None."""
    ext = path.suffix.lower()
    try:
        if ext in (".mp3", ".wav"):
            for frame in ID3(path).getall("APIC"):
                return frame.data, frame.mime or "image/jpeg"
        elif ext in (".m4a", ".mp4", ".m4b"):
            covers = (MP4(path).tags or {}).get("covr")
            if covers:
                is_png = covers[0].imageformat == MP4Cover.FORMAT_PNG
                return bytes(covers[0]), "image/png" if is_png else "image/jpeg"
        elif ext == ".flac":
            for pic in FLAC(path).pictures:
                return pic.data, pic.mime or "image/jpeg"
        else:
            audio = mutagen.File(path)
            pics = getattr(audio, "pictures", None) if audio else None
            if pics:
                return pics[0].data, pics[0].mime or "image/jpeg"
    except (mutagen.MutagenError, ID3NoHeaderError, OSError, ValueError):
        return None
    return None


def _fetch_cover(url: str) -> tuple[bytes, str] | None:
    """Download cover art bytes + content-type (None on any failure)."""
    # Only http(s): urlopen also honors file:// / ftp://, so an attacker-supplied
    # cover_url could otherwise read a local file or hit an internal host (SSRF).
    if urlparse(url).scheme not in ("https", "http"):
        return None
    try:
        request = Request(url, headers={"User-Agent": _USER_AGENT})  # noqa: S310 — http(s) art url
        with urlopen(request, timeout=15) as resp:  # noqa: S310
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
    if ext == ".wav":
        return _write_wav(path, tags)
    return _write_generic(path, tags)  # opus/ogg: text only, no cover frame


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


def _write_wav(path: Path, tags: dict[str, Any]) -> bool:
    """Text tags for WAV via its ID3 chunk.

    mutagen's Easy interface rejects plain strings for WAVE (it wants ID3 frame
    instances, which raised an unhandled TypeError -> 500), and WAV has no
    reliable cover frame, so write the text frames directly and skip the cover.
    """
    audio = WAVE(path)
    if audio.tags is None:
        audio.add_tags()
    frames = {"title": TIT2, "artist": TPE1, "album": TALB, "date": TDRC}
    for key, frame in frames.items():
        if tags.get(key):
            audio.tags.setall(frame.__name__, [frame(encoding=3, text=str(tags[key]))])
    if tags.get("tracknumber"):
        audio.tags.setall("TRCK", [TRCK(encoding=3, text=str(tags["tracknumber"]))])
    audio.save()
    return False


def _write_generic(path: Path, tags: dict[str, Any]) -> bool:
    """Best-effort text tags for opus/ogg via mutagen's Easy interface."""
    audio = mutagen.File(path, easy=True)
    if audio is None:
        raise AutotagError("Unsupported audio format for tagging.")
    for key in ("title", "artist", "album", "date", "tracknumber"):
        if tags.get(key):
            audio[key] = str(tags[key])
    audio.save()
    return False
