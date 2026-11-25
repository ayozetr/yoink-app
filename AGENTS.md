# AGENTS.md

Guidance for coding agents (Claude Code and others) and humans working in this repository.

## What is Yoink

Yoink is a **local** desktop app for downloading high-fidelity video and audio
from multiple platforms. The download engine is **exclusively
[yt-dlp](https://github.com/yt-dlp/yt-dlp)**; [ffmpeg](https://ffmpeg.org/) is
used to merge high-quality video + audio formats. Everything runs on the user's
machine — there is no server and no web deployment.

## Architecture (local, two native Rust layers)

- **Desktop app** — native **Rust + [egui](https://github.com/emilk/egui)/eframe**
  (`desktop/`). A reactive, flat "Flat Minimal" UI (Gloock titles + Inter),
  organised into tabs (Inicio/Cola/Historial/Ajustes/Registro), dark by default
  with a light theme and a System option. It owns its window chrome (custom
  AMOLED title bar, rounded corners) and, on startup, **spawns and supervises the
  bundled `yoink-core` backend** (`desktop/src/backend_proc.rs`), so the app is
  self-contained. It talks to that backend over the local REST/WebSocket API.
- **Backend** — native **Rust** (`yoink-core`, axum), runs locally
  (`backend-rs/`). Shells out to the bundled `yt-dlp` + `ffmpeg` binaries,
  manages the local filesystem, and streams download progress. No Python runtime.
  (The original Python/FastAPI backend lives on the `legacy` branch; the old
  React + Tauri desktop shell was removed when the egui app replaced it.)
- **Minter** — a small helper crate (`desktop-minter/`, `yoink-minter`): a hidden
  WebView that mints YouTube PO tokens. The desktop app spawns it only while
  `po_token_mode` is `auto`.

### Communication contract (strict)

The desktop app is a REST/WebSocket client of `yoink-core` on `127.0.0.1`. The
endpoint behaviours below are the contract; the Rust structs in `backend-rs/src/`
serialize (serde) to the JSON the desktop app's `desktop/src/api.rs` expects —
keep both sides in sync.

- **Metadata (REST):** pasting a URL calls `POST /api/info` (yt-dlp with
  `download=False`), returning an `InfoResponse` that is **either** a single video
  (title, thumbnail, formats, plus `source_lossless`/`best_audio_abr`/`has_audio`/
  `subtitle_langs`/`has_chapters`, and an `is_vr`/`vr_layout` immersive heuristic)
  **or** a flat playlist listing (entries flagged `already_downloaded` for sync).
  A transient extraction failure (anti-bot 403 / network blip) is retried before
  surfacing as 503 (retryable) vs 422 (genuinely unsupported URL).
- **Search (REST):** typing a query (not a URL) hits
  `GET /api/search?q=&source=youtube|soundcloud` (a flat `ytsearch`/`scsearch`)
  for the live dropdown; picking one analyzes it via `POST /api/info`.
- **Music import (REST):** pasting a Spotify/Deezer/Apple/Tidal/Amazon URL hits
  `POST /api/music/resolve`, keylessly turning it into a `MusicImportInfo`
  (`POST /api/music/cover` lazily fills a missing cover). Each track is ranked
  against a YouTube video (`POST /api/music/match`, spotDL-ported scorer),
  downloaded via the normal WS flow, and auto-tagged with the source metadata.
- **Download & progress (WebSockets):** on "Download", the app opens
  `WS /api/ws/download` and sends a `DownloadRequest` (`kind`/`quality`,
  `container`, `audio_format`, `audio_bitrate`, `embed_subs`/`subtitle_lang`/
  `embed_chapters`, `trim_start`/`trim_end`, `is_vr`/`vr_layout`/`auto_vr`). The
  backend runs the job off-thread and streams typed events — `progress` →
  terminal `completed`/`error`. With `normalize_audio` on (off by default), an
  audio download is loudness-normalized to the target LUFS (EBU R128) before it's
  finalized and auto-tagged.
- **Audio auto-tagging (REST):** after an audio download the app looks the file up
  in Apple Music / Deezer / MusicBrainz (or `auto` cascade) and writes tags +
  cover via `POST /api/autotag/{identify,search,apply}` — a manual download shows
  an interactive tag panel to review/apply, the queue tags silently. With
  `fetch_lyrics` on, `POST /api/autotag/lyrics` embeds LRCLIB lyrics. With
  `music_folders` on, `apply` relocates the track into an `Artist/Album` layout.
- **Update check (REST):** with *"check for updates"* on (`AppSettings.check_updates`,
  on by default; the app only — yt-dlp stays owner-managed), the app reads the
  release's `latest.json` on launch; if newer it shows an in-app banner and can
  **self-update in place** (AppImage via `$APPIMAGE`), verifying the asset's
  **minisign signature** against an embedded public key before installing
  (`desktop/src/api.rs`). `GET /api/release-notes` returns a `WhatsNew` for the
  first-launch-after-update "What's new" popup (`?since=<version>` is cumulative).
- **Deep link (`yoink://`):** `desktop/src/deeplink.rs` registers the scheme (via
  the AppImage's `.desktop` entry) and a single-instance Unix socket, so the
  browser — or the **"Send to Yoink" (beta)** extension in `extension/` — hands a
  `yoink://download?url=<encoded>` link to the running app, routed through the
  same analyze path as paste.

## Repository layout

```
.
├── AGENTS.md                 # this file
├── README.md                 # project overview + quick start
├── docs/                     # architecture, roadmap, per-layer guides
├── desktop/                  # the native egui desktop app (yoink-desktop)
│   ├── src/                  # app.rs (UI + state), api.rs (backend client +
│   │                         #   self-update), backend_proc.rs, deeplink.rs,
│   │                         #   theme.rs, i18n.rs (14 languages), fonts.rs,
│   │                         #   icons.rs, minter.rs, tray.rs, main.rs
│   ├── assets/               # bundled fonts + icon
│   └── packaging/            # yoink.desktop (AppImage desktop entry)
├── desktop-minter/           # yoink-minter: the hidden PO-token WebView helper
├── extension/                # "Send to Yoink" (beta) browser extension
├── backend/vendor/ffmpeg/    # bundled minimal ffmpeg+ffprobe (gitignored; built
│                             #   by scripts/build_ffmpeg.sh)
├── backend-rs/               # native Rust backend (yoink-core, axum + yt-dlp/ffmpeg)
│   └── src/                  # main.rs (routes, download, history, settings, …),
│                             #   matching.rs, music.rs, autotag.rs, nfo.rs,
│                             #   library.rs, vr.rs, audio_normalize.rs,
│                             #   po_token.rs, cli.rs
└── scripts/                  # build_ffmpeg.sh, build_core.py, build_egui_appimage.sh,
                              #   make_latest_json_egui.py, gen_licenses.py, smoke_test.sh,
                              #   yoink (CLI)
```

## Common commands

### Desktop app (egui)

```bash
# Run it (spawns yoink-core if one isn't already serving the port):
cargo run --release --manifest-path desktop/Cargo.toml
# Lint + test:
cd desktop && cargo clippy --release -- -D warnings && cargo test --release
```

The desktop app finds `yoink-core` beside its own executable (a release build
ships it as a sibling); in a dev build it reuses a `yoink-core` already serving
the port, or spawns one found via `$YOINK_CORE` / the workspace build.

### Backend (`backend-rs/`)

```bash
cd backend-rs
cargo run                 # serve the API on :8756 (set YOINK_PORT to change)
cargo build --release     # optimized binary at target/release/yoink-core
cargo fmt && cargo clippy  # CI gates on both
cargo test                # unit tests: download args, autotag/nfo/vr/matching, helpers, …
```

Unit tests cover the pure logic and run offline. For runtime behaviour the unit
tests can't reach (real yt-dlp + the bundled ffmpeg: formats, trimming, VR
metadata, tag writing), run the end-to-end **`bash scripts/smoke_test.sh`** —
real downloads of short clips to a temp dir, verified with ffprobe. It needs the
network, so it runs before a release, not in per-PR CI.

The backend finds `yt-dlp` on PATH (or `YOINK_YTDLP`) and ffmpeg at `YOINK_FFMPEG`
(or PATH). `yoink-core` does double duty: no arguments → serve the API; with
arguments → the **CLI** (`src/cli.rs`). `scripts/yoink` is the dev wrapper. See
[`docs/cli.md`](docs/cli.md).

### Packaging (Linux AppImage + Windows installer)

```bash
bash scripts/build_ffmpeg.sh          # once: build a minimal ffmpeg+ffprobe (Linux)
bash scripts/build_egui_appimage.sh   # -> desktop/target/appimage/Yoink_<ver>_amd64.AppImage
python scripts/build_windows.py       # on Windows -> desktop/target/windows/Yoink_<ver>_x64-setup.exe
```

`build_egui_appimage.sh` lays out an AppDir with the egui binary and, beside it,
`yoink-core` + the pinned standalone `yt-dlp` + the minimal `ffmpeg`/`ffprobe`
(`backend_proc.rs` finds them as siblings), then linuxdeploy (+ gtk plugin)
bundles the runtime libs and appimagetool packs it. No WebKit, so it's far
smaller than the old Tauri bundle. `build_windows.py` is the Windows counterpart:
it vendors a prebuilt LGPL **shared** ffmpeg (`scripts/ffmpeg-windows.txt`), runs
`build_core.py`, builds the egui `.exe` (GUI subsystem, with an embedded icon via
`build.rs`), and packs a per-user NSIS installer
(`desktop/packaging/windows/yoink.nsi`) to `%LOCALAPPDATA%\Yoink` that rounds the
window corners via DWM and registers the `yoink://` scheme.

Releases build on GitHub Actions (`.github/workflows/release.yml`): a tag `v*`
builds + signs the AppImage **and the Windows installer** (minisign, via
`cargo tauri signer sign` with the key in repo secrets) and drafts the release
with a combined `latest.json`. The **same minisign key the legacy Tauri app
used** signs each asset, so it serves both the one-time legacy→egui migration
(AppImage on Linux, installer on Windows) and the egui app's own updater. See
[`docs/releasing.md`](docs/releasing.md).

## Conventions

- **Rust, edition 2021.** `cargo fmt` + `cargo clippy` clean (CI gates on
  `clippy -D warnings`). OS-agnostic paths via `std::path`. Rust structs serialize
  (serde) to the JSON contract between the desktop app and the backend.
- **UI (egui):** the design system is typed tokens in `desktop/src/theme.rs` (a
  `Palette` of semantic colors, dark + light, mapped onto `egui::Visuals`) — no
  CSS. Screen logic lives in `desktop/src/app.rs`.
- **Fonts:** Gloock for display titles, Inter for the UI (+ Inter SemiBold for
  emphasis), bundled under `desktop/assets/fonts/`.
- **i18n:** UI strings go through `desktop/src/i18n.rs` (`tl(lang, key)`, 14
  languages); the language is auto-detected from the system and overridable in
  Settings (with a System option). Backend error messages stay in **English**.
- **Security:** the self-update verifies a minisign signature before installing
  (fail-closed); the IPC socket lives in a per-user dir with 0600 perms. Never
  suggest updating yt-dlp from the app — it's owner-managed in a release.
- **Bundled ffmpeg has no working TLS at runtime** (minimal build, mbedTLS fails
  on https), so never rely on it fetching a URL — e.g. yt-dlp `--download-sections`
  is avoided; trimming fetches the full stream, then clips the **local** file.
  Merge/extract/loudnorm/VR all operate on local files.

## Git conventions

- Remote: `git@github.com:ayozetr/yoink-app.git` (SSH).
- Commit messages in **English**, with a subject **and a body**.
- Commit under **your own git identity** (the repo/user's configured
  `user.name` / `user.email`) — don't impersonate another contributor.
- **Never credit an AI/assistant as a `Co-Authored-By`** (or mention the AI in the
  trailer at all). A `Co-Authored-By` for a **human** collaborator is fine.
- License: **AGPL-3.0-or-later**. New source files start with the two-line SPDX
  header (`SPDX-License-Identifier: AGPL-3.0-or-later` + copyright) — see
  `docs/CONTRIBUTING.md`.

## Status

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what's done and what's next.
