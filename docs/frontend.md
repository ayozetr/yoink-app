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
│       ├── Select.tsx           # dark, app-styled dropdown (replaces native <select>)
│       ├── EditMenu.tsx         # custom right-click Cut/Copy/Paste menu for text fields
│       └── ProgressBar.tsx      # gradient progress bar
├── features/
│   ├── downloader/              # main column
│   │   ├── DownloaderPanel.tsx  # orchestrates the column + local state
│   │   ├── formatOptions.ts     # derive kind/quality/container/audio-format options from formats
│   │   └── components/
│   │       ├── DownloaderHeader.tsx
│   │       ├── UrlInput.tsx
│   │       ├── PreviewCard.tsx
│   │       ├── PlaylistCard.tsx
│   │       └── DownloadProgressCard.tsx
│   ├── history/                 # sidebar
│   │   ├── HistorySidebar.tsx
│   │   └── components/
│   └── settings/                # settings modal (dir, defaults, cookies, language, version)
│       └── SettingsModal.tsx
├── i18n/                        # react-i18next setup + en/es locale strings
│   ├── index.ts
│   └── locales/{en,es}.ts
├── lib/                         # API client, download WebSocket, native dialogs
├── types/
│   └── download.ts              # shared domain types (backend JSON contract)
├── App.tsx                      # composition root
├── main.tsx                     # React entry point (imports ./i18n)
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
- **i18n:** user-facing strings come from `react-i18next` (`useTranslation`),
  with English + Spanish dictionaries in `i18n/locales`. The language is
  auto-detected from the system and overridable in Settings; the choice is
  persisted under the `yoink-lang` localStorage key. Backend error messages
  arrive in English; the frontend only translates its own UI.

## Current state

The UI is wired to the live backend. `DownloaderPanel` calls `/api/info` to
populate the preview/playlist, derives the kind/quality/container/audio-format
selectors from the real formats (`formatOptions.ts`), and streams download
progress over the WebSocket client in `lib/`.
