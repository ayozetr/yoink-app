# yoink-desktop — native egui UI

A native, GPU-rendered desktop UI for Yoink built with **egui/eframe** — no
WebView, no HTML/JS for the interface — as an alternative to the Tauri + React
frontend. It drives the same `yoink-core` backend over the existing REST/WS
contract, so the engine is unchanged.

Why: a native egui shell starts in well under a second and feels instant, because
it skips the browser engine entirely (same stack as the author's `netlabcraft`).

## Features

It mirrors the web v4 "Flat Minimal" UI — the same Gloock/Inter fonts, the exact
`--c-*` violet palette, lucide icons, pill tabs, flat de-boxed layout — across all
six screens:

- **Inicio** — paste a link to analyze (video/playlist/music), or type a query to
  **search** YouTube/SoundCloud (source selector, thumbnailed results); a flat
  preview with a Gloock title, Video/Audio toggle, a wide Download button and
  collapsible advanced options.
- **Cola** — a queue with a FORMAT row and Start; items download one at a time.
- **Historial** — stat header, search box, relative times, format badges,
  `POST /api/open` to reveal a file.
- **Ajustes** — the full settings (General, Downloads, PO token, Quality,
  Processing, SponsorBlock, Network), label-left/control-right rows, pill toggles
  and a sticky "on this page" nav; round-trips the whole `AppSettings`.
- **Registro** — the live backend log (`GET /api/logs`), monospace, with copy.
- **Music import** — Spotify/Deezer/Apple/Tidal/Amazon links resolve to a track
  list; each track is matched on YouTube, downloaded and tagged.

Platform: it **spawns and supervises `yoink-core`** (dies with the app via the
stdin watchdog), mints **YouTube PO tokens** through a hidden `wry` WebView
(`../desktop-minter`) in `auto` mode, has a **system tray** (show/quit,
close-to-tray), **desktop notifications**, an **update banner** + **"what's new"**
popup (GitHub releases), **launch-at-startup**, the **`yoink://` deep link** with
single-instance, **14-language-ready i18n** (ES/EN wired) and thumbnails.

`theme.rs` is the design system (the Tailwind replacement); `fonts.rs`/`icons.rs`
load the Gloock/Inter fonts and lucide SVGs; `api.rs` is the backend client (a
tokio worker + channels); the screens live in `app.rs`.

## Build & install (Linux)

```bash
python scripts/build_desktop.py          # release build + dist/yoink-linux/
cd dist/yoink-linux && sudo ./install.sh # → /usr/lib/yoink + /usr/bin/yoink-desktop
```

(First time, run `scripts/build_ffmpeg.sh` and `scripts/build_core.py` once so
yt-dlp/ffmpeg are available to bundle.)

## Run (development)

```bash
cargo run                     # from backend-rs/ — serves :8756
cargo run                     # from desktop/   — the UI (YOINK_PORT overrides the port)
```

Or just run `desktop` with `YOINK_CORE`/`YOINK_MINTER` set and it starts the
backend and minter itself. `YOINK_SHOT=<png>` (+ `YOINK_SHOT_TAB`, `YOINK_SHOT_MS`)
renders one frame to a PNG and exits — a headless way to see the UI.

## Still to do

A standalone auto-tag screen for existing files, in-place self-update (the banner
currently links to the releases page), and Windows packaging.
