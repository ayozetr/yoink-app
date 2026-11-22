# Yoink Media Downloader

[![Release](https://img.shields.io/github/v/release/ayozetr/yoink-app?label=release&color=7c3aed)](https://github.com/ayozetr/yoink-app/releases/latest)
![Platform](https://img.shields.io/badge/platform-Linux%20(AppImage)-2563eb)
![egui](https://img.shields.io/badge/UI-egui-000000)
![Rust](https://img.shields.io/badge/Rust-native-000000?logo=rust&logoColor=white)
![Powered by yt-dlp](https://img.shields.io/badge/powered%20by-yt--dlp-cc0000)
[![Downloads](https://img.shields.io/github/downloads/ayozetr/yoink-app/total.svg?color=2ea44f)](https://github.com/ayozetr/yoink-app/releases/latest)

![Yoink — the analyze view with the format and quality picker](docs/screenshot.png)

Yoink is a local desktop application for downloading high-fidelity video and
audio from roughly 1,800 sites. It provides a clean user interface over
[yt-dlp](https://github.com/yt-dlp/yt-dlp) and [ffmpeg](https://ffmpeg.org/):
paste a link (or an entire Spotify or YouTube playlist), choose a format, and
download it with real previews, live progress and automatic music tagging.
Nothing leaves the machine except the download itself — no account, no
telemetry, no cloud service.

## Features

### Downloading

- Paste any URL, or search directly from the input field, and preview the real
  available formats. A source toggle searches YouTube or SoundCloud.
- Video in MP4, MOV or MKV (with optional subtitles and chapters) or audio in
  MP3, M4A, FLAC or WAV, up to 4K.
- Trim a clip to a range, save format presets, and follow live progress (speed
  and ETA, with cancel and retry).
- VR 180°/360° content is detected and tagged so headset players such as Quest,
  DeoVR and Heresphere render it in 3D.

### Music

- Import from Spotify, Deezer, Apple Music, Tidal or Amazon without an account.
  Yoink finds the closest YouTube match and tags it with the exact source
  metadata and cover art.
- Auto-tag audio downloads (artist, album, cover) from Apple Music, Deezer or
  MusicBrainz, with a review step before anything is written.
- Optional lyrics (via LRCLIB) and loudness normalization to -14 LUFS.

### Batches and library

- Playlists and a paste-many queue: select items, download them in order,
  resume after a crash, and reorder or skip live. Playlist sync pre-selects only
  the entries that are new.
- A local history and statistics store (SQLite), with re-tagging, cover art and
  one-click file access.

### The application

- A self-contained native desktop app (egui, Linux AppImage) that bundles the
  backend, yt-dlp and ffmpeg, so there is nothing else to install.
- 14 interface languages, a dark theme, system tray with launch-at-startup,
  global shortcuts, desktop notifications, automatic updates, SponsorBlock, and
  cookie and proxy support.
- Browser integration through a `yoink://` deep link and the "Send to Yoink"
  (beta) extension, which hands off the current page with a right-click:
  [Firefox](https://addons.mozilla.org/firefox/addon/send-to-yoink/) and
  [Chrome](https://chromewebstore.google.com/detail/ccbngfpojjboddajeialdgppooagdhkp).

## Installation

Download the AppImage from the
[latest release](https://github.com/ayozetr/yoink-app/releases/latest), make it
executable and run it. The application is self-contained (no Python, yt-dlp or
ffmpeg to install separately) and updates itself in place. (A Windows build is
being ported.)

## Running from source

```bash
# Run the desktop app (it spawns the bundled backend automatically):
cargo run --release --manifest-path desktop/Cargo.toml
```

For development you need the Rust toolchain, `yt-dlp` on your PATH and ffmpeg (the
packaged app bundles both), plus — on Linux — `libgtk-3-dev`,
`libayatana-appindicator3-dev` and `libxdo-dev`. A command-line interface is also
available: `scripts/yoink <url>` downloads from the terminal with the same engine
— see [`docs/cli.md`](docs/cli.md). See [`CLAUDE.md`](CLAUDE.md) for per-layer
commands.

### Building the AppImage

```bash
bash scripts/build_ffmpeg.sh          # one-time: build a minimal ffmpeg + ffprobe (~33 MB)
bash scripts/build_egui_appimage.sh   # -> desktop/target/appimage/Yoink_<ver>_amd64.AppImage
```

The full release process is documented in [`docs/releasing.md`](docs/releasing.md).

## Architecture

Yoink has two native Rust layers that communicate asynchronously: the egui
desktop app and a local backend (`yoink-core`, built on axum) that drives
`yt-dlp` and `ffmpeg`. The app spawns the backend on startup; metadata is fetched
over REST (`POST /api/info`) and downloads stream live over a WebSocket
(`/api/ws/download`).

```
desktop/                  # the native egui desktop app (yoink-desktop)
└── src/                  # app.rs (UI + state), api.rs (backend client + self-update),
                          #   backend_proc.rs, deeplink.rs, theme.rs, i18n.rs, …
backend-rs/               # native Rust backend (yoink-core); see CLAUDE.md
desktop-minter/           # yoink-minter: the hidden PO-token WebView helper
extension/                # "Send to Yoink" (beta) browser extension (Firefox, Chromium)
scripts/                  # build_ffmpeg.sh, build_core.py, build_egui_appimage.sh, …
```

## Contributing

Issues and pull requests are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md)
for how to propose a change and the checks to run before submitting.

## License

Yoink's own source code is licensed under the GNU Affero General Public License,
version 3.0 or later (AGPL-3.0-or-later); see [`LICENSE`](LICENSE). You are free
to use, study, modify and redistribute it, including commercially, provided that
derivative works remain under the AGPL and their source remains available —
including to anyone who interacts with a modified version over a network.
Copyright © 2026 Ayoze Torres. Bundled third-party components retain their own
licenses (ffmpeg under the LGPL, yt-dlp under the Unlicense); see
[`docs/THIRD_PARTY_LICENSES.md`](docs/THIRD_PARTY_LICENSES.md).

## Disclaimer

Yoink is a personal tool for downloading media that you are entitled to access —
content you own, that is in the public domain, that is openly licensed, or that
you have the rights holder's permission to download. It is not intended for
piracy or copyright infringement. By using it, you accept that you alone are
responsible for how you use it and for complying with all applicable laws and
platform terms. The full text is in [`DISCLAIMER.md`](DISCLAIMER.md).

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — high-level guide and conventions
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to contribute
- [`docs/`](docs/) — architecture, per-layer guides, the
  [roadmap](docs/ROADMAP.md), the [release process](docs/releasing.md) and
  the [third-party licenses](docs/THIRD_PARTY_LICENSES.md)
