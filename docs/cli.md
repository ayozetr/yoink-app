# Yoink CLI

A thin command-line front-end over Yoink's own engine — `yoink <url>` for scripts,
cron and the terminal. It runs the **exact same** yt-dlp + ffmpeg pipeline the desktop
app uses, **in-process**: no running server, no duplicated logic. It handles single
URLs, **playlists** and **music-service imports** (Spotify / Deezer / Apple / Tidal /
Amazon).

Because it calls the same code, it automatically:

- honours your **saved settings** (download directory, format/quality defaults, cookies,
  proxy, SponsorBlock, filename template, loudness normalization …),
- **auto-tags** (music-service imports get the exact source metadata; a plain audio
  download can be tagged from the catalogue with `--tag`), and
- writes to the **same history database** — so CLI downloads show up in the app.

## Running it

From the project (after `python scripts/setup.py`):

```bash
scripts/yoink <url>
```

For a bare `yoink` command, symlink the wrapper onto your `PATH`:

```bash
ln -s "$(pwd)/scripts/yoink" ~/.local/bin/yoink
yoink <url>
```

Or invoke the module directly with the backend venv (from the `backend/` directory):

```bash
backend/.venv/bin/python -m app.cli <url>
```

## Commands

```
yoink <url> [options]
```

| Option | Description |
| --- | --- |
| `<url>` | A media URL, a **playlist**, or a **music-service URL** (Spotify/Deezer/Apple/Tidal/Amazon). |
| `--audio` / `--video` | Download audio only, or video (the default). |
| `-f`, `--format {mp3,m4a,flac,wav}` | Audio format (with `--audio`). FLAC/WAV only apply to lossless sources. |
| `-c`, `--container {mp4,mov,mkv}` | Video container. |
| `-q`, `--quality Q` | Video quality, e.g. `1080`, `720`, `best`. |
| `-o`, `--output DIR` | Download directory for this run. Relative paths resolve against your current dir. |
| `--vr` | Tag the output as immersive VR, auto-detecting the layout. |
| `--vr-layout LAYOUT` | Force a VR layout (implies `--vr`): `180_sbs`, `180_tb`, `180_mono`, `360_sbs`, `360_tb`, `360_mono`, `fisheye190`, `fisheye200`, `mkx200`, `mkx220`, `rf52`. |
| `--items SPEC` | For a playlist/album: which entries to download, e.g. `1,3,5-8` (default: all). |
| `--filter TEXT` | Only entries whose title/artist contains `TEXT` (case-insensitive). |
| `--skip-existing` | Skip entries already in the download history. |
| `--tag` | Auto-tag a **plain** audio download from the music catalogue (identify → top match). Opt-in — applies without a review step. |
| `--no-tag` | Don't tag (music-service imports are tagged by default; this turns it off). |
| `--info` | Print metadata and exit — no download. |
| `--list` | List a playlist/album's numbered entries and exit — no download. |
| `--json` | Machine-readable JSON on stdout (for scripts/pipes). |
| `-h`, `--help` | Show help. |

Any option you don't pass falls back to your **Settings** defaults.

## Examples

```bash
# Video, best quality, to your configured download folder
yoink "https://youtu.be/VIDEO"

# Audio as mp3
yoink "https://youtu.be/VIDEO" --audio -f mp3

# Immersive VR: auto-detect the layout, or force one
yoink "https://vr.example/clip" --vr
yoink "https://vr.example/clip" --vr-layout 180_sbs

# See a playlist's contents, then grab a subset
yoink "https://youtube.com/playlist?list=…" --list
yoink "https://youtube.com/playlist?list=…" --items 1,3-5 --skip-existing

# Import a whole album from a music service — matched on YouTube, tagged with the
# EXACT source metadata (artist / title / album / year / cover)
yoink "https://open.spotify.com/album/…" -f m4a

# Tag a plain audio download from the catalogue
yoink "https://youtu.be/VIDEO" --audio --tag

# Script-friendly: JSON out + exit code
if f=$(yoink "$1" --audio -f mp3 --json | jq -r .filepath); then echo "saved: $f"; fi
```

## Auto-tagging

- **Music-service imports** are tagged automatically with the **exact source metadata**
  (no catalogue guessing, no review needed). Turn it off with `--no-tag`.
- A **plain audio download** is only tagged if you pass `--tag`. It looks the file up in
  the catalogue (`autotag_source`: Apple Music / Deezer / MusicBrainz / auto) and applies
  the **top match** — with no interactive review, so it's opt-in. If nothing matches it
  leaves the file untouched (better no tags than wrong ones).
- Lyrics (`fetch_lyrics`) and `.nfo` sidecars follow your Settings.

## Output & exit codes

- **Progress** (percent · speed · ETA, prefixed `[n/total]` in batches) is drawn on
  **stderr**, so **stdout** stays clean: a plain run prints the final file path(s);
  `--json` prints one JSON object per download.
- Exit codes: `0` success (all items) · `1` a download/extraction error · `2` invalid
  arguments · `130` cancelled (Ctrl-C). A batch returns `1` if any item failed.

```json
// --json on success
{"status": "completed", "filename": "Song.mp3", "filepath": "/…/Song.mp3", "bytes": 328659}
```

## Scope & follow-ups

Still engine-backed, so more can be surfaced without new download logic. **Not yet
exposed as flags:** trim ranges and subtitle-language selection (both exist in the
engine).

## How it fits

The CLI lives in `backend/app/cli.py` and imports the services directly
(`ytdlp_service.extract_info`, `download_service.download_events`, `music_import`,
`autotag_service`, `settings_store`, `history_store`). The wrapper `scripts/yoink` runs
it with the backend venv and the right `PYTHONPATH`. See
[`docs/architecture.md`](architecture.md) for the engine itself.
