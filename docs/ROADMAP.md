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

## Phase 2 — Connect frontend ↔ backend ⬜

- ⬜ API client in the frontend (typed `fetch` wrapper)
- ⬜ Wire `handleAnalyze` → `POST /api/info`, populate the preview card
- ⬜ Loading / error states for analysis
- ⬜ Derive format & quality selectors from the real `formats` list

## Phase 3 — Downloads + live progress ⬜

- ⬜ `POST /api/download` starts a yt-dlp job as a background task
- ⬜ yt-dlp `progress_hooks` capture percent / speed / ETA
- ⬜ Stream progress to the UI via WebSockets or SSE
- ⬜ Animate the progress bar from real events
- ⬜ ffmpeg merge for high-quality video + audio formats
- ⬜ OS-agnostic save paths (already scaffolded via `pathlib`)

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
