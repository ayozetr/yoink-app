# Frontend

React + TypeScript + Tailwind CSS, built with Vite.

## Structure

```
src/
├── components/
│   ├── layout/
│   │   ├── AppShell.tsx         # fixed chrome (brand + TabBar) over a single scrolling <main>
│   │   ├── TabBar.tsx           # Inicio / Cola / Historial / Ajustes tabs (+ queue badge)
│   │   └── Splash.tsx           # startup overlay shown until the backend answers
│   └── ui/                      # reusable, presentational primitives
│       ├── GlassPanel.tsx       # bare passthrough by default; `boxed` adds the card shell (dialogs)
│       ├── Button.tsx           # solid / gradient action button
│       ├── Select.tsx           # app-styled dropdown (replaces native <select>)
│       ├── Toggle.tsx           # on/off switch (role=switch): chapters, multi-audio, SponsorBlock
│       ├── Drawer.tsx           # right slide-over (animated in + out), focus-trapped — e.g. tag editing
│       ├── Toaster.tsx          # bottom-right toast stack (store in lib/toast.ts)
│       ├── SponsorBlockIcon.tsx # SponsorBlock brand mark (shield + play)
│       ├── BrowserIcon.tsx      # per-browser glyphs for the cookies picker
│       ├── EditMenu.tsx         # custom right-click Cut/Copy/Paste menu for text fields
│       ├── CopyButton.tsx       # copy-to-clipboard button with a copied tick
│       ├── Thumbnail.tsx        # <img> that proxies via /api/thumbnail with a fallback
│       ├── youtubeFallback.ts   # YouTube thumbnail fallback (hqdefault when maxres is the grey 200 placeholder)
│       ├── ProgressBar.tsx      # gradient progress bar
│       ├── Markdown.tsx         # tiny built-in Markdown renderer (release notes)
│       ├── UpdateBanner.tsx     # dismissible "update available" bottom banner
│       ├── UpdatingModal.tsx    # "Downloading…" popup with a real progress bar
│       └── WhatsNewModal.tsx    # first-launch-after-update "what's new" popup
├── features/
│   ├── downloader/              # main column
│   │   ├── DownloaderPanel.tsx  # orchestrates the column + local state
│   │   ├── formatOptions.ts     # derive kind/quality/container/audio-format options from formats
│   │   └── components/
│   │       ├── UrlInput.tsx        # URL field with the source selector (YouTube/SoundCloud) inside + paste + live search dropdown
│   │       ├── SearchSourceIcon.tsx     # per-source glyph for that selector
│   │       ├── SupportedSitesModal.tsx  # "supported sites" list (lazy, from the URL field)
│   │       ├── PreviewCard.tsx     # media row + Vídeo/Audio + advanced options (FORMATO/PROCESADO/RECORTE/PRESETS) + size estimate
│   │       ├── PlaylistCard.tsx    # entry picker (pre-selects new items, badges already-downloaded); music lists default to audio
│   │       ├── ImagePreviewCard.tsx     # Instagram/photo carousel preview
│   │       └── DownloadProgressCard.tsx
│   ├── music/                   # keyless music import (Spotify/Deezer/Apple/Tidal/Amazon)
│   │   └── MusicImportCard.tsx  # resolve → match each track on YouTube → download + tag
│   ├── queue/                   # persistent sequential download queue (opened from the header)
│   │   └── QueuePanel.tsx        # own format picker + collapsible playlist/album groups + skip/stop + drag-reorder + whole-queue progress bar
│   ├── autotag/                 # audio auto-tagging (Apple Music / Deezer / MusicBrainz), wired into DownloaderPanel
│   │   ├── AutoTagPanel.tsx     # inline "Tag audio" card (+ a lyrics indicator/preview/popup) after a single audio download
│   │   ├── AutoTagBatchPanel.tsx # per-track tagging list after an audio playlist
│   │   └── filename.ts          # "Artist - Title" filename parser (seeds catalogue search)
│   ├── history/                 # the Historial tab (editorial, date-grouped; failed rows show the error + copy)
│   │   ├── HistorySidebar.tsx
│   │   └── components/HistoryItemCard.tsx
│   └── settings/                # the Ajustes tab (flowing single-scroll + "on this page" index)
│       ├── SettingsModal.tsx
│       ├── LicensesModal.tsx    # third-party OSS licenses (OPEN_SOURCE_LICENSES.md)
│       └── TermsModal.tsx
├── i18n/                        # react-i18next setup + 14 locale files (lazy-loaded)
│   ├── index.ts
│   └── locales/{en,es,fr,de,it,pt,ru,pl,uk,id,hi,zh,ja,ko}.ts
├── lib/                         # API client (runtime backend-port resolve) + download WebSocket + single-download lock;
│                                #   queue/batch/preset stores, theme, toast store, VR-layout memory, search-source pref,
│                                #   Tauri self-updater, OS notifications, taskbar progress, focus trap, native dialogs
├── types/
│   ├── download.ts              # shared domain types (backend JSON contract)
│   ├── music.ts                 # music-import types (mirror backend models)
│   ├── autotag.ts               # audio auto-tagging types (mirror backend models)
│   └── api.generated.ts         # OpenAPI-generated literal types (scripts/gen_api_types.py)
├── App.tsx                      # composition root
├── main.tsx                     # React entry point (imports ./i18n)
└── index.css                    # Tailwind v4 @theme + design tokens + global styles
```

## Conventions

- **`components/ui`** holds dumb, reusable visuals — no business logic.
- **`features/`** holds screen-specific composition and data fetching.
  Each feature has a top-level panel plus a `components/` subfolder.
- **Styling:** Tailwind v4 (CSS-first). The `@theme` mapping and design tokens
  live in `src/index.css` — a CSS-variable palette (`--c-canvas/surface/line/fg/
  accent/…`) exposed as utilities, **dark by default** with a light theme under
  `html[data-theme="light"]`. No `tailwind.config.js`; PostCSS uses
  `@tailwindcss/postcss`.
- **Types:** keep `types/download.ts` aligned with the backend's Pydantic
  models — it's the single source of truth for the API shape on the client.
- **i18n:** user-facing strings come from `react-i18next` (`useTranslation`),
  with 14 language dictionaries in `i18n/locales` (English bundled, the rest
  lazy-loaded per chunk). The language is
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

The three download engines — `DownloaderPanel` (single/playlist), `QueuePanel`
and `MusicImportCard` — share a single in-memory **download lock**
(`lib/downloadLock.ts`): each acquires it before opening a socket and releases it
on drain/cancel/unmount, and the others' start buttons are disabled while it's
held, so two engines can't write the same `.part` at once (the backend has an
`asyncio.Lock` backstop for the multi-client case).

After an audio download, `DownloaderPanel` offers opt-in **audio auto-tagging**
(Apple Music, Deezer or MusicBrainz, chosen in Settings): a single one-song download opens
`AutoTagPanel` in a right-side `Drawer`,
and a finished audio playlist shows `AutoTagBatchPanel` (a per-track list with
include checkboxes and an accordion editor). Both look files up via
`identifyAudio`, allow manual `searchAudio`, let the user pick a version and
edit fields, and write nothing until "Apply" calls `applyAudioTags`
(`src/lib/api.ts`).

The **queue** (`QueuePanel`) has its own format picker (video/audio + quality/
container or audio format), seeded from Settings but editable, applied to every
queued item. Pasting a music-service album/playlist or a regular video playlist
resolves on add into a **collapsible group row** whose tracks/videos you select
individually (a single video/track stays a plain row); music groups route through
the importer (match on YouTube → download audio → tag). An async drain loop walks
singles + selected children, with **Skip-current** vs **Stop**, live
**drag-reorder**, and a **whole-queue progress bar** ("N of M downloaded", counted
in *media* so an album/playlist counts its selected tracks); the queue persists to
localStorage (`lib/queueStore.ts`). The
main panel's own multi-item batch persists separately (`lib/batchStore.ts`) so an
interrupted playlist resumes.

The app also runs an opt-in **update experience** (`App.tsx`): when the
check-for-updates setting is on, it checks GitHub on launch and, on a newer
release, floats `UpdateBanner` + a notification; installing self-updates in place
through the Tauri updater (`lib/updater.ts`) behind `UpdatingModal`. The first
launch after an update shows `WhatsNewModal`, which renders `/api/release-notes`
via the `Markdown` primitive.

In Settings, the cookies "browser" field is a `Select` dropdown
(Brave/Chrome/Chromium/Edge/Firefox/Opera/Vivaldi) and the cookies.txt field has
a native file picker (`pickFile` in `lib/pickDirectory.ts`). Scrollbars are
hidden app-wide (`index.css`) for a native-app feel; scrolling still works.
