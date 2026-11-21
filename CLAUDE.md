# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What is Yoink

Yoink is a **local** desktop/web app for downloading high-fidelity video and
audio from multiple platforms. The download engine is **exclusively
[yt-dlp](https://github.com/yt-dlp/yt-dlp)**; [ffmpeg](https://ffmpeg.org/) is
used to merge high-quality video + audio formats.

## Architecture (local microservice)

Two layers communicating asynchronously:

- **Frontend** — React + TypeScript + Tailwind CSS (Vite). A reactive, clean
  UI. Its job: show previews, let the user pick format/quality, and
  reflect download progress. Lives at the repo root (`src/`). The v4 UI is a
  flat, de-boxed "Flat Minimal" look (Gloock titles + Inter), organised into
  modular tabs (Inicio/Cola/Historial/Ajustes), dark by default with a light theme.
- **Backend** — native **Rust** (`yoink-core`, axum), runs locally
  (`backend-rs/`). Shells out to the bundled `yt-dlp` + `ffmpeg` binaries,
  manages the local filesystem, and streams download progress. No Python
  runtime. (The original Python/FastAPI backend lives on the `legacy` branch.)

### Communication contract (strict)

- **Metadata (REST):** when the user pastes a URL, the frontend calls the backend.
  The backend runs yt-dlp with `download=False` and returns an `InfoResponse`
  that is **either** a single video (title, thumbnail, formats, plus
  `source_lossless`/`best_audio_abr`/`has_audio`/`subtitle_langs`/`has_chapters`,
  and an `is_vr`/`vr_layout` immersive-video heuristic) **or** a flat playlist listing
  (entries with title/duration/url, each flagged `already_downloaded` when its URL is
  already a completed download — *playlist sync* pre-selects only the new ones).
  Endpoint: `POST /api/info` — a transient
  extraction failure (anti-bot 403 / network blip) is retried before surfacing as
  503 (retryable) vs 422 (a genuinely unsupported URL).
- **Search (REST):** typing a query (not a URL) in the field hits
  `GET /api/search?q=&source=youtube|soundcloud`, a flat `ytsearch`/`scsearch`
  returning matching tracks for the live dropdown (a YouTube/SoundCloud source
  selector lives inside the URL field); picking one analyzes it via `POST /api/info`.
- **Music import (REST):** pasting a Spotify/Deezer/Apple/Tidal/Amazon URL hits
  `POST /api/music/resolve`, which **keyless**ly turns it into a `MusicImportInfo`
  (track/album/playlist + per-track title/artist/duration/cover; `POST /api/music/cover`
  fills a missing per-track cover lazily). The card (and the queue, for a pasted
  music URL) then calls `POST /api/music/match` per track to rank a YouTube video
  (spotDL-ported scorer), downloads it via the normal WS flow, and auto-tags it with
  the *exact* source metadata. Audio is never taken from the source — only its metadata.
- **Download & progress (WebSockets):** on "Download", the frontend opens a
  socket to `WS /api/ws/download` and sends the request (`DownloadRequest`:
  `kind`/`quality`, output `container`, `audio_format`, `embed_subs`/
  `subtitle_lang`/`embed_chapters`, `trim_start`/`trim_end` to clip a range, and
  `is_vr`/`vr_layout` to tag the output as immersive — a projection name suffix
  plus injected Spherical Video V2 metadata — or `auto_vr` to detect + tag VR
  with no preview, used by the queue). The backend runs the yt-dlp job
  off-thread
  (`asyncio.to_thread`) and streams typed events — `progress` (percent, speed,
  ETA) → terminal `completed`/`error` — back over the same socket to animate the
  progress bar. When the `normalize_audio` setting is on (off by default), an
  audio download is loudness-normalized to -14 LUFS (EBU R128) with a two-pass
  ffmpeg `loudnorm` before it's finalized and auto-tagged.
- **Audio auto-tagging (REST):** after an audio download the frontend looks the
  file up in the Apple Music, Deezer or MusicBrainz catalogue — or `auto`, which
  cascades through them (Settings, `autotag_source`) — and writes tags + cover
  art via `POST /api/autotag/{identify,search,apply}`; nothing is written until
  `apply`. When `fetch_lyrics` is on, `POST /api/autotag/lyrics` previews the
  LRCLIB match in the card and `apply` embeds the lyrics (plus an optional synced
  `.lrc` sidecar); `apply` also rewrites the `.nfo` from the tagged metadata. With
  the `music_folders` setting on, `apply` then **relocates** the tagged track into a
  media-server music layout (`<download dir>/<Artist>/<Album>/Artist - Title.ext`,
  the shared Jellyfin/Plex/Navidrome convention — sidecars move with it, history
  path updated) and, when `.nfo` is on too, writes folder-level `album.nfo`/`artist.nfo`.
- **Update check (REST):** with the *"check for updates automatically"* setting on
  (`AppSettings.check_updates`, **on by default**; the app only — yt-dlp stays
  owner-managed), the app checks the latest GitHub release on launch; if newer it
  shows an in-app banner + a desktop notification and can **self-update in place**
  via the Tauri updater (a live-progress "Downloading…" popup). `GET /api/release-notes`
  returns a `WhatsNew` (a list of per-version release `body`s — each trimmed to the part
  before a hidden `<!-- /whatsnew -->` marker) for the first-launch-after-update "What's
  new" popup; with `?since=<version>` (the version last run, remembered in the
  `yoink-last-seen-version` localStorage key) it's **cumulative** — every release in
  `(since, current]`, newest first — so skipping versions doesn't hide their notes.
- **Deep link (`yoink://`, desktop):** the Tauri shell registers a
  `yoink://download?url=<encoded>` scheme so the browser — or the **"Send to Yoink"
  (beta)** extension in `extension/` — can hand a URL to the running app without going
  through the CORS-locked local API. `main.rs` reads the `url` param, ignores a
  malformed link, and emits a `deep-link` event (a cold-start URL is drained via
  `take_pending_deep_link`); the frontend (`lib/desktop.ts` → `App.tsx`) routes it
  through the same analyze path as drag-and-drop.

The TypeScript types in `src/types/` (`download.ts`, `autotag.ts`, `music.ts`)
are the JSON contract; the Rust structs in `backend-rs/src/` serialize to match
them (serde) — keep both sides in sync. The UI is unchanged from the Python era,
so the endpoint behaviours described above hold; only the implementation moved
to Rust.

## Repository layout

```
.
├── CLAUDE.md                 # this file
├── README.md                 # project overview + quick start
├── docs/                     # architecture, roadmap, per-layer guides
├── src/                      # frontend (React + TS + Tailwind)
│   ├── components/
│   │   ├── layout/           # tabbed app shell (brand + TabBar) + splash
│   │   └── ui/               # reusable primitives (GlassPanel, Button, Select, Toggle, Drawer, Toaster, EditMenu, Markdown, update banner/popups, …)
│   ├── features/
│   │   ├── autotag/          # Apple Music tagging cards (single + playlist batch)
│   │   ├── music/            # keyless music import card (Spotify/Deezer/Apple/Tidal/Amazon)
│   │   ├── downloader/       # URL input (source selector inside the field: YouTube/SoundCloud), preview (incl. VR), playlist, progress
│   │   ├── queue/            # download queue: format picker + expandable music/playlist groups (per-item select), skip/reorder
│   │   ├── history/          # download history + stats (its own tab, editorial list)
│   │   └── settings/         # settings tab (download dir, defaults, bandwidth, cookies, language, theme, SponsorBlock, version + auto-update)
│   ├── i18n/                 # react-i18next setup + 14 lazy-loaded locale files
│   ├── lib/                  # API client (+ runtime backend-port resolve) + download WebSocket + single-download lock + queue store + theme + toast store + search-source pref + VR-layout memory + native dialogs + deep-link/desktop bridge
│   └── types/                # shared domain types (backend JSON contract)
├── extension/                # "Send to Yoink" (beta) browser extension (Firefox + Chromium) — fires the yoink:// deep link
├── backend/
│   └── vendor/ffmpeg/        # bundled minimal ffmpeg+ffprobe (gitignored; scripts/build_ffmpeg.sh)
└── backend-rs/              # native Rust backend (yoink-core, axum + yt-dlp/ffmpeg)
    ├── Cargo.toml
    └── src/
        ├── main.rs           # app factory + all HTTP/WS routes; download, history (rusqlite), settings, logs, info/search, yt-dlp retry+cookie helpers
        ├── matching.rs       # spotDL-ported YouTube match ranking (unit-test-pinned to Python)
        ├── music.rs          # keyless music import: Spotify/Deezer/Apple/Tidal/Amazon + Deezer enrich (rate-limit gate)
        ├── autotag.rs        # catalogue lookups (Apple/Deezer/MusicBrainz) + lyrics (LRCLIB) + lofty tag writing
        ├── nfo.rs            # Kodi/Jellyfin .nfo sidecars (movie / musicvideo + folder album/artist)
        ├── library.rs        # music-folder relocation (Artist/Album layout) + rename-to-tagged
        ├── vr.rs             # VR detection + Spherical Video V2/V1 box injection + MKV StereoMode
        └── audio_normalize.rs # two-pass ffmpeg loudnorm (-14 LUFS) + HLS trim (with ffmpeg timeouts)
```

## Common commands

### Everything at once (recommended)

```bash
python scripts/setup.py    # one-time: cargo build (backend) + npm install (frontend)
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

### Backend (`backend-rs/`)

The backend is **native Rust** (`yoink-core`, axum) — it shells out to the
bundled `yt-dlp` + `ffmpeg` binaries. No Python runtime.

```bash
cd backend-rs
cargo run                 # serve the API on :8756 (set YOINK_PORT to change)
cargo build --release     # optimized binary at target/release/yoink-core
cargo fmt && cargo clippy  # format + lint (CI gates on both)
cargo test                # unit tests (e.g. the spotDL matcher parity test)
```

The backend finds `yt-dlp` on PATH (or `YOINK_YTDLP`) and ffmpeg at
`YOINK_FFMPEG` (or PATH); `scripts/dev.py` points it at `backend/vendor/ffmpeg`
when present.

### Desktop app (Tauri)

```bash
bash scripts/build_ffmpeg.sh      # once: build a minimal ffmpeg+ffprobe (~33 MB total)
# bash scripts/build_ffmpeg.sh --windows   # cross-compile the Windows .exe (mingw-w64)
# python scripts/fetch_ffmpeg.py  # fallback: download BtbN LGPL prebuilts (~336 MB)
python scripts/build_core.py      # build yoink-core + fetch yt-dlp + assemble the core resource
npm run tauri build               # produce desktop installers in src-tauri/target
```

The Tauri shell (`src-tauri/`) loads the built frontend and, on startup, spawns
the bundled **`yoink-core`** (the native Rust backend) from the `core` Tauri
`resources` folder — assembled by `scripts/build_core.py` with `yoink-core`,
the pinned standalone `yt-dlp` (version in `scripts/ytdlp-version.txt`), and the
minimal `ffmpeg`/`ffprobe`. `main.rs` sets `YOINK_YTDLP`/`YOINK_FFMPEG` to the
sibling binaries, so the shipped app needs no system Python, yt-dlp or ffmpeg.
`yoink-core` does double duty: launched with no arguments it serves the API;
launched with arguments it runs the **CLI** (`src/cli.rs`) — the Linux
`.deb`/`.rpm` ship a `/usr/bin/yoink-cli` wrapper (`src-tauri/yoink-cli`) that
forwards to it, and `scripts/yoink` is the dev wrapper. See [`docs/cli.md`](docs/cli.md).
Prerequisites: Rust toolchain and, on Linux, `webkit2gtk` (4.1). Icons are
generated with `npm run tauri icon`. See `docs/releasing.md` for the full
release flow and `docs/THIRD_PARTY_LICENSES.md` for the ffmpeg attribution.
Releases build on GitHub Actions (`.github/workflows/release.yml`): Linux +
Windows, signed, with the Windows ffmpeg cross-compiled on the Linux runner.

## Conventions

- **Tailwind v4** (CSS-first, no `tailwind.config.js`): the `@theme` mapping and
  design tokens live in `src/index.css`; PostCSS uses `@tailwindcss/postcss`. The
  palette is CSS custom properties (`--c-canvas/surface/line/fg/accent/…`) exposed
  as utilities, **dark by default** with a light theme under
  `html[data-theme="light"]` (preference in Settings, persisted as `yoink-theme`).
- **Fonts:** self-hosted via `@fontsource` (bundled, offline) — Gloock for display
  titles (`font-display`), Inter for the UI (`font-sans`).
- **Frontend:** function components, feature-folder structure. Reusable visuals
  go in `components/ui`; screen-specific logic stays in `features/`.
- **Backend:** native Rust (`backend-rs`, edition 2021). `cargo fmt` + `cargo
  clippy` clean (CI gates on `clippy -D warnings`). OS-agnostic paths via
  `std::path`. Rust structs serialize (serde) to the TS JSON contract.
- **Security:** keep `npm audit` at **0 vulnerabilities**.
- **Icons:** `lucide-react`.
- **i18n:** UI strings go through `react-i18next` (14 languages in
  `src/i18n/locales`); the language is auto-detected from the system and
  overridable in Settings (persisted under the `yoink-lang` localStorage key).
  Backend error messages stay in **English**; the frontend translates its own UI.

## Git conventions

- Remote: `git@github.com:ayozetr/yoink-app.git` (SSH).
- Commit messages in **English**, with a subject **and a body**.
- **No `Co-Authored-By` trailer.**
- Author identity: **Ayoze Torres** `<ayozetr@users.noreply.github.com>`.
- License: **AGPL-3.0-or-later**. New source files start with the two-line SPDX
  header (`SPDX-License-Identifier: AGPL-3.0-or-later` + copyright) — see
  `CONTRIBUTING.md`.

## Status

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what's done and what's next.
