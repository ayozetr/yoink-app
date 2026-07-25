"""Thin CLI over Yoink's own engine — ``yoink <url>`` for scripts.

Runs the exact same yt-dlp + ffmpeg pipeline the desktop app uses, **in-process**:
it reuses the saved settings (download dir, format defaults, cookies, proxy,
SponsorBlock…), auto-tags audio and writes to the same history DB — and needs no
running server. Handles single URLs, playlists and music-service imports.

    yoink <url>                       # video, best quality, to the saved dir
    yoink <url> --audio -f mp3         # audio only, mp3
    yoink <playlist-url> --items 1,3-5 # a subset of a playlist
    yoink <spotify-album> --tag        # music import: match on YouTube + tag
    yoink <url> --info | --list        # inspect without downloading
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import threading
from pathlib import Path
from typing import Any

# Immersive-video layouts (mirrors DownloadRequest.vr_layout in models/media.py).
VR_LAYOUTS = [
    "180_sbs", "180_tb", "180_mono", "360_sbs", "360_tb", "360_mono",
    "fisheye190", "fisheye200", "mkx200", "mkx220", "rf52",
]


# --------------------------------------------------------------------------- args


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="yoink", description="Download media with Yoink's engine."
    )
    p.add_argument("url", help="a media URL, playlist, or music-service URL")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--audio", action="store_true", help="download audio only")
    mode.add_argument("--video", action="store_true", help="download video (default)")
    p.add_argument("-f", "--format", choices=["mp3", "m4a", "flac", "wav"],
                   help="audio format (with --audio)")
    p.add_argument("-c", "--container", choices=["mp4", "mov", "mkv"],
                   help="video container")
    p.add_argument("-q", "--quality", help='video quality, e.g. "1080", "720", "best"')
    p.add_argument("-o", "--output", metavar="DIR",
                   help="download directory (overrides the saved one)")
    p.add_argument("--vr", action="store_true",
                   help="tag the output as immersive VR, auto-detecting the layout")
    p.add_argument("--vr-layout", choices=VR_LAYOUTS, metavar="LAYOUT",
                   help="force a VR layout (implies --vr): " + ", ".join(VR_LAYOUTS))
    # Playlist / music-service selection
    p.add_argument("--items", metavar="SPEC",
                   help="which entries to download, e.g. 1,3,5-8 (default: all)")
    p.add_argument("--filter", metavar="TEXT",
                   help="only entries whose title/artist contains TEXT (case-insensitive)")
    p.add_argument("--skip-existing", action="store_true",
                   help="skip entries already in the download history")
    # Tagging
    p.add_argument("--tag", action="store_true",
                   help="auto-tag a plain audio download from the music catalogue")
    p.add_argument("--no-tag", action="store_true",
                   help="don't tag (music-service imports are tagged by default)")
    # Output modes
    p.add_argument("--info", action="store_true",
                   help="print metadata and exit (no download)")
    p.add_argument("--list", action="store_true",
                   help="list a playlist/album's entries and exit (no download)")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    return p


def _parse_items(spec: str) -> set[int]:
    """Expand a "1,3,5-8" selection into a set of 1-based indices."""
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.update(range(int(lo), int(hi) + 1))
        else:
            out.add(int(part))
    return out


# --------------------------------------------------------------------------- output


def _fail(message: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"status": "error", "message": message}))
    else:
        print(f"error: {message}", file=sys.stderr)


def _render_progress(ev, prefix: str = "") -> None:
    """A single \\r-updated line on stderr; speed/eta arrive already humanized."""
    pct = ev.percent or 0.0
    width = 20
    filled = int(width * pct / 100)
    bar = "█" * filled + "─" * (width - filled)
    sys.stderr.write(
        f"\r  {prefix}[{bar}] {pct:5.1f}%  {ev.speed or '—':>11}  ETA {ev.eta or '—':>6}  "
        f"{ev.status:<11}"
    )
    sys.stderr.flush()


# --------------------------------------------------------------------------- tagging


def _apply_music_tags(filepath: Path, track) -> None:
    """Tag a music-import download with the *exact* source metadata (best-effort)."""
    from app.core.config import settings
    from app.models.autotag import ApplyRequest
    from app.services.autotag_service import apply

    try:
        apply(
            ApplyRequest(
                path=str(filepath), title=track.title, artist=track.artists,
                album=track.album, year=str(track.year) if track.year else None,
                cover_url=track.cover_url, embed_lyrics=settings.fetch_lyrics,
            ),
            filepath,
        )
    except Exception:  # noqa: BLE001 — best effort; the audio is already saved
        pass


def _apply_catalog_tags(filepath: Path) -> None:
    """Tag a plain audio download from the catalogue (identify → best → apply).

    Non-interactive, so it applies the top match; if nothing is found it leaves the
    file untouched (better no tags than wrong ones).
    """
    from app.core.config import settings
    from app.models.autotag import ApplyRequest
    from app.services.autotag_service import apply, identify

    try:
        results = identify(filepath).results
        if not results:
            return
        c = results[0]
        apply(
            ApplyRequest(
                path=str(filepath), title=c.title, artist=c.artist, album=c.album,
                year=c.year, track_number=c.track_number, cover_url=c.cover_url,
                embed_lyrics=settings.fetch_lyrics,
            ),
            filepath,
        )
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- download


def _build_request(url: str, args, defaults, *, kind_override: str | None = None):
    from app.models.media import DownloadRequest

    kind = kind_override or (
        "audio" if args.audio else "video" if args.video else defaults.default_kind
    )
    is_video = kind == "video"
    return DownloadRequest(
        url=url, kind=kind,
        quality=args.quality or defaults.default_quality,
        container=args.container or defaults.default_container,
        audio_format=args.format or defaults.default_audio_format,
        embed_subs=defaults.default_embed_subs,
        embed_chapters=defaults.default_embed_chapters,
        is_vr=is_video and bool(args.vr_layout),
        vr_layout=args.vr_layout or "180_sbs",
        auto_vr=is_video and args.vr and not args.vr_layout,
    )


async def _download_one(request, *, prefix: str, as_json: bool, tag: Any = None) -> bool:
    """Download one request, record history, optionally tag. Returns success."""
    from app.routers.download import _quality_label
    from app.services import history_store
    from app.services.download_service import download_events

    cancel = threading.Event()
    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, cancel.set)
    except (NotImplementedError, ValueError):
        pass

    completed = error = None
    async for ev in download_events(request, cancel):
        if ev.type == "progress":
            if not as_json:
                _render_progress(ev, prefix)
        elif ev.type == "completed":
            completed = ev
        elif ev.type == "error":
            error = ev
    if not as_json:
        sys.stderr.write("\n")

    if completed is None:
        _fail(error.message if error else "cancelled", as_json)
        return False

    filepath = Path(completed.filepath)
    quality = await asyncio.to_thread(_quality_label, request, completed.filepath)
    try:
        await asyncio.to_thread(
            history_store.add_entry, title=filepath.stem, url=str(request.url),
            kind=request.kind, status="completed", filename=completed.filename,
            filepath=completed.filepath, filesize=completed.total_bytes, quality=quality,
        )
    except Exception:  # noqa: BLE001
        pass

    if request.kind == "audio" and tag is not None:
        if tag == "catalog":
            await asyncio.to_thread(_apply_catalog_tags, filepath)
        else:  # a MusicTrack: exact source metadata
            await asyncio.to_thread(_apply_music_tags, filepath, tag)

    if as_json:
        print(json.dumps({"status": "completed", "filename": completed.filename,
                          "filepath": completed.filepath, "bytes": completed.total_bytes}))
    else:
        print(completed.filepath)
    return True


# --------------------------------------------------------------------------- flows


def _selected(entries: list, args, *, key) -> list:
    """Apply --items / --filter to a 1-based list; ``key(entry)`` is its search text."""
    items = _parse_items(args.items) if args.items else None
    out = []
    for i, e in enumerate(entries, 1):
        if items is not None and i not in items:
            continue
        if args.filter and args.filter.lower() not in key(e).lower():
            continue
        out.append(e)
    return out


def _already_done() -> set[str]:
    from app.routers.info import _match_key
    from app.services import history_store

    return {_match_key(u) for u in history_store.completed_urls()}


async def _run_single(request, args) -> int:
    tag = "catalog" if (request.kind == "audio" and args.tag and not args.no_tag) else None
    return 0 if await _download_one(request, prefix="", as_json=args.json, tag=tag) else 1


async def _run_playlist(entries, args) -> int:
    from app.routers.info import _match_key

    from app.services import settings_store

    picked = _selected(entries, args, key=lambda e: e.title or "")
    done = _already_done() if args.skip_existing else set()
    picked = [e for e in picked if not (args.skip_existing and _match_key(e.url) in done)]
    if not picked:
        print("nothing to download", file=sys.stderr)
        return 0

    defaults = settings_store.get_current()
    tag = "catalog" if (not args.no_tag and args.tag) else None
    total, ok = len(picked), 0
    for n, e in enumerate(picked, 1):
        prefix = f"[{n}/{total}] "
        try:
            request = _build_request(e.url, args, defaults)
        except Exception:  # noqa: BLE001 — a bad entry URL shouldn't sink the batch
            print(f"{prefix}skipped (bad URL): {e.title}", file=sys.stderr)
            continue
        if await _download_one(request, prefix=prefix, as_json=args.json,
                               tag=tag if request.kind == "audio" else None):
            ok += 1
    print(f"\n{ok}/{total} downloaded.", file=sys.stderr)
    return 0 if ok == total else 1


async def _run_music(info, args) -> int:
    from app.routers.info import _match_key

    from app.services import settings_store
    from app.services.music_import import find_youtube_match

    picked = _selected(info.tracks, args, key=lambda t: f"{t.artists} {t.title}")
    if not picked:
        print("nothing to download", file=sys.stderr)
        return 0

    defaults = settings_store.get_current()
    done = _already_done() if args.skip_existing else set()
    total, ok = len(picked), 0
    for n, t in enumerate(picked, 1):
        prefix = f"[{n}/{total}] {t.artists} — {t.title[:28]}  "
        url = await asyncio.to_thread(find_youtube_match, t)
        if not url:
            sys.stderr.write(f"\r{prefix}no YouTube match\n")
            continue
        if args.skip_existing and _match_key(url) in done:
            sys.stderr.write(f"\r{prefix}already downloaded\n")
            ok += 1
            continue
        request = _build_request(url, args, defaults, kind_override="audio")
        tag = None if args.no_tag else t  # exact source metadata
        if await _download_one(request, prefix=prefix, as_json=args.json, tag=tag):
            ok += 1
    print(f"\n{ok}/{total} imported.", file=sys.stderr)
    return 0 if ok == total else 1


# --------------------------------------------------------------------------- info/list


def _print_video_info(v, as_json: bool) -> int:
    if as_json:
        print(json.dumps({
            "type": "video", "title": v.title, "uploader": v.uploader,
            "duration": v.duration_string, "has_audio": v.has_audio,
            "is_vr": v.is_vr, "formats": len(v.formats), "webpage_url": v.webpage_url,
        }))
    else:
        print(f"Title:    {v.title}")
        print(f"Uploader: {v.uploader or '—'}")
        print(f"Duration: {v.duration_string or '—'}")
        print(f"Audio:    {'yes' if v.has_audio else 'no'}")
        if v.is_vr:
            print(f"VR:       {v.vr_layout}")
        print(f"Formats:  {len(v.formats)}")
    return 0


def _print_entries(title: str, count: int, rows: list[tuple[str, str | None]],
                   as_json: bool) -> int:
    """Numbered list of entries — ``rows`` are (label, duration) pairs."""
    if as_json:
        print(json.dumps({"title": title, "count": count,
                          "entries": [{"n": i, "title": r[0], "duration": r[1]}
                                      for i, r in enumerate(rows, 1)]}))
    else:
        print(f"{title} — {count} item(s)")
        for i, (label, dur) in enumerate(rows, 1):
            print(f"  {i:>3}. {label}" + (f"  [{dur}]" if dur else ""))
    return 0


# --------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    from app.core.config import settings
    from app.services import settings_store

    settings_store.load_overrides()
    if args.output:
        settings.download_dir = Path(args.output).expanduser().resolve()

    url = args.url
    from app.services.music_import import is_music_url

    # --- music-service URL (Spotify/Deezer/Apple/Tidal/Amazon) ------------------
    if is_music_url(url):
        from app.services.music_import import resolve

        try:
            info = resolve(url)
        except Exception as exc:  # noqa: BLE001
            _fail(str(exc), args.json)
            return 1
        if args.info:
            return _print_entries(f"{info.type.title()}: {info.name}", len(info.tracks),
                                  [(f"{t.artists} — {t.title}",
                                    None) for t in info.tracks], args.json)
        if args.list:
            return _print_entries(f"{info.type.title()}: {info.name}", len(info.tracks),
                                  [(f"{t.artists} — {t.title}", None)
                                   for t in info.tracks], args.json)
        return asyncio.run(_run_music(info, args))

    # --- everything else: analyze only when we might need the listing -----------
    from app.services.ytdlp_service import MediaExtractionError, extract_info

    if args.info or args.list or _looks_like_playlist(url):
        try:
            resp = extract_info(url)
        except MediaExtractionError as exc:
            _fail(str(exc), args.json)
            return 1
        if resp.type == "playlist" and resp.playlist:
            pl = resp.playlist
            if args.info or args.list:
                return _print_entries(f"Playlist: {pl.title}", pl.entry_count,
                                      [(e.title, e.duration_string) for e in pl.entries],
                                      args.json)
            return asyncio.run(_run_playlist(pl.entries, args))
        if resp.video is not None:  # a single video
            if args.info or args.list:
                return _print_video_info(resp.video, args.json)

    # --- single download --------------------------------------------------------
    from pydantic import ValidationError

    try:
        request = _build_request(url, args, settings_store.get_current())
    except ValidationError as exc:
        _fail(f"invalid request: {exc}", args.json)
        return 2
    try:
        return asyncio.run(_run_single(request, args))
    except KeyboardInterrupt:
        return 130


def _looks_like_playlist(url: str) -> bool:
    """A URL yt-dlp would expand into several items (so we resolve it first)."""
    import re

    return bool(re.search(r"([?&]list=|/playlist\b|/sets/)", url, re.IGNORECASE))


if __name__ == "__main__":
    raise SystemExit(main())
