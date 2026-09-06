"""Thin CLI over Yoink's own engine — ``yoink <url>`` for scripts.

Runs the exact same yt-dlp + ffmpeg pipeline the desktop app uses, **in-process**:
it reuses the saved settings (download dir, format defaults, cookies, proxy,
SponsorBlock…), auto-tags audio and writes to the same history DB — and needs no
running server. Handles single URLs, playlists and music-service imports.

    yoink <url>                       # video, best quality, to the saved dir
    yoink <url> --audio -f mp3         # audio only, mp3
    yoink <url> --trim-start 1:30 --trim-end 2:00   # clip a range
    yoink <url> --subs es              # embed Spanish subtitles
    yoink <url1> <url2> ...            # several URLs in one run
    yoink -a urls.txt                  # read URLs from a file (only links are taken)
    cat urls.txt | yoink -             # …or from stdin
    yoink <playlist-url> --items 1,3-5 # a subset of a playlist
    yoink <spotify-album> --tag        # music import: match on YouTube + tag
    yoink <url> --info | --list        # inspect without downloading
    yoink --print-completion fish      # shell completion script
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
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


def _timestamp(value: str) -> float:
    """Parse a trim point: plain seconds (``90``, ``1.5``) or a clock (``1:30``,
    ``01:02:03``). Returns seconds. Raises for argparse to surface as exit 2."""
    text = value.strip()
    try:
        if ":" in text:
            parts = text.split(":")
            if len(parts) > 3:
                raise ValueError
            secs = 0.0
            for part in parts:
                secs = secs * 60 + float(part)
            return secs
        return float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid time {value!r} (use seconds or MM:SS / HH:MM:SS)"
        ) from None


class _PrintCompletion(argparse.Action):
    """Print a shell completion script and exit — like ``--help``, before the
    positional URL is required, so ``yoink --print-completion fish`` needs no URL."""

    def __call__(self, parser, namespace, values, option_string=None):  # noqa: D401
        sys.stdout.write(_completion_script(values))
        parser.exit()


class _PrintVersion(argparse.Action):
    """Print the installed Yoink version and exit (imports settings lazily)."""

    def __call__(self, parser, namespace, values, option_string=None):  # noqa: D401
        from app.core.config import settings

        print(f"yoink {settings.app_version}")
        parser.exit()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="yoink", description="Download media with Yoink's engine.",
        epilog="settings: 'yoink config' prints them; "
               "'yoink config get|set KEY [VALUE]' reads/edits them.",
    )
    p.add_argument("urls", nargs="*", metavar="URL",
                   help="one or more media / playlist / music-service URLs "
                        "(or '-' to read URLs from stdin)")
    p.add_argument("-a", "--batch-file", action="append", metavar="FILE",
                   help="read URLs from FILE ('-' for stdin); only http(s) links are "
                        "taken, so comments/notes are ignored. Repeatable.")
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
    # Per-run overrides — layered onto the saved settings for this invocation only.
    p.add_argument("-t", "--filename-template", metavar="TMPL",
                   help="yt-dlp output-name template, e.g. '%%(title)s [%%(id)s]'")
    p.add_argument("--rate-limit", metavar="RATE",
                   help="cap download speed, e.g. 2M or 500K")
    p.add_argument("--proxy", metavar="URL",
                   help="proxy for metadata + downloads (http/https/socks)")
    p.add_argument("--cookies-from-browser", metavar="BROWSER",
                   help="read cookies from a browser, e.g. firefox/chrome")
    p.add_argument("--cookies-file", metavar="FILE",
                   help="Netscape cookies.txt for age-gated / private content")
    p.add_argument("--sponsorblock", nargs="?", const="remove",
                   choices=["remove", "mark"], metavar="ACTION",
                   help="SponsorBlock (YouTube): remove or mark segments (bare = remove)")
    p.add_argument("--normalize", action="store_true",
                   help="loudness-normalize audio (re-encodes); target set by --normalize-lufs")
    p.add_argument("--normalize-lufs", type=int, metavar="LUFS",
                   help="loudness target in LUFS (implies --normalize), e.g. -14 "
                        "(streaming) / -16 (Apple Music) / -23 (broadcast). Any value "
                        "in loudnorm's range -70..-5")
    p.add_argument("--video-codec", choices=["any", "h264", "vp9", "av1"],
                   help="prefer a video codec when picking the format")
    p.add_argument("--audio-bitrate", choices=["best", "320", "256", "192", "128"],
                   metavar="KBPS", help="lossy audio bitrate in kbps, or 'best'")
    # Trim / clip a time range (seconds or MM:SS / HH:MM:SS)
    p.add_argument("--trim-start", type=_timestamp, metavar="TS",
                   help="clip start, e.g. 90 or 1:30 (seconds or MM:SS / HH:MM:SS)")
    p.add_argument("--trim-end", type=_timestamp, metavar="TS",
                   help="clip end, e.g. 2:00 (must be after --trim-start)")
    # Subtitles (video only): embed a language, or force off
    subs = p.add_mutually_exclusive_group()
    subs.add_argument("--subs", nargs="?", const="all", metavar="LANG",
                      help="embed subtitles; LANG like en/es/all (bare = all)")
    subs.add_argument("--no-subs", action="store_true",
                      help="don't embed subtitles (overrides the saved default)")
    # Chapter markers (video): override the saved default either way
    chap = p.add_mutually_exclusive_group()
    chap.add_argument("--chapters", action="store_true",
                      help="embed chapter markers when the source has them")
    chap.add_argument("--no-chapters", action="store_true",
                      help="don't embed chapter markers (overrides the saved default)")
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
    p.add_argument("--list-formats", action="store_true",
                   help="list a single video's available formats and exit (no download)")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    p.add_argument("--quiet", action="store_true",
                   help="only errors + final paths (no progress bar, no summaries)")
    p.add_argument("--no-progress", action="store_true",
                   help="hide the progress bar (keep summaries)")
    p.add_argument("--print-completion", choices=["bash", "zsh", "fish"], metavar="SHELL",
                   action=_PrintCompletion,
                   help="print a shell completion script (bash|zsh|fish) and exit")
    p.add_argument("--version", nargs=0, action=_PrintVersion,
                   help="print the Yoink version and exit")
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


# ----------------------------------------------------------------------- completion


def _completion_options() -> list[tuple[list[str], bool, list[str], str]]:
    """Introspect the parser into (flags, takes_arg, choices, kind) per option, so
    the completion scripts stay in sync with the flags automatically. ``kind`` is
    one of choice/dir/file/value/flag, derived from the metavar."""
    out = []
    for action in _build_parser()._actions:
        if not action.option_strings or action.dest == "help":
            continue
        takes_arg = action.nargs != 0
        choices = list(action.choices) if action.choices else []
        metavar = getattr(action, "metavar", None)
        if choices:
            kind = "choice"
        elif metavar == "DIR":
            kind = "dir"
        elif metavar == "FILE":
            kind = "file"
        elif takes_arg:
            kind = "value"
        else:
            kind = "flag"
        out.append((list(action.option_strings), takes_arg, choices, kind))
    return out


def _completion_script(shell: str) -> str:
    """A completion script for bash/zsh/fish, generated from the parser itself."""
    opts = _completion_options()
    flags = [f for names, *_ in opts for f in names]

    if shell == "fish":
        lines = [
            "# yoink fish completion",
            "# install: yoink --print-completion fish > ~/.config/fish/completions/yoink.fish",
        ]
        for names, _takes_arg, choices, kind in opts:
            parts = ["complete", "-c", "yoink"]
            for name in names:
                parts += (["-s", name[1:]] if not name.startswith("--")
                          else ["-l", name[2:]])
            if kind == "dir":
                parts += ["-r", "-a", "'(__fish_complete_directories)'"]
            elif kind == "file":
                parts += ["-r"]  # fish completes files by default for -r
            elif kind == "choice":
                parts += ["-x", "-a", "'" + " ".join(choices) + "'"]
            elif kind == "value":
                parts += ["-x"]
            lines.append(" ".join(parts))
        return "\n".join(lines) + "\n"

    arms = []
    for names, _takes_arg, choices, kind in opts:
        if kind == "choice":
            comp = (f'compadd {" ".join(choices)}' if shell == "zsh"
                    else f'COMPREPLY=( $(compgen -W "{" ".join(choices)}" -- "$cur") )')
        elif kind == "dir":
            comp = "_files -/" if shell == "zsh" else \
                'COMPREPLY=( $(compgen -d -- "$cur") )'
        elif kind == "file":
            comp = "_files" if shell == "zsh" else \
                'COMPREPLY=( $(compgen -f -- "$cur") )'
        else:
            continue
        arms.append(f"    {'|'.join(names)}) {comp}; return;;")
    arms_block = "\n".join(arms)
    flags_line = " ".join(flags)

    if shell == "zsh":
        return (
            "#compdef yoink\n"
            "# yoink zsh completion\n"
            "# install: yoink --print-completion zsh > ~/.zfunc/_yoink"
            "  (dir on $fpath)\n"
            "local cur prev\n"
            "cur=${words[CURRENT]}\n"
            "prev=${words[CURRENT-1]}\n"
            "case $prev in\n"
            f"{arms_block}\n"
            "esac\n"
            'if [[ $cur == -* ]]; then\n'
            f"    compadd -- {flags_line}\n"
            "else\n"
            "    _files\n"
            "fi\n"
        )

    return (
        "# yoink bash completion\n"
        "# install: yoink --print-completion bash > "
        "~/.local/share/bash-completion/completions/yoink\n"
        "_yoink() {\n"
        "    local cur prev\n"
        '    cur="${COMP_WORDS[COMP_CWORD]}"\n'
        '    prev="${COMP_WORDS[COMP_CWORD-1]}"\n'
        '    case "$prev" in\n'
        f"{arms_block}\n"
        "    esac\n"
        '    if [[ "$cur" == -* ]]; then\n'
        f'        COMPREPLY=( $(compgen -W "{flags_line}" -- "$cur") )\n'
        "    else\n"
        '        COMPREPLY=( $(compgen -f -- "$cur") )\n'
        "    fi\n"
        "}\n"
        "complete -F _yoink yoink\n"
    )


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

    # Subtitles (video only): --subs LANG embeds it, --no-subs forces off, else default.
    if args.no_subs:
        embed_subs, subtitle_lang = False, None
    elif args.subs is not None:
        embed_subs, subtitle_lang = True, (None if args.subs == "all" else args.subs)
    else:
        embed_subs, subtitle_lang = defaults.default_embed_subs, None

    # Chapters: explicit override wins, otherwise the saved default.
    embed_chapters = (
        False if args.no_chapters
        else True if args.chapters
        else defaults.default_embed_chapters
    )

    return DownloadRequest(
        url=url, kind=kind,
        quality=args.quality or defaults.default_quality,
        container=args.container or defaults.default_container,
        audio_format=args.format or defaults.default_audio_format,
        embed_subs=embed_subs and is_video,
        subtitle_lang=subtitle_lang if is_video else None,
        embed_chapters=embed_chapters,
        trim_start=args.trim_start,
        trim_end=args.trim_end,
        is_vr=is_video and bool(args.vr_layout),
        vr_layout=args.vr_layout or "180_sbs",
        auto_vr=is_video and args.vr and not args.vr_layout,
    )


async def _download_one(request, *, prefix: str, as_json: bool, tag: Any = None,
                        progress: bool = True) -> bool:
    """Download one request, record history, optionally tag. Returns success."""
    from app.routers.download import _quality_label
    from app.services import history_store
    from app.services.download_service import download_events

    cancel = threading.Event()
    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, cancel.set)
    except (NotImplementedError, ValueError):
        pass

    show_bar = progress and not as_json
    completed = error = None
    async for ev in download_events(request, cancel):
        if ev.type == "progress":
            if show_bar:
                _render_progress(ev, prefix)
        elif ev.type == "completed":
            completed = ev
        elif ev.type == "error":
            error = ev
    if show_bar:
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


def _show_progress(args) -> bool:
    return not (args.no_progress or args.quiet)


async def _run_single(request, args) -> int:
    tag = "catalog" if (request.kind == "audio" and args.tag and not args.no_tag) else None
    ok = await _download_one(request, prefix="", as_json=args.json, tag=tag,
                             progress=_show_progress(args))
    return 0 if ok else 1


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
                               tag=tag if request.kind == "audio" else None,
                               progress=_show_progress(args)):
            ok += 1
    if not args.quiet:
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
        if await _download_one(request, prefix=prefix, as_json=args.json, tag=tag,
                               progress=_show_progress(args)):
            ok += 1
    if not args.quiet:
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


def _print_formats(v, as_json: bool) -> int:
    """List a single video's available formats (id / ext / resolution / codecs / size)."""
    from app.core.humanize import humanize_bytes

    if as_json:
        print(json.dumps({
            "title": v.title,
            "formats": [
                {"format_id": f.format_id, "ext": f.ext, "resolution": f.resolution,
                 "fps": f.fps, "vcodec": f.vcodec, "acodec": f.acodec,
                 "filesize": f.filesize}
                for f in v.formats
            ],
        }))
        return 0
    print(f"{v.title} — {len(v.formats)} format(s)")
    print(f"  {'ID':<8} {'EXT':<5} {'RESOLUTION':<12} {'FPS':>4} "
          f"{'VCODEC':<10} {'ACODEC':<10} SIZE")
    for f in v.formats:
        size = humanize_bytes(f.filesize) if f.filesize else "—"
        fps = str(int(f.fps)) if f.fps else ""
        print(f"  {f.format_id:<8} {f.ext:<5} {(f.resolution or '—'):<12} "
              f"{fps:>4} {(f.vcodec or '—'):<10} {(f.acodec or '—'):<10} {size}")
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


# --------------------------------------------------------------- url collection


_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)


def _extract_urls(text: str) -> list[str]:
    """Pull http(s) URLs out of arbitrary text, so a batch file / stdin can hold
    comments, blank lines or notes — only the links are taken."""
    return [m.group(0).rstrip(".,;)]}\"'") for m in _URL_RE.finditer(text)]


def _collect_urls(args) -> list[str]:
    """Gather URLs from the positionals, any --batch-file(s) and stdin ('-'),
    de-duplicated with order preserved. Command-line URLs are taken verbatim;
    file/stdin content is scanned so only real links are used."""
    raw: list[str] = []
    for u in args.urls:
        raw += _extract_urls(sys.stdin.read()) if u == "-" else [u]
    for path in args.batch_file or []:
        try:
            text = (sys.stdin.read() if path == "-"
                    else Path(path).expanduser().read_text(encoding="utf-8"))
        except OSError as exc:
            _fail(f"cannot read {path}: {exc}", args.json)
            continue
        raw += _extract_urls(text)
    seen: set[str] = set()
    out: list[str] = []
    for u in raw:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _apply_cli_overrides(args, settings) -> None:
    """Layer this run's flags onto the settings singleton — the app's settings UI
    persists these; here they apply for the invocation only. The engine reads
    ``settings.*`` directly (just like ``--output`` for the download dir)."""
    if args.output:
        settings.download_dir = Path(args.output).expanduser().resolve()
    if args.filename_template:
        settings.filename_template = args.filename_template
    if args.rate_limit:
        settings.rate_limit = args.rate_limit
    if args.proxy:
        settings.proxy = args.proxy
    if args.cookies_from_browser:
        settings.cookies_from_browser = args.cookies_from_browser
    if args.cookies_file:
        settings.cookies_file = Path(args.cookies_file).expanduser()
    if args.sponsorblock:
        settings.sponsorblock_enabled = True
        settings.sponsorblock_action = args.sponsorblock
    if args.normalize:
        settings.normalize_audio = True
    if args.normalize_lufs is not None:
        settings.normalize_audio = True
        settings.normalize_lufs = max(-70, min(-5, args.normalize_lufs))
    if args.video_codec:
        settings.video_codec = args.video_codec
    if args.audio_bitrate:
        settings.audio_bitrate = args.audio_bitrate


# ------------------------------------------------------------------------- config


def _coerce_setting(current: Any, value: str) -> Any:
    """Coerce a CLI string to the setting's type (bool / None / str); pydantic
    does the final validation on the whole model."""
    low = value.strip().lower()
    if isinstance(current, bool):
        return low in ("1", "true", "yes", "on")
    if low in ("none", "null", ""):
        return None
    return value


def _run_config(rest: list[str], as_json: bool) -> int:
    """``yoink config`` — read or edit the persisted settings.

        yoink config                 # print all settings
        yoink config get KEY         # print one
        yoink config set KEY VALUE   # set + persist one
    """
    from pydantic import ValidationError

    from app.models.media import AppSettings
    from app.services import settings_store

    data = settings_store.get_current().model_dump()
    if not rest:
        if as_json:
            print(json.dumps(data, indent=2))
        else:
            for key in sorted(data):
                print(f"{key} = {data[key]}")
        return 0

    action, *tail = rest
    if action == "get":
        if len(tail) != 1 or tail[0] not in data:
            _fail("usage: yoink config get KEY", as_json)
            return 2
        val = data[tail[0]]
        print(json.dumps(val) if as_json else ("" if val is None else val))
        return 0
    if action == "set":
        if len(tail) < 2 or tail[0] not in data:
            _fail("usage: yoink config set KEY VALUE", as_json)
            return 2
        key = tail[0]
        data[key] = _coerce_setting(data[key], " ".join(tail[1:]))
        try:
            updated = settings_store.update(AppSettings(**data))
        except ValidationError as exc:
            _fail(f"invalid value for {key}: {exc}", as_json)
            return 2
        print(f"{key} = {updated.model_dump()[key]}")
        return 0
    _fail("usage: yoink config [get KEY | set KEY VALUE]", as_json)
    return 2


# --------------------------------------------------------------------------- main


def _dispatch_url(url: str, args) -> int:
    """Route one URL to the right flow (music import / playlist / single)."""
    from app.services import settings_store
    from app.services.music_import import is_music_url

    try:
        # --- music-service URL (Spotify/Deezer/Apple/Tidal/Amazon) --------------
        if is_music_url(url):
            from app.services.music_import import resolve

            try:
                info = resolve(url)
            except Exception as exc:  # noqa: BLE001
                _fail(str(exc), args.json)
                return 1
            if args.info or args.list:
                return _print_entries(
                    f"{info.type.title()}: {info.name}", len(info.tracks),
                    [(f"{t.artists} — {t.title}", None) for t in info.tracks], args.json)
            return asyncio.run(_run_music(info, args))

        # --- everything else: analyze only when we might need the listing -------
        from app.services.ytdlp_service import MediaExtractionError, extract_info

        if args.info or args.list or args.list_formats or _looks_like_playlist(url):
            try:
                resp = extract_info(url)
            except MediaExtractionError as exc:
                _fail(str(exc), args.json)
                return 1
            if resp.type == "playlist" and resp.playlist:
                pl = resp.playlist
                if args.list_formats:
                    _fail("--list-formats needs a single video, not a playlist",
                          args.json)
                    return 2
                if args.info or args.list:
                    return _print_entries(
                        f"Playlist: {pl.title}", pl.entry_count,
                        [(e.title, e.duration_string) for e in pl.entries], args.json)
                return asyncio.run(_run_playlist(pl.entries, args))
            if resp.video is not None:
                if args.list_formats:
                    return _print_formats(resp.video, args.json)
                if args.info or args.list:
                    return _print_video_info(resp.video, args.json)

        # --- single download ----------------------------------------------------
        from pydantic import ValidationError

        try:
            request = _build_request(url, args, settings_store.get_current())
        except ValidationError as exc:
            _fail(f"invalid request: {exc}", args.json)
            return 2
        return asyncio.run(_run_single(request, args))
    except KeyboardInterrupt:
        return 130


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    from app.core.config import settings
    from app.services import settings_store

    settings_store.load_overrides()

    # `yoink config [...]` — a settings sub-command, no URL/download involved.
    if args.urls and args.urls[0] == "config":
        return _run_config(args.urls[1:], args.json)

    if (args.trim_start is not None and args.trim_end is not None
            and args.trim_end <= args.trim_start):
        _fail("--trim-end must be greater than --trim-start", args.json)
        return 2

    _apply_cli_overrides(args, settings)

    urls = _collect_urls(args)
    if not urls:
        _fail("no URL given (pass a URL, -a FILE, or - to read from stdin)", args.json)
        return 2

    if len(urls) == 1:
        return _dispatch_url(urls[0], args)

    # Batch: independent, sequential (matches the app's single-download model).
    total = len(urls)
    failed = False
    for i, u in enumerate(urls, 1):
        if not args.quiet:
            print(f"\n[{i}/{total}] {u}", file=sys.stderr)
        if _dispatch_url(u, args) != 0:
            failed = True
    return 1 if failed else 0


def _looks_like_playlist(url: str) -> bool:
    """A URL yt-dlp would expand into several items (so we resolve it first)."""
    return bool(re.search(r"([?&]list=|/playlist\b|/sets/)", url, re.IGNORECASE))


if __name__ == "__main__":
    raise SystemExit(main())
