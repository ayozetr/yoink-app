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
  that is **either** a single video (title, thumbnail, formats) **or** a flat
  playlist listing (entries with title/duration/url). Endpoint: `POST /api/info`.
- **Download & progress (WebSockets):** on "Download", the frontend opens a
  socket to `WS /api/ws/download` and sends the request. The backend runs the
  yt-dlp job off-thread (`asyncio.to_thread`) and streams typed events —
  `progress` (percent, speed, ETA) → terminal `completed`/`error` — back over
  the same socket to animate the progress bar.

The TypeScript types in `src/types/download.ts` mirror the Pydantic models in
`backend/app/models/media.py` — keep both sides in sync.

## Repository layout

```
.
├── CLAUDE.md                 # this file
├── README.md                 # project overview + quick start
├── docs/                     # architecture, roadmap, per-layer guides
├── src/                      # frontend (React + TS + Tailwind)
│   ├── components/
│   │   ├── layout/           # app shell, background glow
│   │   └── ui/               # reusable primitives (GlassPanel, Button, …)
│   ├── features/
│   │   ├── downloader/       # URL input, preview, progress (main column)
│   │   └── history/          # download history + stats (sidebar)
│   └── types/                # shared domain types (backend JSON contract)
└── backend/                  # FastAPI + yt-dlp engine
    └── app/
        ├── main.py           # app factory, CORS, router mounting
        ├── core/config.py    # typed settings (CORS, download dir)
        ├── models/media.py   # Pydantic models (JSON contract)
        ├── core/humanize.py   # shared byte/size formatting
        ├── routers/info.py    # POST /api/info
        ├── routers/download.py        # WS /api/ws/download (live progress)
        ├── routers/history.py         # GET /api/history(/stats), POST /api/open
        ├── services/ytdlp_service.py  # typed yt-dlp metadata wrapper
        ├── services/download_service.py  # yt-dlp download + progress stream
        └── services/history_store.py  # SQLite persistence (history + stats)
```

## Common commands

### Everything at once (recommended)

```bash
python scripts/setup.py    # one-time: venv + backend deps + npm install
python scripts/dev.py      # run backend (:8000) + frontend (:5173) together
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
```

### Backend (`backend/`)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload    # http://127.0.0.1:8000  (docs at /docs)

pip install -r requirements-dev.txt   # test deps (pytest, httpx)
pytest                                # run the backend test suite
```

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

## Git conventions

- Remote: `git@github.com:ayozetr/yoink-app.git` (SSH).
- Commit messages in **English**, with a subject **and a body**.
- **No `Co-Authored-By` trailer.**
- Author identity: **Ayoze Torres** `<ayozetr@users.noreply.github.com>`.

## Status

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what's done and what's next.
