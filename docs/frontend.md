# Frontend

React + TypeScript + Tailwind CSS, built with Vite.

## Structure

```
src/
├── components/
│   ├── layout/
│   │   ├── AppLayout.tsx        # dark canvas + two-column main/sidebar shell
│   │   └── BackgroundGlow.tsx   # decorative blurred color blobs
│   └── ui/                      # reusable, presentational primitives
│       ├── GlassPanel.tsx       # frosted-glass card container
│       ├── Button.tsx           # solid / gradient action button
│       ├── Badge.tsx            # small pill label
│       └── ProgressBar.tsx      # gradient progress bar
├── features/
│   ├── downloader/              # main column
│   │   ├── DownloaderPanel.tsx  # orchestrates the column + local state
│   │   └── components/
│   │       ├── DownloaderHeader.tsx
│   │       ├── UrlInput.tsx
│   │       ├── PreviewCard.tsx
│   │       └── DownloadProgressCard.tsx
│   └── history/                 # sidebar
│       ├── HistorySidebar.tsx
│       └── components/
│           ├── HistoryItemCard.tsx
│           └── StatsCard.tsx
├── types/
│   └── download.ts              # shared domain types (backend JSON contract)
├── App.tsx                      # composition root
├── main.tsx                     # React entry point
└── index.css                    # Tailwind directives + global styles
```

## Conventions

- **`components/ui`** holds dumb, reusable visuals — no business logic.
- **`features/`** holds screen-specific composition and (later) data fetching.
  Each feature has a top-level panel plus a `components/` subfolder.
- **Styling:** Tailwind utility classes. Shared color tokens (`canvas`,
  `surface`, `surface-hover`) are defined in `tailwind.config.js` so the dark
  palette lives in one place.
- **Types:** keep `types/download.ts` aligned with the backend's Pydantic
  models — it's the single source of truth for the API shape on the client.

## Current state

The UI renders with placeholder data (`HISTORY`, `STATS`, `SAMPLE_INFO`).
`DownloaderPanel` exposes `handleAnalyze` / `handleDownload` stubs that are the
integration points for the backend (see the [roadmap](ROADMAP.md), Phase 2-3).
