# Backend

Python + FastAPI, wrapping yt-dlp. Strictly typed throughout.

## Structure

```
backend/
├── app/
│   ├── main.py                 # app factory: FastAPI(), CORS, router mounting, /health
│   ├── core/
│   │   ├── config.py           # typed Settings (CORS origins, download dir) via pydantic-settings
│   │   ├── humanize.py         # shared byte/size formatting
│   │   └── ytdlp_options.py    # shared URL normalize + cookie options
│   ├── models/
│   │   ├── media.py            # Pydantic models (JSON contract): InfoResponse, VideoInfo,
│   │   │                       #   PlaylistInfo, DownloadRequest, progress/terminal events, …
│   │   └── autotag.py          # auto-tag models: TagCandidate, CandidateList, request/response
│   ├── routers/
│   │   ├── info.py             # POST /api/info (video or playlist)
│   │   ├── download.py         # WS /api/ws/download (live progress)
│   │   ├── history.py          # GET/DELETE /api/history(/stats), POST /api/open
│   │   ├── settings.py         # GET/PUT /api/settings, GET /api/version
│   │   └── autotag.py          # POST /api/autotag/{identify,search,apply}
│   └── services/
│       ├── ytdlp_service.py    # typed yt-dlp metadata wrapper (extract_info, download=False)
│       ├── download_service.py # yt-dlp download + typed progress stream
│       ├── autotag_service.py  # Apple Music (iTunes) / Deezer lookup + mutagen tag/cover writing
│       ├── history_store.py    # SQLite persistence (history + stats)
│       ├── settings_store.py   # persisted user settings overrides
│       └── updates.py          # GitHub release update check
└── requirements.txt
```

## The yt-dlp wrapper

`services/ytdlp_service.py` is the only place that touches yt-dlp:

- `extract_info(url)` runs `YoutubeDL.extract_info(url, download=False)`, then
  `sanitize_info` to get a stable, JSON-serializable dict.
- Helpers map raw yt-dlp fields into the typed `VideoInfo` / `MediaFormat`
  models: `_map_format` (codecs → has_video/has_audio, filesize), `_best_thumbnail`,
  `_format_duration` (seconds → `"1h 24m 18s"`).
- It also derives download-capability hints for the UI: `source_lossless` and
  `best_audio_abr` (from the audio formats), `subtitle_langs` (manual subtitle
  codes) and `auto_caption_langs` (auto-generated captions not already in
  `subtitle_langs`), and `has_chapters`.
- A single video is fully resolved; a playlist is listed flat (entries capped at
  200) as `PlaylistInfo`. For a playlist, `_probe_first_entry_audio` resolves
  just the first entry to derive `source_lossless`/`best_audio_abr` (assuming a
  homogeneous list); any failure falls back to `(False, None)`. The route
  returns the unified `InfoResponse`.
- Failures raise `MediaExtractionError`, which the route turns into HTTP 422.

## The download engine

`services/download_service.py` runs the actual download off-thread and streams
typed events (`ProgressEvent` → terminal `CompletedEvent`/`ErrorEvent`) over
`WS /api/ws/download`. `_build_options` translates a `DownloadRequest` into
yt-dlp options:

- **Video:** selects `bestvideo+bestaudio` (capped to `quality`) and merges into
  the requested `container` via `merge_output_format`.
- **Audio:** extracts with `FFmpegExtractAudio` to `audio_format`; `flac`/`wav`
  are lossless (no `preferredquality`), and `m4a` prefers an AAC/m4a source so
  ffmpeg can copy the stream instead of re-encoding.
- **Subtitles:** `embed_subs` + `subtitle_lang` enable `writesubtitles` /
  `writeautomaticsub` and `FFmpegEmbedSubtitle`.
- **Chapters:** `embed_chapters` adds `FFmpegMetadata` (`add_chapters`,
  `add_metadata`).

## Audio auto-tagging

`services/autotag_service.py` tags already-downloaded audio against the Apple
Music catalogue via the **iTunes Search API** — free, key-less, plain HTTPS over
stdlib `urllib` (no new dependencies; `mutagen` ships with yt-dlp):

- `identify(path)` parses an "Artist - Title" from the filename
  (`guess_from_filename`, stripping trailing tags like "(Official Video)") and
  searches the catalogue.
- `search(artist, title)` is the manual equivalent.
- Both return a `CandidateList` of `TagCandidate`s (best first; covers bumped to
  1000px). Nothing is written until `apply`.
- `apply(request, path)` writes the chosen (and possibly user-edited) tags +
  cover art with `mutagen`: native frames/atoms/pictures for mp3/m4a/flac,
  text-only tags for opus/ogg/wav.

The `/autotag` router endpoints are plain `def` (FastAPI runs the blocking
network/file work in a thread) and confine the client-supplied path to the
download directory (path guard). Failures raise `AutotagError` → HTTP 422.

## API

### `GET /health`

Liveness probe → `{ "status": "ok", "app": "Yoink Backend" }`.

### `POST /api/info`

Request body (`InfoRequest`):

```json
{ "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }
```

Response (`VideoInfo`, abridged):

```json
{
  "id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "duration": 213.0,
  "duration_string": "3:33",
  "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
  "formats": [
    { "format_id": "137", "ext": "mp4", "resolution": "1080p", "has_video": true, "has_audio": false }
  ]
}
```

- Invalid URL → `422` from Pydantic validation.
- Extraction failure → `422` with `detail: "Could not extract media info: …"`.

### `POST /api/autotag/identify` · `/search` · `/apply`

Audio auto-tagging against the user-selected catalogue — Apple Music (iTunes
Search API) or Deezer, both free and key-less (`settings.autotag_source`):

- `identify` (`{ "path": … }`) and `search` (`{ "artist": …, "title": … }`)
  both return a `CandidateList` of matches.
- `apply` (`ApplyRequest`: `path` + the chosen `title`/`artist`/`album`/`year`/
  `track_number`/`cover_url`) writes the tags into the file and returns
  `ApplyResponse` (`ok`, `embedded_cover`).
- `identify`/`apply` resolve `path` within the download dir → `400`/`403`/`404`
  if it's invalid, outside, or missing. Lookup/write failures → `422`.

## Configuration

`YOINK_`-prefixed env vars (or a local `.env`):

| Variable             | Default                 | Description                   |
| -------------------- | ----------------------- | ----------------------------- |
| `YOINK_CORS_ORIGINS` | Vite dev server origins | Allowed CORS origins          |
| `YOINK_DOWNLOAD_DIR` | `~/Downloads/Yoink`     | Where media is written        |
| `YOINK_API_PREFIX`   | `/api`                  | API route prefix              |

## Run

```bash
cd backend
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload      # http://127.0.0.1:8000  (Swagger UI at /docs)
```

## More

History/stats (`/api/history`), settings (`/api/settings`), the update check
(`/api/version`), and revealing files (`/api/open`) round out the API. See the
[roadmap](ROADMAP.md) for what's done and what's next.
