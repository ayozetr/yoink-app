# Yoink — Roadmap

> Single source of truth for where Yoink is going. **Yoink** is a local,
> high-fidelity media downloader — yt-dlp + bundled ffmpeg in a self-contained
> Tauri desktop app. Philosophy: **local-first**, **honest about quality** (never
> fake "lossless"), no fluff.
>
> Legend: ✅ shipped · 🚧 in progress · ⬜ planned · effort **S**/**M**/**L**.
> Per-feature shipped detail lives in the [GitHub releases](https://github.com/ayozetr/yoink-app/releases)
> and git history — this file stays forward-looking.

## 📍 Status

- **Current release:** **v1.9.1** — hardening + polish: SSRF fix, sharper audio
  auto-tagging, resilient `/api/info`, queue parity (VR auto-detect + format
  defaults), and accessibility/i18n fixes. (v1.9.0: immersive VR + the queue.)
- **Platforms:** Linux (AppImage · deb · rpm) + Windows (msi · NSIS), self-updating.
- **Stack:** React 19 / TS / Tailwind · FastAPI / yt-dlp · ffmpeg bundled as a sidecar.
- **Health:** backend (pytest) + frontend (vitest) green · `npm audit` 0 · strict TS.

---

## ✅ Shipped (by area)

A condensed map of what already works.

**Core engine**
- URL analysis (`POST /api/info`) → preview with the real available formats;
  **YouTube search** from the URL field; flat **playlists**.
- **Anti-bot**: yt-dlp + `curl_cffi` browser impersonation (default) gets past most
  Cloudflare/TLS-fingerprint blocks; custom **Threads (Meta)** extractor.
- **Live downloads** over WebSocket (percent/speed/ETA), **cancel + retry**, off-thread.

**Output & quality**
- Video: **MP4 / MOV / MKV** merge, embedded **subtitles + chapters**, **multi-audio**
  (MKV), **codec** preference (H.264/VP9/AV1).
- Audio: **MP3 / M4A** + honest **FLAC / WAV** (gated to lossless sources), **bitrate**
  picker, M4A by stream-copy.
- **Trim/clip** a time range · **SponsorBlock** (remove/mark).

**🥽 Immersive VR** *(v1.9.0)* — heuristic detection (studios/markers/aspect ratio),
**11 stereo/projection layouts**, projection **name suffix** + injected **Spherical
Video V2** (`st3d`/`sv3d`) into MP4/MOV, **per-channel** layout memory, batch on playlists.

**Library & tagging**
- **Audio auto-tagging** (Apple Music + Deezer + MusicBrainz) with a review step,
  cover art, single + batch, **re-tag from history**.
- **History + stats** (SQLite): rich rows (time/format/size/quality), cover art,
  open file/folder, clear.

**📋 Queue** *(v1.9.0)* — persistent, sequential, **resumes** interrupted items;
honors your **default container / audio format** and **auto-detects + tags VR**
per item *(v1.9.1)*.

**🛡️ Hardening** *(v1.9.1)* — SSRF-safe auto-tag cover fetch (shared guard),
resilient `/api/info` (transient-aware retry → 503 vs 422 vs a permanent error),
**WAL** history under the concurrent queue, trim-range guards, and much sharper
auto-tag title parsing (ES/FR/JP + CJK/K-pop noise, validated on ~600 real
playlist titles).

**Settings** — download dir, defaults, filename template, bandwidth limit, proxy
(http/socks), cookies (browser + icons / `cookies.txt`), SponsorBlock, language,
app + yt-dlp version.

**Platform & polish** — Tauri desktop (Linux + Windows), **signed self-update**,
desktop notifications, taskbar/title progress, global shortcuts, **EN/ES** i18n,
**WCAG-AA** pass (contrast, reduced-motion, ARIA incl. the search combobox),
security-hardened (path guards, SSRF-safe thumbnail proxy w/ pinned DNS, settings
validation), strict TS + tests.

---

## 🎯 Next up — toward v1.10

The highest value/effort work, in order. Most surfaced from the v1.9.0 audit.
*(Queue ↔ feature parity — VR + format defaults — shipped in v1.9.1.)*

1. **Backend logging & observability** (M · **high**) — there is **zero** logging
   today; yt-dlp's error text is never captured. Structured logs to
   `~/.yoink/logs/`, persist the error string in history, surface it in the UI.
   Unblocks debugging everything else.
2. **Sidecar readiness gate + dynamic port** (M · **high**) — poll `/health`
   before revealing the UI (the splash already exists) and fall back if **8756**
   is taken (it's hardcoded). Affects every cold start of the desktop app.
3. **First-run empty state** (S · medium) — example URL, "type to search", link to
   supported sites. Big first-impression win for new users.
4. **Resume partial downloads** (M · medium) — enable yt-dlp `continuedl` so an
   interrupted `.part` resumes on retry instead of restarting from zero.
5. **Persist the remaining download defaults** (S · medium) — container + audio
   format now persist *(v1.9.1)*; subtitles + chapters still don't.

---

## 🧰 Backlog (vetted, by theme)

Not committed and not release-ordered — picked from as capacity allows.

### 🎬 Download & conversion
- 🟡 **Import from music services** *(implemented locally — pending release)* —
  paste a track/album/playlist URL from **Spotify, Deezer, Apple Music, Tidal or
  Amazon Music** → resolve it **keyless** (public APIs / embed scrapes, like the
  Threads extractor) → rank a YouTube match with a **spotDL-ported** scorer →
  download + auto-tag with the *exact* source metadata. One source-agnostic
  pipeline (`/api/music/{resolve,match}` + `MusicImportCard`); only the resolver
  differs per service. A single track shows a square-cover preview;
  albums/playlists a track-picker. The spotDL-ported matcher hits **98%** of
  tracks on a 403-track real-playlist test across all five sources (token-set
  title ratio, glyph folding, name+artist-aware duration gate).
  - **Deezer** ⭐ — public API `api.deezer.com` (no key) · full JSON, **no track
    cap** · the standout (we already use its keyless API for auto-tagging).
  - **Apple Music** — iTunes Lookup API for albums/tracks; **playlists** scrape
    the web page's `serialized-server-data` blob (title/artist/duration/artwork).
  - **Spotify** — public embed `__NEXT_DATA__` + anonymous web-player token paging
    · ~**100-track cap** on big playlists (anonymous API rate-limits the full
    fetch); a bring-your-own-credentials Settings field would lift it.
  - **Tidal** — embed `<list-item>` scrape + the regular page's og tags.
  - **Amazon Music** — `music.amazon.*/embed/{asin}` HTML scrape; the embed carries
    no cover/durations, so those are **backfilled from Deezer's keyless API**
    (matched by a loosened title key).
  API-based (Deezer/Apple) are sturdier; the embed scrapes (Spotify/Tidal/Amazon)
  are more fragile — a page change needs an extractor tweak, like Threads.
- 🟡 **Search beyond YouTube** *(implemented locally — pending release)* — a
  **YouTube ↔ SoundCloud** selector in the header (persisted) drives the URL-field
  typeahead, flipping the yt-dlp search prefix (`ytsearch`→`scsearch`). More
  platforms drop in by adding a prefix.
- ⬜ **Split by chapters** (M) — one file per chapter (`--split-chapters`).
- ⬜ **Playlist sync / `--download-archive`** (M) — only fetch what's new.
- ⬜ **Sidecar exports** (S) — `.info.json` / thumbnail / loose `.srt`/`.vtt`.
- ⬜ **Subtitles as separate files + auto-translate** (M).
- ⬜ **Transcode local files** (M) — drop a file (no URL), remux/re-encode.
- ⬜ **Clip → GIF/WebP** (M) — export a trimmed range (ffmpeg palette).
- ⬜ **Loudness normalization** (M) — ffmpeg `loudnorm` (EBU R128).
- ⬜ **Capture frame / embed poster** (S).
- ⬜ **Download presets/profiles** (M) — named option bundles, one click.
- ⬜ **Library subfolders** (M) — path templates (`%(uploader)s/%(title)s`).

### 📋 Playlists
*Surfaced testing real YouTube Music "Hits" mixes (`RD…`) and curated `PL` lists —
extraction is solid (49–144 tracks, both URL forms, capped at 200 with a
`truncated` flag); these are curation/scale/persistence gaps.*
- ⬜ **Persistent playlist downloads** (M · **high**) — a playlist batch runs through
  the in-panel flow (`DownloaderPanel` `startQueue`/`runJob`), **not** the
  persistent queue, so a 144-track download has **no resume**: closing /
  refreshing / a crash loses all progress. Route playlist batches through the
  persistent queue (or persist the batch + offer resume). The standout gap for
  big lists; overlaps with *Resume partial downloads* and the engine-unify big bet.
- ⬜ **Filter/search within the entry list** (S) — up to 200 items scroll in a fixed
  `max-h` box with no filter; add a "filter tracks…" input to narrow the list.
- ⬜ **Range + smarter selection** (S) — only select-all/none today; add shift-click
  range selection (and maybe "select first N").
- 🟡 **Batch totals** *(implemented locally — pending release)* — the playlist card
  shows the current selection's count + **total duration** ("23 selected · 1h 18m").
  A rough **size** estimate is still pending (flat entries carry no per-item
  formats, so it needs a probe/heuristic).
- ⬜ **Audio-first for music playlists** (S) — YT Music mixes (`RD…`/`OLAK…` list ids
  or `music.youtube.com`) are music-intent; default `kind` to **audio** for them
  instead of video.
- ⬜ **Lazy-load / virtualize the entry thumbnails** (S/M) — up to 200 `<Thumbnail>`
  fire ~200 proxy requests at once on render; `loading="lazy"` or virtualize.
- ⬜ **Per-item retry in the batch summary** (S) — when some tracks fail, retry just
  those (the single-job retry exists; extend it per failed playlist item).

### 🎵 Audio library
- ⬜ **Auto-tag title parsing for non-Western formats** (M) — the filename noise
  stripper now cleans **~93%** of real popular-playlist titles (English/Spanish/
  French "(Official Video)/(Vídeo Oficial)/(Clip officiel)", a "| album/label"
  suffix, "M/V", wrapping quotes, "(Explicit)"). The ~7% tail that still leaks has
  **no "Artist - Title" structure** — K-pop (`ARTIST 'TITLE' MV`), Bollywood
  (`Song | Movie | Cast`), quoted-title headers — so artist/title can't be split
  reliably. Needs format-aware heuristics (or fingerprint-based identify);
  meanwhile the manual edit/search in the tag card covers it.
- ⬜ **Embed source thumbnail as cover** on audio (S).
- ⬜ **Lyrics in auto-tagging** (L) — LRCLIB (free, no key).
- ⬜ **Media-server naming presets** (S) — Jellyfin/Plex/Navidrome layouts.
- ⬜ **NFO sidecars** (M).

### 🖥️ UX / UI
- ⬜ **Drag-and-drop a link** onto the window (M).
- ⬜ **Responsive PreviewCard** (M) — stack the fixed thumbnail + controls on narrow widths.
- ⬜ **Unify PlaylistCard checkboxes** onto `Toggle` (S).
- ⬜ **Re-download / re-analyze from history** (S).
- ⬜ **Skip-current vs cancel-all** in the queue (M).
- ⬜ **Reorder the queue** (drag up/down) (M).

### 🔌 OS & integrations
- ⬜ **`yoink://` deep link** (M · **high**) — enables "send to Yoink" from anywhere,
  sidestepping the local-CORS lock; single-instance already focuses the window.
- ⬜ **System tray + close-to-tray + autostart** (S/M) — a true always-on manager.
- ⬜ **Thin CLI over the local API** (S/M) — `yoink <url>` for scripts.
- ⬜ **Browser extension** "Download with Yoink" (M) — context-menu → `yoink://`.
- ⬜ **More distribution channels** — AUR (S) / Flatpak (M) / winget + Chocolatey (M).

---

## 🛠️ Quality & hardening

Engineering work that keeps the app fast, debuggable and reproducible. (Items
also in *Next up* are the urgent ones.)

- ⬜ **WebSocket open timeout** (S) — fail fast if the handshake hangs on a slow boot.
- ⬜ **SQLite schema versioning** (S) — `PRAGMA user_version` + idempotent migrations.
- ⬜ **Generate TS types from OpenAPI** (M) — kill manual `download.ts` ↔ `media.py` drift.
- ⬜ **Pin yt-dlp exactly per release** (S) — reproducible builds.
- ⬜ **ruff + mypy in CI** (S) — currently only `pytest` runs (CI itself paused on billing).
- ⬜ **More tests** (S) — `_host_is_blocked`, queue/VR integration in the WS,
  frontend `estimatedSizeBytes`/`formatBytes`.
- ⬜ **PyInstaller `--onedir`** (M) — faster cold start (no per-launch re-extraction).

## 🥽 VR follow-ups

- ⬜ **Spherical Video V1** (uuid XML) (M) — for older players + YouTube re-upload,
  which expect the legacy XML blob alongside the V2 boxes.
- ⬜ **MKV `StereoMode` tag** (M · low) — MKV currently gets only the name suffix.
- ⬜ **Fisheye/EAC projection box** (M · low) — 5 of 11 layouts are name-suffix only.
- ⬜ **Post-tag ffprobe validation** (S) — confirm a player will read the boxes.
- ⬜ **VR-studio list as versioned data** (S · low) — not a hardcoded tuple.

---

## 🔮 Big bets (future — separate mini-projects)

Bigger, standalone efforts. Desktop (Linux/Windows) stays the focus.

- ⬜ **Subscriptions + scheduled downloads** (L) — follow a channel/playlist and
  auto-grab new items (PVR-style), OPML import/export. Needs tray/autostart + archive.
- ⬜ **macOS build** (L) — the sidecar + ffmpeg bundle should port; needs a Mac to
  build/sign/notarize. Unblocks re-adding **Safari** to the cookies selector.
- ⬜ **Android** (L) — the PyInstaller sidecar can't run on Android, so the local
  server must be replaced. Routes: embed Python (Chaquopy) + ffmpeg-kit · native
  yt-dlp lib (Seal-style) · thin remote client. Proven feasible (cf. Seal).

---

## 🚫 Deliberately deferred / non-goals

Decisions kept here so they aren't re-proposed.

- **Concurrent downloads** — the queue is **sequential by design**. Parallelising
  means redesigning the whole progress/history UI for a modest gain and real
  regression risk; revisit only with a dedicated multi-progress UI.
- **In-app yt-dlp update** — **not happening, by design.** Yoink only *reports* the
  bundled yt-dlp version; it's updated with the next Yoink release (owner's decision).
