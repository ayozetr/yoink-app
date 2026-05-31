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
│  - Preview card        │     WS/SSE: live download progress    │  - ffmpeg merge           │
│  - Progress bar        │ ◀╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ │  - filesystem (pathlib)   │
│  - History sidebar     │       (percent, speed, ETA)           │                           │
└────────────────────────┘                                       └──────────────────────────┘
                                                                  (planned: WS/SSE = dashed)
```

## Why two layers

- The browser cannot run yt-dlp or write to arbitrary local folders. A small
  local backend owns the system-level work (process spawning, filesystem,
  ffmpeg) and exposes a clean API.
- The frontend stays a pure view/interaction layer, easy to iterate on.

## Communication contract

### 1. Metadata — REST (implemented)

When the user pastes a URL and clicks **Analizar**:

1. Frontend → `POST /api/info` with `{ "url": "..." }`.
2. Backend runs yt-dlp with `download=False` and normalizes the result.
3. Backend → clean JSON: `title`, `duration`, `duration_string`,
   `thumbnail_url`, and a list of `formats`.
4. Frontend populates the preview card and the format/quality selectors.

The JSON shape is defined once in `backend/app/models/media.py` (Pydantic) and
mirrored in `src/types/download.ts` (TypeScript).

### 2. Download & progress — WebSockets / SSE (planned)

When the user clicks **Descargar**:

1. Frontend requests a download (chosen format/quality).
2. Backend starts a yt-dlp job in a **background task**.
3. yt-dlp `progress_hooks` emit percent / speed / ETA.
4. Those events stream to the frontend over **WebSockets or SSE**.
5. The frontend animates the progress bar from real events.
6. ffmpeg merges separate video/audio streams when needed.

## Cross-platform notes

- Save paths use `pathlib` so they work natively on Linux and Windows.
- The default download directory is `~/Downloads/Yoink`, overridable via
  `YOINK_DOWNLOAD_DIR`.
- ffmpeg must be on the `PATH` for high-quality merges.
