# Roadmap and release history

Yoink is a local, high-fidelity media downloader built on yt-dlp with a bundled
ffmpeg. This document records what each release delivered and what is planned.

The latest published release is **4.4.0** (all 1.x–4.4.0 releases are the
React + Tauri / Python app). The project is currently being rebuilt as a native
Rust application — see **Unreleased** below.

Per-feature detail for each release is in the
[GitHub releases](https://github.com/ayozetr/yoink-app/releases); this file is
the summary.

## Unreleased

A ground-up rewrite to a self-contained native-Rust stack, replacing the
React + Tauri desktop shell and the Python/FastAPI backend:

- **Desktop app** — rebuilt in native Rust + egui (`desktop/`). Owns its window
  chrome, spawns and supervises the backend, and ships as a WebKit-free AppImage
  (far smaller than the Tauri bundle).
- **Backend** — ported from Python/FastAPI to native Rust (`yoink-core`, axum).
  No Python runtime; it shells out to the bundled yt-dlp and a custom minimal
  ffmpeg (~33 MB vs ~336 MB).

Full feature parity with 4.4.0, plus:

- Live type-to-search with a loading indicator and stale-result protection.
- Queue: per-item format overrides, drag-to-reorder, and resolved content titles
  instead of raw links.
- An interactive audio tag panel (review the catalogue match, edit fields, embed
  cover and lyrics) after a manual download, and per-row history actions (play,
  open folder, redownload, retag).
- Accurate download-size estimates; optional rounded window corners (squared when
  maximized); clear-history and clear-logs actions.
- Trimming reworked to clip the finished local file (the bundled ffmpeg has no
  working TLS, so it cannot fetch ranges itself).
- An expanded unit-test suite and an end-to-end smoke test.
- A one-time migration path for existing users: the AppImage is signed with the
  same minisign key the Tauri app used, so the legacy updater accepts it.

**Before it replaces the published app:** Windows packaging (the in-app updater
and `latest.json` are currently Linux-only).

## Released

### 4.x

- **4.4.0** (2026-11-21) — Per-item format in the queue; audio bitrate for queued
  audio; AppImage application icon and desktop/AppStream metadata.
- **4.3.0** (2026-10-28) — ISRC-exact YouTube-Music matches; optional SoundCloud
  lossless; updated download engine.
- **4.2.0** (2026-10-24) — Clear the yt-dlp cache from the app; engine update;
  trimming on more sites.
- **4.1.0** (2026-10-22) — Per-download video codec and audio bitrate; new output
  formats; safer downloads.
- **4.0.0** (2026-10-16) — Redesigned interface; Logs tab; theme preference
  (dark / light / system); accessibility work.

### 3.x

- **3.9.0** (2026-10-14) — Instagram photos; multi-connection downloads (aria2c,
  opt-in); sturdier packaging.
- **3.8.0** (2026-09-15) — OK.ru support; automatic YouTube PO token; Instagram
  highlights with multiple stories; "backend unreachable" banner.
- **3.7.0** (2026-09-09) — Genre in the auto-tag; configurable loudness target;
  GitHub response caching; SoundCloud playlist track names; live history updates.
- **3.6.0** (2026-09-01) — Fix for the stuck "Preparing…" state; SponsorBlock-
  outage resilience; bundled supported-site logos.
- **3.5.0** (2026-08-30) — CLI shipped in the `.deb`/`.rpm`; music filed into an
  Artist/Album library; cumulative "What's new"; opt-in YouTube PO token.
- **3.4.0** (2026-08-30) — Self-healing downloads; "restart to finish updating";
  expanded CLI.
- **3.3.0** (2026-08-20) — Sharper, faster trims; steadier YouTube; cover art on
  Windows; layout polish.
- **3.2.0** (2026-08-16) — Command-line interface; Instagram stories and posts;
  sharper music matches.
- **3.1.0** (2026-07-21) — Browser extension ("Send to Yoink"); open-source
  license listing.
- **3.0.0** (2026-07-17) — Send to Yoink from the browser; desktop integration
  (deep links).

### 2.x

- **2.9.0** (2026-07-06) — Settings redesign.
- **2.8.0** (2026-07-05) — Tag-based filenames ("Artist – Title").
- **2.7.0** (2026-07-04) — In-app automatic updates; post-update "What's new".
- **2.6.0** (2026-07-03) — Per-format queue; albums and playlists with per-track
  selection; playlist sync.
- **2.5.1** (2026-07-03) — Playlist covers; unified preview card; YouTube Music as
  audio.
- **2.5.0** (2026-07-02) — Amazon Music covers; better auto-tagging; opt-in lyrics;
  improved history; correct YouTube quality labels; faster startup.
- **2.4.0** (2026-06-29) — More video sources; VR trimming and silent-source
  warnings; steadier downloads.
- **2.3.1** (2026-06-27) — Windows fixes (covers, music import, lyrics); sturdier
  cookie fallback.
- **2.3.0** (2026-06-25) — Embedded and synced lyrics; cookie handling that doesn't
  break search; `.nfo` metadata sidecars.
- **2.2.0** (2026-06-22) — Resumable playlist downloads; download presets; broader
  VR tagging.
- **2.1.0** (2026-06-18) — One download at a time (lock); starts even when the port
  is taken; full progress reporting; advanced-options grouping.
- **2.0.0** (2026-06-13) — Music-service import (Spotify / Deezer / Apple Music /
  Tidal / Amazon Music); SoundCloud search; 14 interface languages; resumable
  downloads.

### 1.x — foundation

- **1.9.1** (2026-06-11) — Auto-tag sharpening; queue parity; i18n and accessibility.
- **1.9.0** (2026-06-08) — Immersive / VR video; download queue; robustness and
  security.
- **1.8.1** (2026-06-08) — Auto-tag merges Apple Music + Deezer with better ranking;
  retag from history.
- **1.8.0** (2026-06-07) — Filename templates; per-download video codec and audio
  bitrate.
- **1.7.0** (2026-06-07) — Trim to a start/end range (video and audio).
- **1.6.0** (2026-06-07) — Type-to-search (YouTube search from the URL field).
- **1.5.1** (2026-06-05) — SponsorBlock and chapters fixes.
- **1.5.0** (2026-06-05) — SponsorBlock: cut or mark sponsor / intro / outro
  segments.
- **1.4.0** (2026-06-04) — Multi-catalogue auto-tag (Apple Music / Deezer /
  MusicBrainz / Automatic); queue resilience.
- **1.3.0** (2026-06-04) — Audio auto-tag card with review and edit (Apple Music);
  playlist lossless detection; cookie file picker.
- **1.2.0** (2026-06-02) — Threads, Kick and Reddit sources; `curl_cffi`
  impersonation past TLS-fingerprint blocks.
- **1.1.0** (2026-06-02) — In-app signed self-update (Windows + AppImage); multiple
  audio tracks (MKV).
- **1.0.0** (2026-06-02) — Initial release: local downloader (yt-dlp + bundled
  ffmpeg); MP4 / MOV / MKV containers; embedded subtitles and chapters.

## Planned

Not committed to a release; picked up as capacity allows. Desktop (Linux and
Windows) is the focus.

- **VR studio list as versioned data** — move the hardcoded studio list out of
  source into data.
- **Subscriptions and scheduled downloads** — follow a channel or playlist and
  auto-grab new items (PVR-style), with OPML import/export. Needs tray/autostart
  and a download archive.
- **macOS build** — `yoink-core` and the ffmpeg build port cleanly; needs a Mac to
  build, sign and notarize. Would unblock re-adding Safari to the cookie sources.
- **Android** — `yoink-core` compiles to Android natively; the work is a native
  shell plus an ffmpeg/yt-dlp integration.
- **Windows on ARM64 (native)** — the x64 build already runs on Snapdragon Win11
  via emulation; a native `aarch64-pc-windows-msvc` build is feasible and mostly
  needs an ARM64 runner and a `latest.json` entry.

## Non-goals

Decisions kept here so they are not re-proposed.

- **Concurrent downloads** — the queue is sequential by design, enforced by a
  single-download lock so two jobs can't collide on the same partial file.
  Parallelising would mean redesigning the progress and history UI for a modest
  gain; revisit only with a dedicated multi-progress UI.
- **In-app yt-dlp update** — Yoink reports the bundled yt-dlp version only; it is
  updated with each Yoink release.
- **Local media conversion / editing** — transcoding, remuxing, clipping to
  GIF/WebP or grabbing a frame from a local file is out of scope. Yoink downloads
  audio and video; it is not a converter, editor or frame grabber.
