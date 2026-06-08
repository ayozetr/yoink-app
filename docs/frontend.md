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
│       ├── Toggle.tsx           # on/off switch (role=switch): chapters, multi-audio, SponsorBlock
│       ├── SponsorBlockIcon.tsx # SponsorBlock brand mark (shield + play)
│       ├── EditMenu.tsx         # custom right-click Cut/Copy/Paste menu for text fields
│       └── ProgressBar.tsx      # gradient progress bar
├── features/
│   ├── downloader/              # main column
│   │   ├── DownloaderPanel.tsx  # orchestrates the column + local state
│   │   ├── formatOptions.ts     # derive kind/quality/container/audio-format options from formats
│   │   └── components/
│   │       ├── DownloaderHeader.tsx
│   │       ├── UrlInput.tsx        # URL field + paste + live YouTube search dropdown
│   │       ├── PreviewCard.tsx     # format/quality/subs + scissors trim + VR controls + size estimate
│   │       ├── PlaylistCard.tsx
│   │       └── DownloadProgressCard.tsx
│   ├── queue/                   # persistent sequential download queue (opened from the header)
│   │   └── QueuePanel.tsx
│   ├── autotag/                 # audio auto-tagging (Apple Music / Deezer / MusicBrainz), wired into DownloaderPanel
│   │   ├── AutoTagPanel.tsx     # inline "Tag audio" card after a single audio download
│   │   ├── AutoTagBatchPanel.tsx # per-track tagging list after an audio playlist
│   │   └── filename.ts          # "Artist - Title" filename parser (seeds catalogue search)
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
│   ├── download.ts              # shared domain types (backend JSON contract)
│   └── autotag.ts               # audio auto-tagging types (mirror backend models)
├── App.tsx                      # composition root
├── main.tsx                     # React entry point (imports ./i18n)
└── index.css                    # Tailwind directives + global styles
```

## Conventions

- **`components/ui`** holds dumb, reusable visuals — no business logic.
- **`features/`** holds screen-specific composition and data fetching.
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
progress over the WebSocket client in `lib/`. FLAC/WAV are gated behind probed
lossless detection — `PreviewCard` uses the single video's `source_lossless`
and `PlaylistCard` uses `playlist.source_lossless` (probed from the first entry).

After an audio download, `DownloaderPanel` offers opt-in **audio auto-tagging**
(Apple Music, Deezer or MusicBrainz, chosen in Settings): a single one-song download shows the
collapsible `AutoTagPanel`,
and a finished audio playlist shows `AutoTagBatchPanel` (a per-track list with
include checkboxes and an accordion editor). Both look files up via
`identifyAudio`, allow manual `searchAudio`, let the user pick a version and
edit fields, and write nothing until "Apply" calls `applyAudioTags`
(`src/lib/api.ts`).

In Settings, the cookies "browser" field is a `Select` dropdown
(Brave/Chrome/Chromium/Edge/Firefox/Opera/Vivaldi) and the cookies.txt field has
a native file picker (`pickFile` in `lib/pickDirectory.ts`). Scrollbars are
hidden app-wide (`index.css`) for a native-app feel; scrolling still works.
