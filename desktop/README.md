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
- **Phase 2 (next):** the hidden WebView (a separate `wry` process) that mints
  YouTube PO tokens with `bgutils-js` — the one thing that still needs a JS
  runtime — so `po_token_mode: "auto"` keeps working under a native UI.
- **Later:** the Cola, Historial, Ajustes, music-import and auto-tag screens; i18n
  (reusing a Rust i18n layer); thumbnails; then the Tauri shell concerns
  (updater, tray, deep link, notifications) as native crates.

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
