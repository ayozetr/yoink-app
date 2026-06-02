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

## Phase 8 — Branding, i18n & polish ✅ (→ v0.9.0)

> More immediate than Phase 7 (Android). Grouped by area.

### Branding & naming
- ✅ README title → "Yoink Media Downloader" (+ badges: release, platforms,
  Tauri, React, FastAPI, yt-dlp, license, React Doctor score)
- ✅ App header: "Media Downloader" → "Yoink Media Downloader"
  (`DownloaderHeader.tsx`)
- ✅ Installer/exe metadata: **Copyright** = GitHub user (`© ayozetr`) via Tauri
  `bundle.copyright`. Left `productName = "Yoink"` (changing it renames the
  binary/installer and risks breaking sidecar paths).

### UX fixes
- ✅ **"Developed by ayozetr" link** now opens the profile in the packaged app
  via the Tauri **opener** plugin (`openExternal`), with a `window.open`
  fallback in the dev browser.
- ✅ Cookies hint: "no para vídeos públicos" → "no para **contenido público**"
  (`SettingsModal.tsx`)
- ✅ **Responsive design**: the sidebar + main column stack on narrow windows
  (fluid widths, `lg:` breakpoint); modal scrolls instead of clipping.

### Internationalization (English + Spanish)
- ✅ Translated the UI to **English + Spanish** with `react-i18next` (namespaced
  dictionaries in `src/i18n/locales/`)
- ✅ **Language selector** in Settings (System / Español / English), persisted to
  `localStorage` (`yoink-lang`) via the i18next detector
- ✅ **Detect the system language** (`navigator.language`) as the default
- ✅ Backend error messages → **English**; the frontend shows them as-is and
  handles its own translations separately
- ✅ E2E pin the Playwright locale to `es-ES` so the Spanish assertions stay
  deterministic after i18n

### Legal
- ✅ Added an **MIT LICENSE** (compatible with the bundled LGPL ffmpeg and
  Unlicense yt-dlp, which keep their own licenses)

### Extras shipped in v0.9.0
- ✅ **Native folder picker** for the download dir (Tauri **dialog** plugin) —
  a folder icon at the end of the field opens the OS directory chooser
- ✅ **Custom dropdown** (`Select`) replacing the unstyled native `<select>`
  popup, used for format/quality/language across Settings, preview and playlist
  (dark, `fixed`-positioned so it isn't clipped by the modal)
- ✅ **Custom context menu** (`EditMenu`): minimal Cut/Copy/Paste on text fields
  only, suppressing the webview's native Print/Save-as menu; closes on the
  capture phase so it works inside modals
- ✅ **Security audit**: `npm audit` (0), `pip-audit` (0, bumped pytest to clear
  CVE-2025-71176), `cargo audit` (0 vulns; only transitive GTK3 "unmaintained"
  warnings)
- ✅ **react-doctor** pass (score 92/100): fixed the genuine, behavior-safe
  findings; documented the verified false positives

## Phase 9 — Advanced formats & going public ⬜ (→ v1.0.0)

The 1.0 milestone: richer output formats **and** opening the repo to the world.

### Advanced output formats & quality-aware audio

Today Yoink offers MP4 (video) + MP3 (audio). Expand to give real control, and
be **honest about source quality** (don't inflate lossy sources into "lossless").

### Video containers
- ⬜ Offer **MP4** (default), **MOV**, **MKV** (`merge_output_format`)
- ⬜ MKV power features: **embed subtitles** (`writesubtitles` +
  `FFmpegEmbedSubtitle`), **chapters/metadata** (`FFmpegMetadata`,
  `add_chapters`), and optionally **multiple audio tracks** where the source
  has them (`--audio-multistreams`)
- ⬜ Subtitle language picker (es / en / all)

### Audio formats
- ⬜ Lossy: **MP3**, **M4A** — prefer **M4A** when possible (copy the source
  AAC with no re-encode; truer + faster than MP3)
- ⬜ Lossless: **FLAC**, **WAV** — only offered/meaningful when the source is
  actually lossless

### Source-quality detection (honest lossless)
- ⬜ In `/api/info`, inspect the formats' `acodec`/`abr` → expose
  `source_lossless` (true for flac/alac/wav/pcm…) and the max bitrate
- ⬜ Frontend: enable FLAC/WAV **only when `source_lossless`**; otherwise warn
  ("this source isn't lossless — FLAC would just upscale it") and suggest
  M4A/Opus (the real max quality)
- ⬜ Rationale: YouTube serves lossy (Opus ~160 kbps / AAC); transcoding that to
  FLAC just bloats the file with **no quality gain**. Bandcamp/SoundCloud can be
  genuinely lossless.

### Going public

- ⬜ **Audit the repo + git history for secrets** before flipping it public
  (none expected — the VM credentials live outside the repo — but verify) and
  re-check `.gitignore`
- ⬜ Ensure the **LICENSE** (from v0.9.0) is in place
- ⬜ Polish the README for newcomers: badges (release/license), a screenshot,
  clear install + usage
- ⬜ GitHub repo **description + topics**
- ⬜ **Make the repo public** — also enables the in-app "Check for updates"
  (the unauthenticated GitHub API 404s on private repos)
