# Architecture

Yoink is a **local microservice**: a reactive web UI talking to a local Python
engine that wraps yt-dlp.

```
┌────────────────────────┐         REST: POST /api/info          ┌──────────────────────────┐
│      Frontend          │ ───────────────────────────────────▶ │        Backend            │
│  React + TS + Tailwind │                                       │     FastAPI (Python)      │
│      (Vite, :5173)     │ ◀─────────────────────────────────── │        (:8000)            │
│                        │     clean JSON (title, formats…)      │                           │
│  - URL input           │                                       │  - yt-dlp wrapper         │
│  - Preview card        │       WS: live download progress      │  - ffmpeg merge           │
│  - Progress bar        │ ◀╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ │  - filesystem (pathlib)   │
│  - History sidebar     │       (percent, speed, ETA)           │                           │
└────────────────────────┘                                       └──────────────────────────┘
                                                                  (dashed = WS download stream)
```

## Why two layers

- The browser cannot run yt-dlp or write to arbitrary local folders. A small
  local backend owns the system-level work (process spawning, filesystem,
  ffmpeg) and exposes a clean API.
- The frontend stays a pure view/interaction layer, easy to iterate on.

## Communication contract

### 1. Metadata — REST (implemented)

When the user pastes a URL and clicks **Analyze**:

1. Frontend → `POST /api/info` with `{ "url": "..." }`.
2. Backend runs yt-dlp with `download=False` and normalizes the result.
3. Backend → clean JSON: `title`, `duration`, `duration_string`,
   `thumbnail_url`, a list of `formats`, plus capability hints
   `source_lossless`, `best_audio_abr`, `subtitle_langs`, `auto_caption_langs`,
   and `has_chapters`.
4. Frontend populates the preview card and the format/quality selectors.

For a playlist, the backend additionally resolves the **first entry** to set
`source_lossless` / `best_audio_abr` on the listing, so the playlist UI gates
FLAC/WAV like a single video (assuming a homogeneous playlist).

The JSON shape is defined once in `backend/app/models/media.py` (Pydantic) and
mirrored in `src/types/download.ts` (TypeScript).

### 2. Download & progress — WebSockets (implemented)

When the user clicks **Download**:

1. Frontend opens `WS /api/ws/download` and sends a `DownloadRequest`: `kind`
   and `quality`, the output `container` (mp4/mov/mkv) or `audio_format`
   (mp3/m4a/flac/wav), and the `embed_subs` / `subtitle_lang` / `embed_chapters`
   options.
2. Backend runs the yt-dlp job off-thread (`asyncio.to_thread`).
3. yt-dlp `progress_hooks` emit percent / speed / ETA.
4. Those events stream back over the same socket as typed events.
5. The frontend animates the progress bar from real events until a terminal
   `completed` / `error` event.
6. ffmpeg merges separate video/audio streams (and extracts/embeds audio,
   subtitles, and chapters) as needed.

### 3. Audio auto-tagging — REST (implemented)

After an audio download (single or playlist), the UI offers to tag the file(s)
from the user-selected catalogue — Apple Music (iTunes Search API), Deezer or
MusicBrainz (with cover art from the Cover Art Archive),
both free, key-less and over plain HTTPS via stdlib `urllib` (`autotag_source` in
Settings). The flow is **identify/search → user picks a version and edits →
apply**; nothing is written to the file until **Apply**.

1. `POST /api/autotag/identify` — `{ "path" }`. The backend parses the
   filename's `Artist - Title` and looks it up, returning a `CandidateList` of
   matching releases (single/EP/album, each with cover art).
2. `POST /api/autotag/search` — `{ "artist", "title" }`. Manual catalogue
   search, returning the same `CandidateList`.
3. `POST /api/autotag/apply` — the (possibly user-edited) `TagCandidate` fields
   + `path`. The backend writes tags and cover art with `mutagen` (full tags for
   mp3/m4a/flac; text-only for opus/ogg/wav) and returns an `ApplyResponse`.

All file paths are confined to the download directory (path guard). Models live
in `backend/app/models/autotag.py`, mirrored in `src/types/autotag.ts`.

## Cross-platform notes

- Save paths use `pathlib` so they work natively on Linux and Windows.
- The default download directory is `~/Downloads/Yoink`, overridable via
  `YOINK_DOWNLOAD_DIR`.
- ffmpeg must be on the `PATH` for high-quality merges.
