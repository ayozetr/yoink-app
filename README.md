# Yoink Media Downloader

[![Release](https://img.shields.io/github/v/release/ayozetr/yoink-app?label=release&color=7c3aed)](https://github.com/ayozetr/yoink-app/releases/latest)
![Platforms](https://img.shields.io/badge/platforms-Linux%20%C2%B7%20Windows-2563eb)
![Tauri](https://img.shields.io/badge/Tauri-2-24C8DB?logo=tauri&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-Python-009688?logo=fastapi&logoColor=white)
![Powered by yt-dlp](https://img.shields.io/badge/powered%20by-yt--dlp-cc0000)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/license-CC%20BY--NC--SA%204.0-lightgrey)](LICENSE)
[![React Doctor](https://www.react.doctor/share/badge?p=yoink&s=92&w=26&f=10)](https://www.react.doctor/share?p=yoink&s=92&w=26&f=10)

![Yoink — analyzing a video with the format/quality picker and download history sidebar](docs/screenshot.png)

Yoink is a **local** desktop/web app for downloading high-fidelity video and
audio from many platforms, powered exclusively by
[yt-dlp](https://github.com/yt-dlp/yt-dlp) (with [ffmpeg](https://ffmpeg.org/)
for merging high-quality streams).

It is split into two layers that communicate asynchronously:

- **Frontend** — React + TypeScript + Tailwind CSS (Vite). A reactive, dark-mode
  UI (14 languages) that shows previews, lets you pick the container/format,
  quality, subtitles and chapters, and reflects download progress in real time.
- **Backend** — Python + FastAPI (in `backend/`). Wraps yt-dlp, manages the local
  filesystem, and invokes ffmpeg. Metadata is served over REST (`POST /api/info`);
  downloads stream live progress to the UI over a WebSocket (`/api/ws/download`).

## Features

- **Analyze any URL** (with a **paste-from-clipboard** button) → preview (title,
  thumbnail, duration) with the real available formats. ~1800 sites via yt-dlp.
- **Search from the URL field** — type a query instead of a URL and pick a result
  from the live dropdown (thumbnail, channel, views); a header toggle switches the
  search between **YouTube** and **SoundCloud**.
- **Import from music services** — paste a track/album/playlist URL from
  **Spotify, Deezer, Apple Music, Tidal or Amazon Music** (no account or API key);
  Yoink finds the best YouTube match for each song, downloads the audio, and tags
  it with the *exact* source metadata + cover art. ~99.5% match rate on real
  playlists. The audio is never taken from the service — only its metadata.
- **Live downloads** over WebSocket (percent / speed / ETA), with **cancel**
  and **retry**.
- **Output formats, your choice:**
  - Video — **MP4**, **MOV** or **MKV** (ffmpeg merge), with optional
    **embedded subtitles** (language picker) and **chapters/metadata**.
  - Audio — **MP3**, **M4A**, plus **FLAC**/**WAV** that are only offered when
    the source is genuinely lossless (no fake upscaling).
- **Trim / clip** — a scissors button to download only a time range (e.g.
  `0:30 → 2:10`) of a video or audio.
- **Immersive / VR video** — detects 180°/360° clips (SBS · TB · mono ·
  fisheye / MKX / RF5.2) and tags the file so VR players (Quest / DeoVR /
  Heresphere) show it in 3D: a projection name suffix **plus injected Spherical
  Video V2 metadata** (`st3d`/`sv3d`). Shown only when detected; you confirm or
  fix the layout, and it's remembered per channel.
- **Playlists** — pick which items to download with checkboxes; they download
  sequentially with "X of N" progress (VR tagging applies to the whole batch).
- **Download queue** — paste many links to download one after another; the
  queue **persists across restarts** and **resumes** interrupted items.
- **Audio auto-tagging** — after an audio download, an inline card tags the file
  with real artist / album / title / year + **cover art** from **Apple Music,
  Deezer or MusicBrainz** (free, no account; pick one — or Automatic — in
  Settings); you review, edit or search before anything is written. Works per
  song and across whole playlists.
- **SponsorBlock** (optional, off by default) — strip or just mark sponsor /
  intro / outro segments on YouTube downloads, chosen in Settings.
- **History & stats** persisted locally (SQLite), with quality (resolution /
  bitrate), re-tagging, and **cover art** for tagged
  audio, open file / folder, and clear.
- **Settings** — download folder, default format/quality (up to **4K / best**),
  **filename template**, **video codec** & **audio bitrate**, **bandwidth limit**,
  **proxy** (http/socks), **language**, and cookies (browser — with icons — or
  `cookies.txt`).
- **Desktop notifications** when a download finishes, **taskbar/title progress**,
  and keyboard shortcuts (Ctrl/Cmd+L focus URL, Ctrl/Cmd+, settings).
- **14 UI languages** (react-i18next: EN/ES/FR/DE/IT/PT-BR/RU/PL/UK/ID/HI/ZH/JA/KO), auto-detected from your system
  language and switchable in Settings.
- **Update check** against the latest GitHub release; Settings also shows the
  bundled **yt-dlp version** and whether a newer one is out.
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
│   ├── autotag/          # Apple Music tagging cards (single + playlist batch)
│   ├── music/            # music-service import card (Spotify/Deezer/Apple/Tidal/Amazon)
│   ├── downloader/       # URL input (+ search-source toggle), preview, playlist, progress
│   ├── history/          # download history + stats (sidebar)
│   └── settings/         # settings modal (download dir, defaults, cookies, version)
├── lib/                  # API client + download WebSocket
└── types/                # shared domain types (mirror the backend JSON contract)

backend/                  # FastAPI + yt-dlp engine (see backend/README.md)
src-tauri/                # Tauri desktop shell
scripts/                  # setup.py, dev.py, fetch_ffmpeg.py, build_backend.py
e2e/                      # Playwright end-to-end tests
```

## Contributing

Issues and pull requests are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md)
for how to propose a change and the checks to run.

## License

Yoink's own source code is licensed under **CC BY-NC-SA 4.0** (non-commercial,
share-alike) — see [`LICENSE`](LICENSE). Bundled third-party components keep
their own licenses (ffmpeg = LGPL, yt-dlp = Unlicense); see
[`docs/THIRD_PARTY_LICENSES.md`](docs/THIRD_PARTY_LICENSES.md).

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — high-level guide and conventions
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to contribute
- [`docs/`](docs/) — architecture, per-layer guides, the [roadmap](docs/ROADMAP.md),
  the [release process](docs/releasing.md) and
  [third-party licenses](docs/THIRD_PARTY_LICENSES.md)
