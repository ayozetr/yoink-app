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

## Phase 1 — Backend metadata ✅

- ✅ FastAPI app structure (typed: main, core, models, routers, services)
- ✅ Python `venv` + pinned `requirements.txt` (fastapi, uvicorn, yt-dlp, pydantic)
- ✅ yt-dlp wrapper with `download=False` metadata extraction
- ✅ `POST /api/info` endpoint (title, duration, thumbnail, formats)
- ✅ `/health` liveness probe
- ✅ CORS configured for the local Vite dev server
- ✅ Project documentation (CLAUDE.md, /docs, READMEs)
- ✅ Unit tests for the services and routes (`backend/tests`, pytest)

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

## Phase 4 — History & persistence ✅

- ✅ Persist completed/failed downloads in SQLite (`~/.yoink/history.db`,
  stdlib `sqlite3`, no new deps); `GET /api/history`
- ✅ Real download statistics (count, total transferred); `GET /api/history/stats`
- ✅ "Open folder" wired to the OS file manager (`POST /api/open`,
  xdg-open/open/explorer), constrained to the download dir
- ✅ Cancel (close the socket → `threading.Event` aborts the job) and retry
  (re-issue the last selection) from the UI
- ✅ Sidebar history + stats load real backend data and refresh after each job

## Extras (beyond the original roadmap) ✅

- ✅ **Playlists:** `POST /api/info` returns a flat playlist listing; the UI
  shows a `PlaylistCard` with per-item checkboxes and downloads the selected
  items sequentially ("X of N" progress)
- ✅ **Cookies** for sign-in-only content, via settings (`YOINK_COOKIES_FROM_BROWSER`
  or `YOINK_COOKIES_FILE`), applied to both metadata and downloads
- ✅ **URL normalization** (e.g. TikTok `/photo/` → `/video/`)
- ✅ **Clear history** button (`DELETE /api/history`)

## Phase 5 — Packaging & polish ✅

- ✅ One-command local startup (`scripts/dev.py` runs backend + frontend;
  `scripts/setup.py` for venv + deps)
- ✅ Desktop packaging with Tauri (`src-tauri/`) for **Linux & Windows**: the
  FastAPI backend **and ffmpeg/ffprobe** ship as a PyInstaller sidecar the app
  launches on startup (self-contained — no Python/ffmpeg needed). Build with
  `python scripts/fetch_ffmpeg.py && python scripts/build_backend.py && npm run tauri build`.
  Linux: `.AppImage`/`.deb`/`.rpm`; Windows: `.msi`/NSIS `.exe`. See
  [`releasing.md`](releasing.md)
- ✅ Settings UI (download dir, default format/quality, cookies) — persisted
  via `GET`/`PUT /api/settings` to `<data_dir>/settings.json`
- ✅ End-to-end tests (Playwright, `e2e/`, mocked API)

## Phase 6 — Self-update 🚧

- ✅ Show the current app version in the Settings modal (injected from
  package.json at build time)
- ✅ "Check for updates" button → `GET /api/version` queries the GitHub
  Releases API and reports whether a newer release exists
- ✅ Fallback "Actualizar" link that opens the GitHub release page when an
  update is available
- ⬜ In-app download & install via `tauri-plugin-updater` (signed artifacts +
  `latest.json`). Note: on Linux the updater only supports AppImage (not
  `.deb`/`.rpm`); it works for the Windows `.exe`/`.msi`.
- ⬜ Publish signed update artifacts + `latest.json` in the release flow

> The update check needs the GitHub repo to be **public** (the unauthenticated
> API returns 404 for private repos).

## Phase 7 — Android (experimental) ⬜

The frontend ports to Android easily (Tauri v2 mobile loads the React UI in a
WebView). The hard part is the engine: the PyInstaller backend sidecar does
**not** work on Android (no spawnable binaries, no `externalBin`), so the
local HTTP/WebSocket server must be replaced. Three routes:

- ⬜ **Embed Python (Chaquopy) + ffmpeg-kit**: run yt-dlp in-process and drive
  it via native Tauri commands instead of REST/WS to `localhost`. Keeps Python.
- ⬜ **Native yt-dlp lib (`youtubedl-android`) + ffmpeg-kit**: the approach the
  Seal app uses; leaves Python behind for a Kotlin/Java layer.
- ⬜ **Thin client**: APK is just the UI talking to a remote backend (the
  desktop FastAPI on a PC/NAS). Minimal work, but no longer fully "local".
- ⬜ Android toolchain + plumbing: Android SDK/NDK/JDK, `tauri android`,
  scoped-storage save paths, runtime permissions.

> Notes: functionally proven on Android (cf. the Seal app = yt-dlp + ffmpeg in
> an APK). Distribute via direct APK / F-Droid — Google Play typically rejects
> YouTube downloaders. This is a separate mini-project, not an extension of the
> desktop packaging.
