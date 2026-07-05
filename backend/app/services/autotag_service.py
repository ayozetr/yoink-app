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
import locale
import logging
import os
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC,
    ID3,
    ID3NoHeaderError,
    TALB,
    TDRC,
    TIT2,
    TPE1,
    TRCK,
    USLT,
)
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE

from yt_dlp.utils import sanitize_filename

from app.core.config import settings
from app.core.ffmpeg import ffmpeg_path
from app.core.safe_http import SSL_CONTEXT, SafeHTTPError, fetch_public
from app.services import nfo
from app.services.lyrics import Lyrics, fetch_lyrics
from app.models.autotag import (
    ApplyRequest,
    ApplyResponse,
    CandidateList,
    LyricsRequest,
    LyricsResult,
    TagCandidate,
)

logger = logging.getLogger(__name__)

_USER_AGENT = f"Yoink/{settings.app_version} (https://github.com/ayozetr/yoink-app)"
_ITUNES_URL = "https://itunes.apple.com/search"
_DEEZER_URL = "https://api.deezer.com/search"
_MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording"
_COVERART_URL = "https://coverartarchive.org/release"
# Cap catalogue JSON reads so a huge/streamed body can't exhaust memory.
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class AutotagError(RuntimeError):
    """Raised for any auto-tagging failure surfaced to the client."""


# --- identify / search -----------------------------------------------------

def identify(path: Path) -> CandidateList:
    """Catalogue matches for a downloaded file, keyed on its filename."""
    artist, title = guess_from_filename(path.name)
    results = _search(artist, title) if title else []
    # Some channels title videos "Song - Artist" (e.g. an artist's own channel:
    # "Punto G - Quevedo"), which guess_from_filename reads backwards. When a
    # dash-split found nothing, retry with artist/title swapped before giving up.
    if not results and artist and title:
        results = _search(title, artist)
    return CandidateList(results=results)


def search(artist: str, title: str) -> CandidateList:
    """Manual catalogue search."""
    return CandidateList(results=_search(artist, title))


def _norm_for_match(text: str) -> str:
    """Lower-case, strip accents + bracketed/parenthetical noise + punctuation."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", text)  # drop "(feat …)" / "[Remix]"
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _relevant(cands: list[TagCandidate], title: str) -> list[TagCandidate]:
    """Drop catalogue hits whose title shares *nothing* with the query title.

    Fuzzy APIs (Apple Music especially) return an unrelated "closest" song when
    they have no real match — e.g. searching a track that isn't in the store gives
    a random hit that then masquerades as a candidate. Conservative on purpose:
    a hit is kept if it shares any 2+ char token, or one title contains the other,
    so only genuinely-unrelated results are removed (a real match always overlaps).
    """
    query = _norm_for_match(title)
    qtok = {t for t in query.split() if len(t) >= 2}
    if not qtok:
        return cands  # nothing meaningful to compare against → keep everything
    kept: list[TagCandidate] = []
    for cand in cands:
        norm = _norm_for_match(cand.title)
        ctok = {t for t in norm.split() if len(t) >= 2}
        if not ctok or (qtok & ctok) or query in norm or norm in query:
            kept.append(cand)
    return kept


def _search(artist: str, title: str) -> list[TagCandidate]:
    """Search the selected catalogue (auto / Apple Music / Deezer / MusicBrainz),
    ranked so the cleanest match for the query comes first, with clearly-unrelated
    fuzzy hits dropped."""
    source = settings.autotag_source
    if source == "auto":
        results = _auto_search(artist, title)
    elif source == "deezer":
        results = _deezer_search(artist, title)
    elif source == "musicbrainz":
        results = _musicbrainz_search(artist, title)
    else:
        results = _itunes_search(artist, title)
    return _rank(_relevant(results, title), artist, title)


_VERSION_EXTRAS = (
    "remix", "version", "live", "edit", "acoustic", "instrumental",
    "sped up", "slowed", "cover", "karaoke",
)


def _rank(
    results: list[TagCandidate], artist: str, title: str
) -> list[TagCandidate]:
    """Order matches so the cleanest version (closest to the query, without an
    added remix / feat / qualifier) comes first. Stable for equal scores, so a
    catalogue's own ordering is preserved within a tie."""
    qt = title.strip().lower()
    qa = artist.strip().lower()

    def score(cand: TagCandidate) -> int:
        ct = cand.title.strip().lower()
        s = 0
        if ct == qt:
            s += 100  # exact title match
        elif qt and qt in ct:
            s += 40  # query is a substring (extra stuff appended)
        for extra in _VERSION_EXTRAS:
            if extra in ct and extra not in qt:
                s -= 25  # a remix/live/… the query didn't ask for
        s -= abs(len(ct) - len(qt)) // 8  # closer length = fewer "(feat …)"/"[…]"
        if qa and qa in cand.artist.strip().lower():
            s += 15  # artist also matches
        return s

    return sorted(results, key=score, reverse=True)


def _auto_search(artist: str, title: str) -> list[TagCandidate]:
    """Combine the fast catalogues (Apple Music + Deezer), deduped.

    Merging matters: a song one catalogue lists but the other doesn't (e.g. an
    original only on Deezer vs a remix only on Apple Music) would be missed if we
    stopped at the first non-empty source. MusicBrainz is a fallback only when
    both fast sources come up empty (broad coverage, but rate-limited). A source
    that errors (network / rate limit) is skipped.
    """
    combined: list[TagCandidate] = []
    seen: set[tuple[str, str]] = set()
    for source in (_itunes_search, _deezer_search):
        try:
            results = source(artist, title)
        except AutotagError:
            continue
        for cand in results:
            key = (cand.artist.strip().lower(), cand.title.strip().lower())
            if key not in seen:
                seen.add(key)
                combined.append(cand)
    if combined:
        return combined
    try:
        return _musicbrainz_search(artist, title)
    except AutotagError:
        return []


def _user_country() -> str | None:
    """Best-effort 2-letter region for the iTunes storefront. Yoink runs on the
    user's own machine, so its locale is their Apple Music region (e.g. ``es_ES``
    -> ``ES``). ``None`` when it can't be determined (falls back to the US store)."""
    candidates = [
        os.environ.get("LC_ALL"),
        os.environ.get("LC_MESSAGES"),
        os.environ.get("LANG"),
    ]
    try:
        candidates.append(locale.getlocale()[0])
    except (ValueError, TypeError):
        pass
    for value in candidates:
        if value and "_" in value:
            region = value.split("_", 1)[1][:2]
            if region.isalpha():
                return region.upper()
    return None


def _apple_stores() -> list[str | None]:
    """Storefronts to query: the user's region first, then iTunes' US default
    (``None`` = no ``country`` param). Querying both is purely additive — it only
    adds regional catalogue (e.g. Spanish releases missing from the US store) and
    never drops a US match, so it can't return fewer results than before."""
    region = _user_country()
    return [region, None] if region and region != "US" else [None]


def _itunes_search_store(
    term: str, limit: int, country: str | None
) -> list[TagCandidate]:
    """One iTunes Search request against a single storefront."""
    params: dict[str, str | int] = {"term": term, "entity": "song", "limit": limit}
    if country:
        params["country"] = country
    try:
        request = Request(  # noqa: S310 — fixed https host
            f"{_ITUNES_URL}?{urlencode(params)}", headers={"User-Agent": _USER_AGENT}
        )
        with urlopen(request, timeout=15, context=SSL_CONTEXT) as response:  # noqa: S310
            data = json.loads(response.read(_MAX_RESPONSE_BYTES))
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


def _itunes_search(artist: str, title: str, limit: int = 8) -> list[TagCandidate]:
    """Apple Music search across the user's storefront + the US default, merged
    and deduped. A track only in a regional store (common for Spanish releases,
    which the US-only default missed) is now found; US results are unaffected."""
    term = f"{artist} {title}".strip()
    if not term:
        return []
    stores = _apple_stores()
    results: list[TagCandidate] = []
    seen: set[tuple[str, str]] = set()
    errors = 0
    for country in stores:
        try:
            found = _itunes_search_store(term, limit, country)
        except AutotagError:
            errors += 1
            continue
        for cand in found:
            key = (cand.artist.strip().lower(), cand.title.strip().lower())
            if key not in seen:
                seen.add(key)
                results.append(cand)
    if errors and errors == len(stores):  # every storefront failed → surface it
        raise AutotagError("Apple Music search failed")
    return results


def _deezer_search(artist: str, title: str, limit: int = 8) -> list[TagCandidate]:
    term = f"{artist} {title}".strip()
    if not term:
        return []
    query = urlencode({"q": term, "limit": limit})
    try:
        request = Request(  # noqa: S310 — fixed https host
            f"{_DEEZER_URL}?{query}", headers={"User-Agent": _USER_AGENT}
        )
        with urlopen(request, timeout=15, context=SSL_CONTEXT) as response:  # noqa: S310
            data = json.loads(response.read(_MAX_RESPONSE_BYTES))
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
        with urlopen(request, timeout=15, context=SSL_CONTEXT) as response:  # noqa: S310
            data = json.loads(response.read(_MAX_RESPONSE_BYTES))
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


# yt-dlp sanitises filesystem-illegal chars in filenames to fullwidth look-alikes
# ("|" → "｜", ":" → "：", "?" → "？", "*" → "＊", "/" → "⧸"…). Map them back so the
# catalogue query matches the real title.
_FULLWIDTH = str.maketrans(
    {
        "＂": '"', "：": ":", "＜": "<", "＞": ">", "？": "?",
        "｜": "|", "＊": "*", "／": "/", "＼": "\\", "⧸": "/", "⧹": "\\",
        # Full-width / CJK brackets used for noise tags ("（Official MV）",
        # "【MV full】") — fold to ASCII so the tag stripper catches them.
        "（": "(", "）": ")", "【": "[", "】": "]",
    }
)


_FILENAME_TAGS = re.compile(
    r"\s*[([][^)\]]*?"
    r"\b(?:official|oficial|officiel|video|v[ií]deo|videoclip|clip|audio"
    r"|lyrics?|letras?|visualizer|visualiser|hd|4k|mv|prod|explicit)\b"
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
# Note the "｜" (U+FF5C, fullwidth pipe): yt-dlp sanitises "|" in filenames to it,
# so a YouTube "Song | VIDEO" lands on disk as "Song ｜ VIDEO".
_TRAILING_NOISE = re.compile(
    r"\s*(?:"
    r"[|｜\-–—]\s*(?:official\s+|oficial\s+|full\s+|music\s+|lyrics?\s+)*"
    r"|(?:official\s+|oficial\s+|full\s+|music\s+|lyrics?\s+)+"
    r")"
    r"(?:video|v[ií]deo|videoclip|audio|visualizer|visualiser|mv|hd|4k|hq)"
    r"(?:\s+oficial)?\b\s*$",  # Spanish puts the qualifier last: "Vídeo Oficial"
    re.IGNORECASE,
)


# Spanish-order "… Vídeo/Videoclip/Audio Oficial" with no separator in front —
# unambiguous noise (no real title ends this way), so strip it even without a
# leading "-"/"|". Kept narrow (requires the trailing "oficial") to stay safe.
_TRAILING_NOISE_ES = re.compile(
    r"\s+(?:v[ií]deo|videoclip|audio)\s+oficial\s*$", re.IGNORECASE
)


def _strip_noise(text: str) -> str:
    text = _EMOJI.sub("", text)
    text = _FEAT.sub("", text)
    # Peel off stacked trailing noise ("… | Official Video | HD").
    prev = None
    while prev != text:
        prev = text
        text = _TRAILING_NOISE.sub("", text).strip()
        text = _TRAILING_NOISE_ES.sub("", text).strip()
        # Bare trailing "M/V" (K-pop), with or without the slash.
        text = re.sub(r"\s*\bm\s*/\s*v\b\s*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s{2,}", " ", text).strip()
    # Quotes wrapping the whole title (K-pop 'TITLE' / "TITLE") aren't part of it.
    return text.strip("\"'`‘’“”").strip()


def guess_from_filename(name: str) -> tuple[str, str]:
    """Best-effort (artist, title) from a download filename.

    Strips the extension, trailing tags like "(Official Video)"/"(prod. …)", a
    trailing "feat. …" and stray emoji, then splits on the first " - ". Returns
    ("", base) when there's no dash.
    """
    base = re.sub(r"\.[^.]+$", "", name)
    base = base.translate(_FULLWIDTH)  # ｜／：？… (yt-dlp sanitised) → ASCII
    base = _FILENAME_TAGS.sub("", base).strip()
    match = re.match(r"^(.+?)\s[-–—]\s(.+)$", base)
    if match:
        # The dash already split artist/title, so a trailing " | …" on the title
        # is a YouTube suffix (album/label/movie), not an "Artist | Title"
        # separator — drop it. Only safe here, with the artist already known.
        title = re.sub(r"\s*[|｜].*$", "", _strip_noise(match.group(2))).strip()
        return _strip_noise(match.group(1)), title or _strip_noise(match.group(2))

    # No "Artist - Title" dash — try a couple of non-Western shapes before
    # giving up and treating the whole thing as a title.
    #
    # K-pop & friends: ``ARTIST 'TITLE'`` / ``ARTIST "TITLE"`` — the quoted run is
    # the title, the text before it the artist. The open-quote must follow a space
    # (not a letter), so a possessive apostrophe ("Destiny's") isn't mistaken for
    # a title quote.
    quoted = re.search(r"(?:^|\s)(['‘\"“])([^'’\"”]{2,})['’\"”]", base)
    if quoted and quoted.start(1) > 0:
        artist = _strip_noise(base[: quoted.start(1)])
        title = _strip_noise(quoted.group(2))
        if artist and title:
            return artist, title

    # Indian / other Asian uploads: ``Title | Movie | Cast | Singers`` — the song
    # leads and the rest is movie/cast/label noise. Two-plus pipes is a strong
    # signal of that shape; a single "A | B" stays put (the pipe might be the
    # artist/title separator), so only take the first segment when there are ≥3.
    parts = base.split("|")
    if len(parts) >= 3:
        first = _strip_noise(parts[0])
        if first:
            return "", first

    return "", _strip_noise(base)


# --- apply -----------------------------------------------------------------

def _lookup_lyrics(path: Path, request: ApplyRequest) -> Lyrics | None:
    """Lyrics for the track from LRCLIB, or None (best-effort, never fatal).

    Probes the file's duration (mutagen) so LRCLIB's exact ``/get`` match can be
    used before falling back to its search.
    """
    try:
        probed = mutagen.File(str(path))
        duration = getattr(probed.info, "length", None) if probed else None
        return fetch_lyrics(
            request.title or "", request.artist or "", request.album, duration
        )
    except Exception as exc:  # noqa: BLE001 — lyrics are best-effort
        logger.warning("Lyrics lookup failed for %s: %s", path.name, exc)
        return None


def _write_lrc_sidecar(media_path: Path, synced: str) -> None:
    """Write a synced ``<name>.lrc`` next to the audio (best-effort)."""
    try:
        media_path.with_suffix(".lrc").write_text(synced, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write .lrc for %s: %s", media_path.name, exc)


def lyrics_preview(request: LyricsRequest) -> LyricsResult:
    """Preview-time lyrics availability for the auto-tag card (no writing)."""
    duration: float | None = None
    if request.path:
        try:
            probed = mutagen.File(request.path)
            duration = getattr(probed.info, "length", None) if probed else None
        except Exception:  # noqa: BLE001 — duration is just a hint
            duration = None
    found = fetch_lyrics(request.title, request.artist, request.album, duration)
    if not found:
        return LyricsResult(found=False)
    return LyricsResult(
        found=bool(found.plain or found.synced or found.instrumental),
        instrumental=found.instrumental,
        has_synced=bool(found.synced),
        plain=found.plain,
    )


def apply(request: ApplyRequest, path: Path) -> ApplyResponse:
    """Write the chosen tags + cover art into the file."""
    cover_url = request.cover_url
    # No source cover (e.g. an Amazon-playlist track, whose embed exposes none) —
    # best-effort lookup on Deezer by artist+title so the file still gets art.
    if not cover_url and request.artist and request.title:
        try:
            hits = _deezer_search(request.artist, request.title, limit=1)
            cover_url = next((c.cover_url for c in hits if c.cover_url), None)
        except AutotagError:
            cover_url = None
    cover = _fetch_cover(cover_url) if cover_url else None
    tags = {
        "title": request.title,
        "artist": request.artist,
        "album": request.album,
        "date": request.year,
        "tracknumber": request.track_number,
    }
    # The card's checkbox (embed_lyrics) overrides the global setting per track.
    want_lyrics = (
        request.embed_lyrics
        if request.embed_lyrics is not None
        else settings.fetch_lyrics
    )
    synced_lyrics: str | None = None
    if want_lyrics and request.title:
        found = _lookup_lyrics(path, request)
        if found:
            if found.plain:
                tags["lyrics"] = found.plain
            # Synced .lrc sidecar (opt-in) for karaoke-capable players.
            if settings.lyrics_lrc and found.synced:
                synced_lyrics = found.synced
    try:
        embedded = _write_tags(path, tags, cover)
    except (mutagen.MutagenError, ValueError, KeyError, TypeError) as exc:
        # Corrupt / mistyped / partial audio file, or a format mutagen can't tag
        # cleanly: surface as a clean 422 rather than an unhandled 500.
        raise AutotagError(f"Could not write tags to the file: {exc}") from exc
    # Only now the tags are written — write the .lrc next to the tagged file so a
    # failed tag-write doesn't leave an orphaned sidecar by an untagged file.
    if synced_lyrics:
        _write_lrc_sidecar(path, synced_lyrics)
    # Rewrite the .nfo (if enabled) with the *tagged* metadata, so it matches the
    # file's tags instead of the raw YouTube uploader the download-time one had.
    if settings.nfo_sidecars:
        nfo.write(
            path,
            nfo.build(
                kind="audio",
                title=request.title or "",
                artist=request.artist or "",
                album=request.album or "",
                year=request.year or "",
                thumb=cover_url or "",
            ),
        )
    return ApplyResponse(ok=True, embedded_cover=embedded)


def rename_to_tagged(path: Path, new_title: str) -> Path:
    """Rename the audio file — and any sidecars sharing its name (``.nfo``/``.lrc``)
    — to the auto-tag name (``"Artist - Title"``), keeping each extension.

    Returns the new audio path, or the original when the rename can't happen (an
    empty/unchanged name, or a *different* file already owns the target name).
    Best-effort: filesystem errors leave everything as-is instead of raising.
    """
    new_stem = sanitize_filename(new_title, restricted=False).strip()
    if not new_stem or new_stem == path.stem:
        return path
    target = path.with_name(new_stem + path.suffix)
    if target.exists():
        return path  # don't clobber a different file that already has this name
    prefix = path.stem + "."
    try:
        movable = [
            p for p in path.parent.iterdir() if p.is_file() and p.name.startswith(prefix)
        ]
        for sib in movable:
            sib.rename(sib.with_name(new_stem + sib.name[len(path.stem) :]))
    except OSError:
        return path
    return target


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


def _webp_to_jpeg(data: bytes) -> bytes | None:
    """Convert WebP image bytes to JPEG via ffmpeg (best-effort).

    Returns the JPEG bytes, or None if ffmpeg is unavailable or the conversion
    fails. Uses stdin/stdout pipes — no temp files touch disk.
    """
    # ffmpeg_path() resolves the bundled binary (with .exe on Windows) or the
    # one on PATH — a bare "ffmpeg"/"ffmpeg.exe" that subprocess finds via PATH.
    try:
        result = subprocess.run(  # noqa: S603 — trusted binary path
            [ffmpeg_path(), "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0",
             "-f", "mjpeg", "-q:v", "2", "pipe:1"],
            input=data, capture_output=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _fetch_cover(url: str) -> tuple[bytes, str] | None:
    """Download cover art bytes + content-type (None on any failure).

    The ``cover_url`` is client-supplied, so this goes through the SSRF-safe
    fetcher: only public http(s) hosts, the connection pinned to the validated
    IP, redirects re-validated, and the read capped — the same guard as the
    thumbnail proxy. A plain urlopen here was an internal-host read/probe
    primitive (the bytes get embedded and are re-servable via /api/cover).
    """
    try:
        data, content_type = fetch_public(url, headers={"User-Agent": _USER_AGENT})
    except SafeHTTPError:
        return None
    # An empty body would embed as a zero-byte "cover" (embedded_cover=True) — a
    # broken image; treat it as no cover at all.
    if not data:
        return None
    # Tag writers want an image mime; fall back to jpeg if the server was vague.
    mime = content_type if content_type.startswith("image/") else "image/jpeg"
    # WebP is unsupported as embedded cover art by Windows and most players;
    # detect by magic bytes (RIFF....WEBP) and convert to JPEG via ffmpeg.
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        converted = _webp_to_jpeg(data)
        if converted is not None:
            return converted, "image/jpeg"
        logger.warning(
            "WebP cover from %s could not be converted; embedding as-is", url
        )
    return data, mime


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
    if tags.get("lyrics"):
        audio.setall(
            "USLT", [USLT(encoding=3, lang="eng", desc="", text=str(tags["lyrics"]))]
        )
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
    if tags.get("lyrics"):
        audio["\xa9lyr"] = [str(tags["lyrics"])]
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
    if tags.get("lyrics"):
        audio["lyrics"] = str(tags["lyrics"])
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
    if tags.get("lyrics"):
        audio.tags.setall(
            "USLT", [USLT(encoding=3, lang="eng", desc="", text=str(tags["lyrics"]))]
        )
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
    if tags.get("lyrics"):
        audio["lyrics"] = str(tags["lyrics"])
    audio.save()
    return False
