# yoink-desktop — native egui UI (work in progress)

A native, GPU-rendered desktop UI for Yoink built with **egui/eframe** — no
WebView, no HTML/JS — as an alternative to the Tauri + React frontend. It drives
the same `yoink-core` backend over the existing REST/WS contract, so the engine
is unchanged.

Why: a native egui shell starts in well under a second and feels instant, because
it skips the browser engine entirely (same stack as the author's `netlabcraft`).

## Status — phased rewrite

- **Phase 1 (done):** app shell (tabbed: Inicio/Cola/Historial/Ajustes, dark by
  default), the typed design system (`theme.rs` — the Tailwind replacement), and
  the download screen end to end: analyze a URL (`POST /api/info`), pick
  format/quality, download with live progress (`WS /api/ws/download`).
- **Phase 2 (done):** the hidden WebView that mints YouTube PO tokens — the one
  thing that still needs a JS runtime — as a separate `wry` process
  (`../desktop-minter`) the app spawns only in `po_token_mode: "auto"`. It loads a
  blank page served by the backend (same origin, no CORS) and injects the bundled
  `bgutils-js` minter loop. Verified end to end: the app auto-spawns it and real
  session GVS tokens are minted for downloads (`dispatched → proxy → token`).
- **Phase 3 (done):** the Historial screen (`GET /api/history`, with size/quality/
  date and an "Abrir" button via `POST /api/open`) and the Ajustes screen (reads
  the whole `AppSettings`, edits the common fields incl. `po_token_mode`, and saves
  the full object back so nothing is lost).
- **Phase 4 (done):** the Cola (queue) — paste URLs, they download one at a time
  (sharing the single in-flight slot with the Inicio screen) using the default
  format, with per-item status and progress, remove, and "clear completed".
- **Phase 5 (done):** thumbnails in the preview card, loaded from the video's
  `thumbnail_url` via `egui_extras` image loaders (remote JPEG/PNG/WebP over http).
- **Phase 6 (done):** i18n (`i18n.rs`): every UI string goes through `tl(lang,
  key)`, with Spanish and English, auto-detected from `LANG`/`LC_*` and switchable
  live in Ajustes. The table is a flat match, so more locales are just more arms.
- **Phase 7 (done):** music-service import. A Spotify/Deezer/Apple/Tidal/Amazon
  link is detected and resolved (`POST /api/music/resolve`) into a track list shown
  with its cover; "Import all" enqueues each track, and the worker runs the full
  per-track pipeline — match on YouTube (`/api/music/match`), download the audio,
  and tag it with the exact source metadata (`/api/autotag/apply`).
- **Phase 8 (done):** desktop notifications on download completion (via
  `notify-rust`), gated by the existing `notify_on_complete` setting.
- **Later:** a standalone auto-tag screen for existing files; then the remaining
  Tauri shell concerns (in-app updater, system tray, `yoink://` deep link) as
  native crates.

## Run

```bash
# 1. the backend (from backend-rs/)
cargo run                       # serves :8756

# 2. this UI (from desktop/)
cargo run                       # YOINK_PORT overrides the backend port
```

Depends on the egui/eframe family (0.37) and, on Linux, the usual windowing
libraries. The design system lives in `theme.rs`; the backend client (tokio
worker + channels) in `api.rs`; the screens in `app.rs`.
