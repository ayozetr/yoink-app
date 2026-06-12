"""Keyless music import from Spotify / Deezer / Apple Music / Tidal / Amazon.

Each source resolves a track/album/playlist URL into a common
:class:`MusicImportInfo` (no API keys — public APIs for Deezer/Apple, public
embed scrapes for Spotify/Tidal/Amazon). The audio is never taken from the
service: :func:`find_youtube_match` finds the best YouTube match per track with
the spotDL-ported ranker, and the caller downloads + tags it with this metadata.

See docs/spotify-import.md for the design.
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.core.ytdlp_options import network_options
from app.models.music import MusicImportInfo, MusicKind, MusicSource, MusicTrack
from app.services.matching import best_match

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_SEARCH_N = 5  # YouTube candidates to rank per track


class MusicImportError(RuntimeError):
    """Raised when a music URL can't be parsed or its source can't be read."""


# --- HTTP helpers ----------------------------------------------------------

def _get(url: str, headers: dict[str, str] | None = None) -> str:
    h = {"User-Agent": _USER_AGENT}
    if headers:
        h.update(headers)
    try:
        with urlopen(Request(url, headers=h), timeout=15) as resp:  # noqa: S310
            return resp.read().decode("utf-8", "replace")
    except (URLError, OSError) as exc:
        raise MusicImportError(f"Could not reach the music service: {exc}") from exc


def _get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    try:
        return json.loads(_get(url, headers))
    except ValueError as exc:
        raise MusicImportError("Unexpected response from the music service.") from exc


def _mmss_to_ms(text: str) -> int | None:
    parts = text.strip().split(":")
    if not all(p.isdigit() for p in parts):
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + int(p)
    return secs * 1000


# --- source detection ------------------------------------------------------

# Each entry: source -> (regex with (kind, id) groups). Spotify/Apple add extras.
_SPOTIFY_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z-]+/)?|spotify:)"
    r"(track|album|playlist)[/:]([A-Za-z0-9]+)",
    re.IGNORECASE,
)
_DEEZER_RE = re.compile(
    r"(?:deezer\.com|deezer\.page\.link)/(?:[a-z]{2}/)?(track|album|playlist)/(\d+)",
    re.IGNORECASE,
)
_APPLE_RE = re.compile(
    r"music\.apple\.com/(?:([a-z]{2})/)?(album|song|playlist)/[^/]+/(pl\.[\w-]+|\d+)",
    re.IGNORECASE,
)
_APPLE_TRACK_RE = re.compile(r"[?&]i=(\d+)")
_TIDAL_RE = re.compile(
    r"(?:tidal\.com|embed\.tidal\.com|listen\.tidal\.com)/(?:browse/)?"
    r"(track|album|playlist)s?/([\w-]+)",
    re.IGNORECASE,
)
_AMAZON_RE = re.compile(
    r"music\.amazon\.[a-z.]+/(albums|tracks|playlists|user-playlists)/([A-Z0-9.]+)",
    re.IGNORECASE,
)

_DETECTORS: list[tuple[MusicSource, re.Pattern[str]]] = [
    ("spotify", _SPOTIFY_RE),
    ("deezer", _DEEZER_RE),
    ("apple", _APPLE_RE),
    ("tidal", _TIDAL_RE),
    ("amazon", _AMAZON_RE),
]


def detect_source(url: str) -> MusicSource | None:
    for source, pattern in _DETECTORS:
        if pattern.search(url):
            return source
    return None


def is_music_url(url: str) -> bool:
    return detect_source(url) is not None


def resolve(url: str) -> MusicImportInfo:
    """Resolve any supported music URL into a tracklist (keyless)."""
    source = detect_source(url)
    if source == "spotify":
        return _resolve_spotify(url)
    if source == "deezer":
        return _resolve_deezer(url)
    if source == "apple":
        return _resolve_apple(url)
    if source == "tidal":
        return _resolve_tidal(url)
    if source == "amazon":
        return _resolve_amazon(url)
    raise MusicImportError("Not a recognised music-service URL.")


# --- YouTube match (shared) ------------------------------------------------

def find_youtube_match(track: MusicTrack) -> str | None:
    """Search YouTube for a track and return the best-ranked video URL (or None)."""
    query = f"{track.artists} {track.title}".strip()
    if not query:
        return None
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        **network_options(),
    }
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"ytsearch{_SEARCH_N}:{query}", download=False)
    except DownloadError:
        return None
    entries = (info or {}).get("entries") or []
    candidates = [
        {
            "title": e.get("title"),
            "channel": e.get("channel") or e.get("uploader"),
            "duration": e.get("duration"),
            "id": e.get("id"),
            "url": e.get("url") or e.get("webpage_url"),
        }
        for e in entries
        if isinstance(e, dict)
    ]
    best = best_match(
        track_title=track.title,
        track_artists=track.artists,
        track_duration_ms=track.duration_ms,
        candidates=candidates,
    )
    if not best:
        return None
    if best.get("id"):
        return f"https://www.youtube.com/watch?v={best['id']}"
    return best.get("url")


# --- Spotify (public embed + anonymous token) ------------------------------

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def _find_key(obj: Any, key: str, depth: int = 0) -> str | None:
    if depth > 7:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and isinstance(v, str) and v:
                return v
            found = _find_key(v, key, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj[:5]:
            found = _find_key(v, key, depth + 1)
            if found:
                return found
    return None


def _sp_cover(entity: dict[str, Any]) -> str | None:
    images = (entity.get("visualIdentity") or {}).get("image") or []
    if images:
        return images[-1].get("url")
    sources = (entity.get("coverArt") or {}).get("sources") or []
    return sources[-1].get("url") if sources else None


def _sp_year(entity: dict[str, Any]) -> str | None:
    rd = entity.get("releaseDate")
    if isinstance(rd, dict):
        rd = rd.get("isoString") or rd.get("year")
    if isinstance(rd, (str, int)):
        text = str(rd)
        return text[:4] if len(text) >= 4 else None
    return None


def _sp_api_tracks(kind: str, sid: str, token: str) -> list[dict[str, Any]] | None:
    base = "playlists" if kind == "playlist" else "albums"
    items: list[dict[str, Any]] = []
    offset = 0
    try:
        while offset < 2000:
            url = f"https://api.spotify.com/v1/{base}/{sid}/tracks?limit=50&offset={offset}"
            page = json.loads(
                _get(url, {"Authorization": f"Bearer {token}"})
            )
            page_items = page.get("items") or []
            items.extend(page_items)
            if not page.get("next") or not page_items:
                break
            offset += len(page_items)
        return items or None
    except (MusicImportError, ValueError):
        return None


def _sp_track_from_api(item: dict[str, Any], kind: str, album_entity: dict[str, Any]) -> MusicTrack | None:
    track = item.get("track") if kind == "playlist" else item
    if not isinstance(track, dict) or not track.get("name"):
        return None
    album = track.get("album") or {}
    images = album.get("images") or []
    if kind == "playlist":
        album_name = album.get("name")
        year = (album.get("release_date") or "")[:4] or None
        cover = images[0].get("url") if images else None
    else:
        album_name = album_entity.get("name")
        year = _sp_year(album_entity)
        cover = _sp_cover(album_entity)
    tid = track.get("id") or ""
    return MusicTrack(
        title=track["name"],
        artists=", ".join(a.get("name", "") for a in track.get("artists", []) if a.get("name")),
        duration_ms=track.get("duration_ms"),
        is_explicit=bool(track.get("explicit")),
        album=album_name,
        year=year,
        cover_url=cover,
        source_url=f"https://open.spotify.com/track/{tid}" if tid else "",
    )


def _resolve_spotify(url: str) -> MusicImportInfo:
    match = _SPOTIFY_RE.search(url)
    if not match:
        raise MusicImportError("Not a recognised Spotify URL.")
    kind, sid = match.group(1).lower(), match.group(2)

    embed = f"https://open.spotify.com/embed/{kind}/{sid}"
    blob = _NEXT_DATA_RE.search(_get(embed))
    if not blob:
        raise MusicImportError("Spotify embed page changed shape.")
    try:
        data = json.loads(blob.group(1))
        entity = data["props"]["pageProps"]["state"]["data"]["entity"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MusicImportError("Could not parse the Spotify metadata.") from exc
    token = _find_key(data, "accessToken")
    cover = _sp_cover(entity)

    if kind == "track":
        track = MusicTrack(
            title=entity.get("name") or entity.get("title") or "",
            artists=", ".join(a.get("name", "") for a in entity.get("artists", []) if a.get("name")),
            duration_ms=entity.get("duration"),
            is_explicit=bool(entity.get("isExplicit")),
            year=_sp_year(entity),
            cover_url=cover,
            source_url=f"https://open.spotify.com/track/{sid}",
        )
        return MusicImportInfo(source="spotify", type="track", name=track.title,
                               subtitle=track.artists, cover_url=cover, tracks=[track])

    api_items = _sp_api_tracks(kind, sid, token) if token else None
    if api_items:
        tracks = [t for t in (_sp_track_from_api(it, kind, entity) for it in api_items) if t]
        truncated = False
    else:
        album_name = entity.get("name") if kind == "album" else None
        album_year = _sp_year(entity) if kind == "album" else None
        tracks = []
        for item in entity.get("trackList") or []:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            uri = item.get("uri", "")
            parts = uri.split(":")
            surl = f"https://open.spotify.com/{parts[1]}/{parts[2]}" if len(parts) == 3 else ""
            tracks.append(MusicTrack(
                title=item.get("title", ""), artists=item.get("subtitle", "") or "",
                duration_ms=item.get("duration"), is_explicit=bool(item.get("isExplicit")),
                album=album_name, year=album_year, cover_url=cover, source_url=surl))
        truncated = len(tracks) >= 100

    subtitle = entity.get("subtitle") if kind == "playlist" else (tracks[0].artists if tracks else None)
    return MusicImportInfo(source="spotify", type=kind,
                           name=entity.get("name") or entity.get("title") or "",
                           subtitle=subtitle, cover_url=cover, tracks=tracks, truncated=truncated)


# --- Deezer (public API, keyless) ------------------------------------------

def _deezer_track(item: dict[str, Any], album_name: str | None, year: str | None,
                  cover: str | None) -> MusicTrack | None:
    if not item.get("title"):
        return None
    alb = item.get("album") or {}
    dur = item.get("duration")  # seconds
    return MusicTrack(
        title=item.get("title", ""),
        artists=(item.get("artist") or {}).get("name", ""),
        duration_ms=int(dur) * 1000 if dur else None,
        is_explicit=bool(item.get("explicit_lyrics")),
        album=album_name or alb.get("title"),
        year=year,
        cover_url=cover or alb.get("cover_xl") or alb.get("cover_big"),
        source_url=item.get("link") or "",
    )


def _resolve_deezer(url: str) -> MusicImportInfo:
    match = _DEEZER_RE.search(url)
    if not match:
        raise MusicImportError("Not a recognised Deezer URL.")
    kind, did = match.group(1).lower(), match.group(2)
    data = _get_json(f"https://api.deezer.com/{kind}/{did}")
    if not isinstance(data, dict) or data.get("error"):
        raise MusicImportError("Deezer couldn't resolve that URL.")

    cover = data.get("cover_xl") or data.get("picture_xl") or data.get("cover_big")
    if kind == "track":
        alb = data.get("album") or {}
        cover = cover or alb.get("cover_xl") or alb.get("cover_big")
        track = _deezer_track(data, alb.get("title"),
                              (data.get("release_date") or "")[:4] or None, cover)
        if not track:
            raise MusicImportError("Deezer returned no track.")
        return MusicImportInfo(source="deezer", type="track", name=track.title,
                               subtitle=track.artists, cover_url=cover, tracks=[track])

    name = data.get("title", "")
    album_name = name if kind == "album" else None
    album_year = (data.get("release_date") or "")[:4] or None if kind == "album" else None
    subtitle = ((data.get("artist") or {}).get("name") if kind == "album"
                else (data.get("creator") or {}).get("name"))
    items = (data.get("tracks") or {}).get("data") or []
    nxt = (data.get("tracks") or {}).get("next")
    while nxt and len(items) < 2000:
        page = _get_json(nxt)
        items += page.get("data") or []
        nxt = page.get("next")
    tracks = [t for t in (_deezer_track(it, album_name, album_year, cover) for it in items) if t]
    return MusicImportInfo(source="deezer", type=kind, name=name, subtitle=subtitle,
                           cover_url=cover, tracks=tracks)


# --- Apple Music (iTunes Lookup API, keyless; albums/tracks only) ----------

def _apple_track(item: dict[str, Any], album_name: str | None) -> MusicTrack | None:
    if not item.get("trackName"):
        return None
    art = (item.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
    date = item.get("releaseDate") or ""
    return MusicTrack(
        title=item.get("trackName", ""),
        artists=item.get("artistName", ""),
        duration_ms=item.get("trackTimeMillis"),
        is_explicit=item.get("trackExplicitness") == "explicit",
        album=album_name or item.get("collectionName"),
        year=date[:4] or None,
        cover_url=art or None,
        source_url=item.get("trackViewUrl") or "",
    )


def _resolve_apple(url: str) -> MusicImportInfo:
    match = _APPLE_RE.search(url)
    if not match:
        raise MusicImportError("Not a recognised Apple Music URL.")
    country = (match.group(1) or "us").lower()
    kind, apple_id = match.group(2).lower(), match.group(3)
    if kind == "playlist":
        raise MusicImportError(
            "Apple Music playlists need credentials; only albums and tracks work keyless."
        )

    track_m = _APPLE_TRACK_RE.search(url)
    if track_m:  # a single track inside an album URL (?i=trackId)
        data = _get_json(
            f"https://itunes.apple.com/lookup?id={track_m.group(1)}&country={country}"
        )
        results = data.get("results") or []
        item = next((r for r in results if r.get("wrapperType") == "track"), None)
        track = _apple_track(item, None) if item else None
        if not track:
            raise MusicImportError("Apple Music returned no track.")
        return MusicImportInfo(source="apple", type="track", name=track.title,
                               subtitle=track.artists, cover_url=track.cover_url, tracks=[track])

    data = _get_json(
        f"https://itunes.apple.com/lookup?id={apple_id}&country={country}&entity=song"
    )
    results = data.get("results") or []
    collection = next((r for r in results if r.get("wrapperType") == "collection"), {})
    name = collection.get("collectionName", "")
    artist = collection.get("artistName")
    cover = (collection.get("artworkUrl100") or "").replace("100x100bb", "600x600bb") or None
    songs = [r for r in results if r.get("wrapperType") == "track"]
    tracks = [t for t in (_apple_track(s, name) for s in songs) if t]
    return MusicImportInfo(source="apple", type="album", name=name, subtitle=artist,
                           cover_url=cover, tracks=tracks)


# --- Tidal (public embed scrape) -------------------------------------------

_TIDAL_ITEM_RE = re.compile(r"<list-item\b[^>]*>(.*?)</list-item>", re.DOTALL)
_TIDAL_SLOT_RE = lambda slot: re.compile(  # noqa: E731
    rf'<(?:span|time) slot="{slot}"[^>]*>(.*?)</(?:span|time)>', re.DOTALL
)
_TIDAL_TITLE = _TIDAL_SLOT_RE("title")
_TIDAL_ARTIST = _TIDAL_SLOT_RE("artist")
_TIDAL_DURATION = _TIDAL_SLOT_RE("duration")
_OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)"')


def _resolve_tidal(url: str) -> MusicImportInfo:
    match = _TIDAL_RE.search(url)
    if not match:
        raise MusicImportError("Not a recognised Tidal URL.")
    kind, tid = match.group(1).lower(), match.group(2)
    html = _get(f"https://embed.tidal.com/{kind}s/{tid}?countryCode=US")

    # The embed carries the tracklist but no og tags; the regular page has the
    # album/playlist title + artist ("Artist - Album") + cover.
    try:
        page = _get(f"https://tidal.com/{kind}/{tid}")
    except MusicImportError:
        page = ""
    og = _OG_TITLE_RE.search(page)
    og_artist, og_name = None, None
    if og:
        text = unescape(og.group(1))
        if " - " in text:
            og_artist, og_name = (s.strip() for s in text.split(" - ", 1))
        else:
            og_name = text.strip()

    cover_m = re.search(r'<meta property="og:image" content="([^"]*)"', page)
    cover = unescape(cover_m.group(1)) if cover_m else None

    tracks: list[MusicTrack] = []
    for block in _TIDAL_ITEM_RE.findall(html):
        tm = _TIDAL_TITLE.search(block)
        if not tm:
            continue
        title = unescape(re.sub(r"<[^>]+>", "", tm.group(1))).strip()
        if not title:
            continue
        am = _TIDAL_ARTIST.search(block)
        artist = unescape(re.sub(r"<[^>]+>", "", am.group(1))).strip() if am else ""
        dm = _TIDAL_DURATION.search(block)
        dur_ms = _mmss_to_ms(re.sub(r"<[^>]+>", "", dm.group(1))) if dm else None
        pid_m = re.search(r'product-id="(\d+)"', block)
        tracks.append(MusicTrack(
            title=title, artists=artist or og_artist or "", duration_ms=dur_ms,
            is_explicit='slot="explicit-badge"><i class="badge explicit"' in block,
            album=og_name if kind == "album" else None, cover_url=cover,
            source_url=f"https://tidal.com/track/{pid_m.group(1)}" if pid_m else ""))

    if not tracks:
        raise MusicImportError("Could not read the Tidal tracklist.")
    if kind == "track":
        return MusicImportInfo(source="tidal", type="track", name=tracks[0].title,
                               subtitle=tracks[0].artists, cover_url=cover, tracks=tracks[:1])
    subtitle = og_artist if kind == "album" else None
    return MusicImportInfo(source="tidal", type=kind, name=og_name or "Tidal",
                           subtitle=subtitle, cover_url=cover, tracks=tracks)


# --- Amazon Music (public embed scrape) ------------------------------------

_AMZ_ITEM_RE = re.compile(r'<li class="trackItem.*?</li>', re.DOTALL)
_AMZ_TITLE_RE = re.compile(r'class="trackListTitle[^"]*"[^>]*>(?:<a[^>]*>)?([^<]+)', re.DOTALL)
_AMZ_ARTIST_RE = re.compile(r'class="trackListArtist[^"]*"[^>]*>(?:<a[^>]*>)?([^<]+)', re.DOTALL)
_AMZ_ASIN_RE = re.compile(r'data-asin="([A-Z0-9]+)"')
_TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)


def _resolve_amazon(url: str) -> MusicImportInfo:
    match = _AMAZON_RE.search(url)
    if not match:
        raise MusicImportError("Not a recognised Amazon Music URL.")
    kind_path, asin = match.group(1).lower(), match.group(2)
    kind: MusicKind = (
        "track" if kind_path == "tracks"
        else "playlist" if "playlist" in kind_path
        else "album"
    )
    # The embed lives at music.amazon.<tld>/embed/<asin>; reuse the URL's tld.
    tld_m = re.search(r"music\.amazon\.([a-z.]+)/", url)
    tld = tld_m.group(1) if tld_m else "com"
    # Collapse inter-tag whitespace so titles/artists sit flush after their tags.
    html = re.sub(r">\s+<", "><", _get(f"https://music.amazon.{tld}/embed/{asin}"))

    title_tag = _TITLE_TAG_RE.search(html)
    set_name = ""
    if title_tag:
        # "Amazon Music - Álbum <name> [Explicit]" / "... - Playlist <name>"
        set_name = re.sub(r"^Amazon Music\s*[-–]\s*(?:Álbum|Album|Playlist|Lista)\s*",
                          "", unescape(title_tag.group(1))).strip()
        set_name = re.sub(r"\s*\[Explicit\]\s*$", "", set_name)

    cover_m = re.search(r'<meta property="og:image" content="([^"]*)"', html)
    cover = unescape(cover_m.group(1)) if cover_m else None

    tracks: list[MusicTrack] = []
    for block in _AMZ_ITEM_RE.findall(html):
        tm = _AMZ_TITLE_RE.search(block)
        if not tm:
            continue
        title = re.sub(r"\s*\[Explicit\]\s*$", "", unescape(tm.group(1)).strip())
        am = _AMZ_ARTIST_RE.search(block)
        artist = unescape(am.group(1)).strip() if am else ""
        asin_m = _AMZ_ASIN_RE.search(block)
        tracks.append(MusicTrack(
            title=title, artists=artist,
            is_explicit="[Explicit]" in tm.group(1),
            album=set_name if kind == "album" else None, cover_url=cover,
            source_url=f"https://music.amazon.{tld}/albums/{asin}?trackAsin={asin_m.group(1)}"
            if asin_m else ""))

    if not tracks:
        raise MusicImportError("Could not read the Amazon Music tracklist.")
    if kind == "track":
        return MusicImportInfo(source="amazon", type="track", name=tracks[0].title,
                               subtitle=tracks[0].artists, cover_url=cover, tracks=tracks[:1])
    subtitle = tracks[0].artists if kind == "album" else None
    return MusicImportInfo(source="amazon", type=kind, name=set_name or "Amazon Music",
                           subtitle=subtitle, cover_url=cover, tracks=tracks)
