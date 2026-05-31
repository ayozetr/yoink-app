# Yoink — Roadmap

Status of the project: what's done and what's next.

Legend: ✅ done · 🚧 in progress · ⬜ planned

## Phase 0 — Foundations ✅

- ✅ Frontend scaffolded with Vite (React 19 + TypeScript)
- ✅ Tailwind CSS v3 configured (`tailwind.config.js`, `postcss.config.js`, global CSS)
- ✅ `lucide-react` icons
- ✅ `npm audit` clean (0 vulnerabilities)
- ✅ Initial mockup decomposed into a scalable architecture
  (`components/ui`, `components/layout`, `features/`, `types/`)
- ✅ Shared domain types mirroring the backend JSON contract
- ✅ Git repository synced to `git@github.com:ayozetr/yoink-app.git`

## Phase 1 — Backend metadata 🚧

- ✅ FastAPI app structure (typed: main, core, models, routers, services)
- ✅ Python `venv` + pinned `requirements.txt` (fastapi, uvicorn, yt-dlp, pydantic)
- ✅ yt-dlp wrapper with `download=False` metadata extraction
- ✅ `POST /api/info` endpoint (title, duration, thumbnail, formats)
- ✅ `/health` liveness probe
- ✅ CORS configured for the local Vite dev server
- ✅ Project documentation (CLAUDE.md, /docs, READMEs)
- ⬜ Unit tests for the yt-dlp service and the `/api/info` route

## Phase 2 — Connect frontend ↔ backend ✅

- ✅ API client in the frontend (typed `fetch` wrapper, `src/lib/api.ts`)
- ✅ Wire `handleAnalyze` → `POST /api/info`, populate the preview card
- ✅ Loading / error states for analysis (cancels in-flight requests)
- ✅ Derive format & quality selectors from the real `formats` list
- ✅ TS types mirror the Pydantic contract 1:1 (snake_case, incl. `formats`)

## Phase 3 — Downloads + live progress ✅

- ✅ `WS /api/ws/download` starts a yt-dlp job (run off-thread via
  `asyncio.to_thread`); progress is streamed over the same socket
- ✅ yt-dlp `progress_hooks` capture percent / speed / ETA, bridged to the
  event loop through an `asyncio.Queue`
- ✅ Stream progress to the UI via WebSockets (typed event contract)
- ✅ Animate the progress bar from real events (download → processing → done)
- ✅ ffmpeg merge for high-quality video + audio (`merge_output_format=mp4`);
  MP3 extraction for audio-only
- ✅ OS-agnostic save paths to `~/Downloads/Yoink` via `pathlib`

> Cancel/retry of in-flight jobs is deferred to Phase 4.

## Phase 4 — History & persistence ⬜

- ⬜ Persist completed/failed downloads (replace placeholder history data)
- ⬜ Real download statistics (count, total transferred)
- ⬜ "Open folder" action wired to the OS file manager
- ⬜ Cancel / retry downloads

## Phase 5 — Packaging & polish ⬜

- ⬜ One-command local startup (frontend + backend)
- ⬜ Desktop packaging (e.g. Tauri/Electron) for Linux and Windows
- ⬜ Settings UI (default download dir, default format/quality)
- ⬜ End-to-end tests
