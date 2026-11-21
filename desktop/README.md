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
- **Later:** the music-import and auto-tag screens; i18n (reusing a Rust i18n
  layer); thumbnails; then the Tauri shell concerns (updater, tray, deep link,
  notifications) as native crates.

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
