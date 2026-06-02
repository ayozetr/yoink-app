# Yoink Media Downloader

[![Release](https://img.shields.io/github/v/release/ayozetr/yoink-app?label=release&color=7c3aed)](https://github.com/ayozetr/yoink-app/releases/latest)
![Platforms](https://img.shields.io/badge/platforms-Linux%20%C2%B7%20Windows-2563eb)
![Tauri](https://img.shields.io/badge/Tauri-2-24C8DB?logo=tauri&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-Python-009688?logo=fastapi&logoColor=white)
![Powered by yt-dlp](https://img.shields.io/badge/powered%20by-yt--dlp-cc0000)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)
[![React Doctor](https://www.react.doctor/share/badge?p=yoink&s=92&e=1&w=11&f=6)](https://www.react.doctor/share?p=yoink&s=92&e=1&w=11&f=6)

Yoink is a **local** desktop/web app for downloading high-fidelity video and
audio from many platforms, powered exclusively by
[yt-dlp](https://github.com/yt-dlp/yt-dlp) (with [ffmpeg](https://ffmpeg.org/)
for merging high-quality streams).

It is split into two layers that communicate asynchronously:

- **Frontend** — React + TypeScript + Tailwind CSS (Vite). A reactive, dark-mode
  UI that shows previews, lets you pick format/quality, and reflects download
  progress in real time.
- **Backend** — Python + FastAPI (in `backend/`). Wraps yt-dlp, manages the local
  filesystem, and invokes ffmpeg. Metadata is served over REST (`POST /api/info`);
  downloads stream live progress to the UI over a WebSocket (`/api/ws/download`).

## Features

- **Analyze any URL** → preview (title, thumbnail, duration) with the real
  available formats. ~1800 sites via yt-dlp.
- **Live downloads** over WebSocket (percent / speed / ETA); MP4 (ffmpeg merge)
  or MP3 extraction. **Cancel** and **retry** supported.
- **Playlists** — pick which items to download with checkboxes; they download
  sequentially with "X of N" progress.
- **History & stats** persisted locally (SQLite), with open-folder and clear.
- **Settings** — download folder, default format/quality, and cookies
  (browser or `cookies.txt`) for sign-in-only content.
- **Update check** against the latest GitHub release.
- **Self-contained desktop app** (Tauri, Linux & Windows): bundles the backend
  **and ffmpeg** as a sidecar — no Python or ffmpeg install needed.

## Quick start

```bash
python scripts/setup.py    # one-time: venv + backend deps + npm install
python scripts/dev.py      # run backend (:8756) + frontend (:5173) together
```

Then open <http://localhost:5173>. For development you need **ffmpeg** on your
PATH; the packaged desktop app bundles it. See [`CLAUDE.md`](CLAUDE.md) for
per-layer commands.

### Desktop build (Tauri)

```bash
python scripts/fetch_ffmpeg.py    # once: download ffmpeg+ffprobe (LGPL) to bundle
python scripts/build_backend.py   # bundle backend + ffmpeg as a PyInstaller sidecar
npm run tauri build               # installers in src-tauri/target/release/bundle
```

Prerequisites: Rust toolchain and, on Linux, `webkit2gtk` (4.1); on Windows,
WebView2 + MSVC build tools. Full flow in [`docs/releasing.md`](docs/releasing.md).

## Project structure

```
src/                      # frontend (React + TS + Tailwind)
├── components/{layout,ui}
├── features/
│   ├── downloader/       # URL input, preview, playlist, progress (main column)
│   ├── history/          # download history + stats (sidebar)
│   └── settings/         # settings modal (download dir, defaults, cookies, version)
├── lib/                  # API client + download WebSocket
└── types/                # shared domain types (mirror the backend JSON contract)

backend/                  # FastAPI + yt-dlp engine (see backend/README.md)
src-tauri/                # Tauri desktop shell
scripts/                  # setup.py, dev.py, fetch_ffmpeg.py, build_backend.py
e2e/                      # Playwright end-to-end tests
```

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — high-level guide and conventions
- [`docs/`](docs/) — architecture, per-layer guides, the [roadmap](docs/ROADMAP.md),
  the [release process](docs/releasing.md) and
  [third-party licenses](docs/THIRD_PARTY_LICENSES.md)
