# Yoink Backend

Local FastAPI service that wraps [yt-dlp](https://github.com/yt-dlp/yt-dlp) to
power the Yoink frontend. It extracts media metadata over REST and streams
download progress to the UI over a WebSocket.

> For a deeper reference on yt-dlp itself (pipeline, dependencies, the Python
> embedding API, format selection, progress hooks), see
> [`../docs/yt-dlp.md`](../docs/yt-dlp.md).

## Requirements

- Python **3.13** (recommended — yt-dlp's `curl_cffi` anti-bot impersonation
  needs a Python with compatible wheels; see `../CLAUDE.md`). 3.11+ runs, but
  `scripts/setup.py` selects 3.13.
- [ffmpeg](https://ffmpeg.org/) on your `PATH` (needed to merge high-quality
  video + audio formats during downloads)

## Setup

```bash
cd backend
python -m venv .venv

# Linux / macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

- API base: `http://127.0.0.1:8000/api`
- Interactive docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

## Endpoints

### `POST /api/info`

Extract metadata for a URL **without downloading** (`yt-dlp` `download=False`).

Request:

```json
{ "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }
```

Response (abridged):

```json
{
  "id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "duration": 213.0,
  "duration_string": "3:33",
  "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
  "formats": [{ "format_id": "137", "ext": "mp4", "resolution": "1080p", "has_video": true, "has_audio": false }]
}
```

For a playlist URL the response is a flat listing; the backend resolves the
first entry to set `source_lossless` / `best_audio_abr` on it, and flags each
entry already in the download history (`already_downloaded`) so the UI
pre-selects only the new ones. A transient extraction failure is retried, then
surfaces as **503** (retryable) vs **422** (a genuinely unsupported URL).

### `POST /api/autotag/{identify,search,lyrics,apply}`

Audio auto-tagging against the Apple Music (iTunes) / Deezer / MusicBrainz
catalogue. `identify` matches a downloaded file, `search` queries by
artist/title, `lyrics` previews the LRCLIB match (when the lyrics setting is on),
and `apply` writes the chosen tags + cover art with `mutagen` (mp3/m4a/flac
native, opus/ogg/wav text-only) — optionally embedding lyrics (+ a synced `.lrc`)
and rewriting the `.nfo` from the tagged metadata. Paths are confined to the
download directory.

## Configuration

Settings are read from `YOINK_`-prefixed environment variables (or a local
`.env`):

| Variable               | Default                  | Description                          |
| ---------------------- | ------------------------ | ------------------------------------ |
| `YOINK_CORS_ORIGINS`   | Vite dev server origins  | JSON list of allowed origins         |
| `YOINK_DOWNLOAD_DIR`   | `<OS Downloads>/Yoink`   | Where downloaded media is written (the OS Downloads folder, localized) |

## Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, router mounting
│   ├── core/               # typed settings, humanize, ffmpeg locate, shared yt-dlp options, SSRF-safe fetch
│   ├── models/            # Pydantic models (JSON contract): media, music, autotag
│   ├── routers/            # info, media, download (WS), history, settings, autotag, music
│   └── services/           # yt-dlp metadata + download, music import + match, autotag (+ lyrics, nfo), VR, history/settings stores, updates
└── requirements.txt
```

> The download contract (the `DownloadRequest` options for container,
> audio format, subtitles, and chapters) and the per-layer reference live in
> [`../docs/backend.md`](../docs/backend.md).
