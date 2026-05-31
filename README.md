# Yoink

Yoink is a local app for downloading high-fidelity video and audio from
multiple platforms, powered exclusively by [yt-dlp](https://github.com/yt-dlp/yt-dlp).

It is split into two layers that communicate asynchronously:

- **Frontend** — React + TypeScript + Tailwind CSS (Vite). A reactive, dark-mode
  UI that shows previews, lets you pick format/quality, and reflects download
  progress in real time.
- **Backend** — Python + FastAPI (in `backend/`). Wraps yt-dlp, manages the local
  filesystem, and invokes ffmpeg to merge high-quality formats. Metadata is
  served over REST (`/api/info`, `download=False`); download progress streams to
  the UI via WebSockets/SSE.

## Frontend

### Requirements

- Node.js 20+

### Getting started

```bash
npm install
npm run dev      # start the dev server
npm run build    # type-check + production build
npm run lint     # lint
```

### Project structure

```
src/
├── components/
│   ├── layout/      # app shell, background glow
│   └── ui/          # reusable primitives (GlassPanel, Button, Badge, ProgressBar)
├── features/
│   ├── downloader/  # URL input, preview, progress (main column)
│   └── history/     # download history + stats (sidebar)
├── types/           # shared domain types (mirrors the backend JSON contract)
└── App.tsx          # composition root
```

## Backend

See [`backend/README.md`](backend/README.md).

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — high-level guide and conventions
- [`docs/`](docs/) — architecture, frontend & backend guides, and the [roadmap](docs/ROADMAP.md)
