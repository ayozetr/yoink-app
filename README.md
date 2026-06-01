# Yoink

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
- **Desktop app** (Tauri) bundling the backend as a sidecar — no Python needed.

## Quick start

```bash
python scripts/setup.py    # one-time: venv + backend deps + npm install
python scripts/dev.py      # run backend (:8000) + frontend (:5173) together
```

Then open <http://localhost:5173>. (ffmpeg must be installed for high-quality
video+audio merges.) See [`CLAUDE.md`](CLAUDE.md) for per-layer commands.

### Desktop build (Tauri)

```bash
python scripts/build_backend.py   # bundle the backend as a PyInstaller sidecar
npm run tauri build               # installers in src-tauri/target/release/bundle
```

Prerequisites: Rust toolchain and, on Linux, `webkit2gtk` (4.1).

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
scripts/                  # setup.py, dev.py, build_backend.py
e2e/                      # Playwright end-to-end tests
```

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — high-level guide and conventions
- [`docs/`](docs/) — architecture, per-layer guides, the [roadmap](docs/ROADMAP.md)
  and the [release process](docs/releasing.md)
