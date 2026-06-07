# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What is Yoink

Yoink is a **local** desktop/web app for downloading high-fidelity video and
audio from multiple platforms. The download engine is **exclusively
[yt-dlp](https://github.com/yt-dlp/yt-dlp)**; [ffmpeg](https://ffmpeg.org/) is
used to merge high-quality video + audio formats.

## Architecture (local microservice)

Two layers communicating asynchronously:

- **Frontend** — React + TypeScript + Tailwind CSS (Vite). A reactive, clean,
  dark-mode UI. Its job: show previews, let the user pick format/quality, and
  reflect download progress. Lives at the repo root (`src/`).
- **Backend** — Python + FastAPI, runs locally (`backend/`). Wraps yt-dlp,
  manages the local filesystem, and invokes ffmpeg. Strictly typed.

### Communication contract (strict)

- **Metadata (REST):** when the user pastes a URL, the frontend calls FastAPI.
  The backend runs yt-dlp with `download=False` and returns an `InfoResponse`
  that is **either** a single video (title, thumbnail, formats, plus
  `source_lossless`/`best_audio_abr`/`subtitle_langs`/`has_chapters`) **or** a
  flat playlist listing (entries with title/duration/url). Endpoint: `POST /api/info`.
- **Search (REST):** typing a query (not a URL) in the field hits
  `GET /api/search?q=`, which runs a flat `ytsearch` and returns matching videos
  for the live dropdown; picking one analyzes it via `POST /api/info`.
- **Download & progress (WebSockets):** on "Download", the frontend opens a
  socket to `WS /api/ws/download` and sends the request (`DownloadRequest`:
  `kind`/`quality`, output `container`, `audio_format`, `embed_subs`/
  `subtitle_lang`/`embed_chapters`, and `trim_start`/`trim_end` to clip a
  range). The backend runs the yt-dlp job off-thread
  (`asyncio.to_thread`) and streams typed events — `progress` (percent, speed,
  ETA) → terminal `completed`/`error` — back over the same socket to animate the
  progress bar.
- **Audio auto-tagging (REST):** after an audio download the frontend looks the
  file up in the Apple Music, Deezer or MusicBrainz catalogue — or `auto`, which
  cascades through them (Settings, `autotag_source`) — and writes tags + cover
  art via `POST /api/autotag/{identify,search,apply}`; nothing is written until
  `apply`.

The TypeScript types in `src/types/download.ts` mirror the Pydantic models in
`backend/app/models/media.py` (and `src/types/autotag.ts` ↔
`backend/app/models/autotag.py`) — keep both sides in sync.

## Repository layout

```
.
├── CLAUDE.md                 # this file
├── README.md                 # project overview + quick start
├── docs/                     # architecture, roadmap, per-layer guides
├── src/                      # frontend (React + TS + Tailwind)
│   ├── components/
│   │   ├── layout/           # app shell, background glow
│   │   └── ui/               # reusable primitives (GlassPanel, Button, Select, EditMenu, …)
│   ├── features/
│   │   ├── autotag/          # Apple Music tagging cards (single + playlist batch)
│   │   ├── downloader/       # URL input, preview, playlist, progress (main column)
│   │   ├── history/          # download history + stats (sidebar)
│   │   └── settings/         # settings modal (download dir, defaults, cookies, language, SponsorBlock, version)
│   ├── i18n/                 # react-i18next setup + en/es locale strings
│   ├── lib/                  # API client + download WebSocket + native dialogs
│   └── types/                # shared domain types (backend JSON contract)
└── backend/                  # FastAPI + yt-dlp engine
    └── app/
        ├── main.py           # app factory, CORS, router mounting
        ├── core/config.py    # typed settings (CORS, download dir)
        ├── models/media.py   # Pydantic models (JSON contract)
        ├── models/autotag.py  # auto-tagging models (TagCandidate, CandidateList, …)
        ├── core/humanize.py   # shared byte/size formatting
        ├── core/ytdlp_options.py      # shared URL normalize + cookie options
        ├── routers/info.py    # POST /api/info (video or playlist), GET /api/search (YouTube)
        ├── routers/download.py        # WS /api/ws/download (live progress)
        ├── routers/history.py         # GET/DELETE /api/history(/stats), POST /api/open
        ├── routers/settings.py        # GET/PUT /api/settings, GET /api/version + /api/ytdlp-version
        ├── routers/autotag.py         # POST /api/autotag/{identify,search,apply}
        ├── routers/media.py           # GET /api/thumbnail (host-guarded image proxy)
        ├── services/ytdlp_service.py  # typed yt-dlp metadata wrapper
        ├── services/download_service.py  # yt-dlp download + progress stream
        ├── services/threads_extractor.py  # custom Threads (Meta) yt-dlp extractor
        ├── services/autotag_service.py # Apple Music lookup + mutagen tag writing
        ├── services/history_store.py  # SQLite persistence (history + stats)
        ├── services/settings_store.py # persisted user settings overrides
        └── services/updates.py        # GitHub release update check
```

## Common commands

### Everything at once (recommended)

```bash
python scripts/setup.py    # one-time: venv + backend deps + npm install
python scripts/dev.py      # run backend (:8756) + frontend (:5173) together
# python scripts/dev.py --api-port 8010 --web-port 5180   # custom ports
```

`dev.py` points the frontend at the chosen backend port and stops both on
Ctrl+C. The per-layer commands below are still available for working on one
side in isolation.

### Frontend (repo root)

```bash
npm install
npm run dev      # dev server (http://localhost:5173)
npm run build    # type-check (tsc -b) + production build
npm run lint     # eslint
npm run test:e2e # Playwright E2E (mocked API; first run: npx playwright install chromium)
```

### Backend (`backend/`)

> Use **Python 3.13** (not 3.14): yt-dlp's `curl_cffi` impersonation — needed to
> get past Cloudflare/anti-bot 403s — only works on a Python with compatible
> `curl_cffi` wheels, and 3.14's newer OpenSSL fingerprint is itself blocked by
> some sites. `scripts/setup.py` selects 3.13 automatically (via uv, isolated).

```bash
python3.13 -m venv .venv          # or: uv venv --python 3.13 .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload    # http://127.0.0.1:8756  (docs at /docs)

pip install -r requirements-dev.txt   # test deps (pytest, httpx)
pytest                                # run the backend test suite
```

### Desktop app (Tauri)

```bash
python scripts/fetch_ffmpeg.py    # once: download ffmpeg+ffprobe (LGPL) to bundle
python scripts/build_backend.py   # bundle the backend (+ffmpeg) as a PyInstaller sidecar
npm run tauri build               # produce desktop installers in src-tauri/target
```

The Tauri shell (`src-tauri/`) loads the built frontend and launches the
bundled backend sidecar on startup. The sidecar embeds ffmpeg/ffprobe (wired to
yt-dlp via `ffmpeg_location`), so the shipped app needs no system ffmpeg.
Prerequisites: Rust toolchain and, on Linux, `webkit2gtk` (4.1). Icons are
generated with `npm run tauri icon`. See `docs/releasing.md` for the full
release flow and `docs/THIRD_PARTY_LICENSES.md` for the ffmpeg LGPL attribution.

## Conventions

- **Tailwind v3** with `tailwind.config.js` + `postcss.config.js`. Shared color
  tokens (`canvas`, `surface`, `surface-hover`) live in the Tailwind theme.
- **Frontend:** function components, feature-folder structure. Reusable visuals
  go in `components/ui`; screen-specific logic stays in `features/`.
- **Backend:** strictly typed Python (`from __future__ import annotations`,
  explicit return types). OS-agnostic paths via `pathlib` (Linux + Windows).
  Dependencies isolated in a `venv`.
- **Security:** keep `npm audit` at **0 vulnerabilities**.
- **Icons:** `lucide-react`.
- **i18n:** UI strings go through `react-i18next` (English + Spanish in
  `src/i18n/locales`); the language is auto-detected from the system and
  overridable in Settings (persisted under the `yoink-lang` localStorage key).
  Backend error messages stay in **English**; the frontend translates its own UI.

## Git conventions

- Remote: `git@github.com:ayozetr/yoink-app.git` (SSH).
- Commit messages in **English**, with a subject **and a body**.
- **No `Co-Authored-By` trailer.**
- Author identity: **Ayoze Torres** `<ayozetr@users.noreply.github.com>`.

## Status

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what's done and what's next.
