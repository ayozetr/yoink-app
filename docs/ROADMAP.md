# Yoink — Roadmap

Status of the project: what's done and what's next.

Legend: ✅ done · 🚧 in progress · ⬜ planned

## Phase 0 — Foundations ✅

- ✅ Frontend scaffolded with Vite (React 19 + TypeScript)
- ✅ Tailwind CSS v3 configured (`tailwind.config.js`, `postcss.config.js`, global CSS)
- ✅ `lucide-react` icons
- ✅ `npm audit` clean (0 vulnerabilities)
- ✅ Initial mockup decomposed into a scalable architecture
  (`components/ui`, `components/layout`, `features/`, `types/`)
- ✅ Shared domain types mirroring the backend JSON contract
- ✅ Git repository synced to `git@github.com:ayozetr/yoink-app.git`

## Phase 1 — Backend metadata ✅

- ✅ FastAPI app structure (typed: main, core, models, routers, services)
- ✅ Python `venv` + pinned `requirements.txt` (fastapi, uvicorn, yt-dlp, pydantic)
- ✅ yt-dlp wrapper with `download=False` metadata extraction
- ✅ `POST /api/info` endpoint (title, duration, thumbnail, formats)
- ✅ `/health` liveness probe
- ✅ CORS configured for the local Vite dev server
- ✅ Project documentation (CLAUDE.md, /docs, READMEs)
- ✅ Unit tests for the services and routes (`backend/tests`, pytest)

## Phase 2 — Connect frontend ↔ backend ✅

- ✅ API client in the frontend (typed `fetch` wrapper, `src/lib/api.ts`)
- ✅ Wire `handleAnalyze` → `POST /api/info`, populate the preview card
- ✅ Loading / error states for analysis (cancels in-flight requests)
- ✅ Derive format & quality selectors from the real `formats` list
- ✅ TS types mirror the Pydantic contract 1:1 (snake_case, incl. `formats`)

## Phase 3 — Downloads + live progress ✅

- ✅ `WS /api/ws/download` starts a yt-dlp job (run off-thread via
  `asyncio.to_thread`); progress is streamed over the same socket
- ✅ yt-dlp `progress_hooks` capture percent / speed / ETA, bridged to the
  event loop through an `asyncio.Queue`
- ✅ Stream progress to the UI via WebSockets (typed event contract)
- ✅ Animate the progress bar from real events (download → processing → done)
- ✅ ffmpeg merge for high-quality video + audio (`merge_output_format=mp4`);
  MP3 extraction for audio-only
- ✅ OS-agnostic save paths to `~/Downloads/Yoink` via `pathlib`

> Cancel/retry of in-flight jobs is deferred to Phase 4.

## Phase 4 — History & persistence ✅

- ✅ Persist completed/failed downloads in SQLite (`~/.yoink/history.db`,
  stdlib `sqlite3`, no new deps); `GET /api/history`
- ✅ Real download statistics (count, total transferred); `GET /api/history/stats`
- ✅ "Open folder" wired to the OS file manager (`POST /api/open`,
  xdg-open/open/explorer), constrained to the download dir
- ✅ Cancel (close the socket → `threading.Event` aborts the job) and retry
  (re-issue the last selection) from the UI
- ✅ Sidebar history + stats load real backend data and refresh after each job

## Extras (beyond the original roadmap) ✅

- ✅ **Playlists:** `POST /api/info` returns a flat playlist listing; the UI
  shows a `PlaylistCard` with per-item checkboxes and downloads the selected
  items sequentially ("X of N" progress)
- ✅ **Cookies** for sign-in-only content, via settings (`YOINK_COOKIES_FROM_BROWSER`
  or `YOINK_COOKIES_FILE`), applied to both metadata and downloads
- ✅ **URL normalization** (e.g. TikTok `/photo/` → `/video/`)
- ✅ **Clear history** button (`DELETE /api/history`)

## Phase 5 — Packaging & polish ✅

- ✅ One-command local startup (`scripts/dev.py` runs backend + frontend;
  `scripts/setup.py` for venv + deps)
- ✅ Desktop packaging with Tauri (`src-tauri/`) for **Linux & Windows**: the
  FastAPI backend **and ffmpeg/ffprobe** ship as a PyInstaller sidecar the app
  launches on startup (self-contained — no Python/ffmpeg needed). Build with
  `python scripts/fetch_ffmpeg.py && python scripts/build_backend.py && npm run tauri build`.
  Linux: `.AppImage`/`.deb`/`.rpm`; Windows: `.msi`/NSIS `.exe`. See
  [`releasing.md`](releasing.md)
- ✅ Settings UI (download dir, default format/quality, cookies) — persisted
  via `GET`/`PUT /api/settings` to `<data_dir>/settings.json`
- ✅ End-to-end tests (Playwright, `e2e/`, mocked API)

## Phase 6 — Self-update ✅ (shipped in v1.1.0)

- ✅ Show the current app version in the Settings modal (injected from
  package.json at build time)
- ✅ "Check for updates" → now uses `tauri-plugin-updater`'s `check()` against
  the release `latest.json`
- ✅ **In-app download & install** via `tauri-plugin-updater` (signed artifacts
  + `latest.json`). Auto-installs on **Windows** and the **Linux AppImage**;
  `.deb`/`.rpm` (and other cases) fall back to a "view release" link — platform
  detected via `plugin-os` + the `is_appimage` command.
- ✅ Release flow signs builds (`TAURI_SIGNING_PRIVATE_KEY[/_PASSWORD]`) and
  publishes `latest.json` + `.sig` assets — see `docs/releasing.md` §6
  *(shipped in v1.1.0; self-update applies from v1.1.0 onward)*

> The update check needs the GitHub repo to be **public** (the unauthenticated
> API returns 404 for private repos).

## Phase 7 — Other platforms → moved to "Future" (end of this file)

Desktop (Linux/Windows) is the current focus; **macOS** and **Android** are
parked as separate, future mini-projects in [Future](#future--other-platforms)
at the end.

## Phase 8 — Branding, i18n & polish ✅ (→ v0.9.0)

> More immediate than Phase 7 (Android). Grouped by area.

### Branding & naming
- ✅ README title → "Yoink Media Downloader" (+ badges: release, platforms,
  Tauri, React, FastAPI, yt-dlp, license, React Doctor score)
- ✅ App header: "Media Downloader" → "Yoink Media Downloader"
  (`DownloaderHeader.tsx`)
- ✅ Installer/exe metadata: **Copyright** = GitHub user (`© ayozetr`) via Tauri
  `bundle.copyright`. Left `productName = "Yoink"` (changing it renames the
  binary/installer and risks breaking sidecar paths).

### UX fixes
- ✅ **"Developed by ayozetr" link** now opens the profile in the packaged app
  via the Tauri **opener** plugin (`openExternal`), with a `window.open`
  fallback in the dev browser.
- ✅ Cookies hint: "no para vídeos públicos" → "no para **contenido público**"
  (`SettingsModal.tsx`)
- ✅ **Responsive design**: the sidebar + main column stack on narrow windows
  (fluid widths, `lg:` breakpoint); modal scrolls instead of clipping.

### Internationalization (English + Spanish)
- ✅ Translated the UI to **English + Spanish** with `react-i18next` (namespaced
  dictionaries in `src/i18n/locales/`)
- ✅ **Language selector** in Settings (System / Español / English), persisted to
  `localStorage` (`yoink-lang`) via the i18next detector
- ✅ **Detect the system language** (`navigator.language`) as the default
- ✅ Backend error messages → **English**; the frontend shows them as-is and
  handles its own translations separately
- ✅ E2E pin the Playwright locale to `es-ES` so the Spanish assertions stay
  deterministic after i18n

### Legal
- ✅ Added a **LICENSE** — **CC BY-NC-SA 4.0** from v1.0.0 (v0.9.0 shipped under
  MIT). The bundled LGPL ffmpeg and Unlicense yt-dlp keep their own licenses.

### Extras shipped in v0.9.0
- ✅ **Native folder picker** for the download dir (Tauri **dialog** plugin) —
  a folder icon at the end of the field opens the OS directory chooser
- ✅ **Custom dropdown** (`Select`) replacing the unstyled native `<select>`
  popup, used for format/quality/language across Settings, preview and playlist
  (dark, `fixed`-positioned so it isn't clipped by the modal)
- ✅ **Custom context menu** (`EditMenu`): minimal Cut/Copy/Paste on text fields
  only, suppressing the webview's native Print/Save-as menu; closes on the
  capture phase so it works inside modals
- ✅ **Security audit**: `npm audit` (0), `pip-audit` (0, bumped pytest to clear
  CVE-2025-71176), `cargo audit` (0 vulns; only transitive GTK3 "unmaintained"
  warnings)
- ✅ **react-doctor** pass (score 92/100): fixed the genuine, behavior-safe
  findings; documented the verified false positives

## Phase 9 — Advanced formats & going public ✅ (v1.0.0 released & public)

The 1.0 milestone: richer output formats **and** opening the repo to the world.
Shipped in **v1.0.0** (public). Multi-audio and the self-terminating backend
remain as noted follow-ups.

### Advanced output formats & quality-aware audio

Today Yoink offers MP4 (video) + MP3 (audio). Expand to give real control, and
be **honest about source quality** (don't inflate lossy sources into "lossless").

**Phase 1 (done):** containers, audio formats and honest-lossless gating.

### Video containers
- ✅ Offer **MP4** (default), **MOV**, **MKV** (`merge_output_format` driven by
  `DownloadRequest.container`); a container picker in the preview/playlist cards
- ✅ **Embed subtitles** (`writesubtitles`/`writeautomaticsub` +
  `FFmpegEmbedSubtitle`) and **chapters/metadata** (`FFmpegMetadata`,
  `add_chapters`/`add_metadata`) into the merged output
- ✅ Subtitle language picker (None / All / available codes), shown only when
  the source actually exposes subtitles; `/api/info` reports `subtitle_langs`
  and `has_chapters`
- ✅ **Multiple audio tracks** (MKV) — `audio_multistreams` uses
  `bv*+mergeall[vcodec=none]` + `allow_multiple_audio_streams`; a UI toggle is
  shown for MKV when the source has more than one audio language *(in main,
  shipped in v1.1.0)*

### Audio formats
- ✅ Lossy: **MP3**, **M4A**; Lossless: **FLAC**, **WAV** — selectable per
  download (`DownloadRequest.audio_format` → `FFmpegExtractAudio` codec;
  lossless variants skip `preferredquality`)
- ✅ **M4A by copy**: m4a selects an AAC/m4a source so `FFmpegExtractAudio`
  copies the stream (`-c copy`) instead of re-encoding it

### Source-quality detection (honest lossless)
- ✅ `/api/info` inspects each format's `acodec`/`abr` → exposes
  `source_lossless` (flac/alac/wav/pcm/tta/wavpack/ape) and `best_audio_abr`
- ✅ Frontend gates FLAC/WAV to lossless sources: the options are disabled and
  an inline warning shows ("this source isn't lossless — FLAC/WAV would just
  upscale it"); a stale lossless choice falls back to MP3
- ✅ Rationale: YouTube serves lossy (Opus ~160 kbps / AAC); transcoding to FLAC
  just bloats the file with **no quality gain**. Bandcamp/SoundCloud can be
  genuinely lossless.

### Packaging robustness (orphaned sidecar) ✅

The PyInstaller `--onefile` `yoink-backend.exe` is a *bootloader* that unpacks
to a temp dir and spawns the real Python process as a child. On Windows
`child.kill()` (Tauri's `RunEvent::Exit`) only killed the bootloader, so the
Python child lingered — holding port 8756 and the on-disk `yoink-backend.exe`.
That made the NSIS updater fail with *"Error opening file for writing
…\yoink-backend.exe"* (seen upgrading to 0.9.0; worked around by `taskkill`
before Retry). Implemented two complementary layers (built & compile-checked on
both OSes, and **validated in runtime**: the in-app v1.1.0 → v1.2.0 self-update
on Windows upgraded cleanly, with no locked-exe error):

- ✅ **Rust kills the process tree on exit** — `kill_sidecar()` runs
  `taskkill /PID <pid> /T /F` on Windows (was a bare `child.kill()`), reaping
  the bootloader *and* the Python child.
- ✅ **NSIS pre-install hook** (`src-tauri/installer-hooks.nsh`,
  `NSIS_HOOK_PREINSTALL`): `taskkill` of `yoink.exe` / `yoink-backend.exe`
  before copying files, so an in-place update never trips on the locked exe.
- ✅ **Self-terminating backend** — exits on stdin EOF (packaged build only,
  `sys.frozen`), covering a hard crash where `RunEvent::Exit` never fires
  *(shipped in v1.1.0)*

### Going public

- ✅ **Audited the repo + git history for secrets** — clean: no secrets in the
  working tree or full history, no sensitive files tracked
  (`.env`/db/keys/cookies), no VM/host/IP references; `.gitignore` covers
  `venv`/`node_modules`/`.env`/`target`/`dist`/`vendor`
- ✅ **LICENSE** in place — **CC BY-NC-SA 4.0** (non-commercial, share-alike);
  v0.9.0 shipped under MIT
- ✅ Polished the README: badges (release/license/stack/React Doctor), a
  screenshot (`docs/screenshot.png`), and a quick-start
- ✅ GitHub repo **description + topics** set (12 topics: yt-dlp, ffmpeg, tauri,
  react, typescript, fastapi, python, …)
- ✅ **Made the repo public** — the in-app "Check for updates" now works (the
  unauthenticated GitHub API serves the latest release instead of 404ing)

## Post-1.0 ideas (backlog)

Mostly shipped across v1.1.0–v1.2.0; a couple of ideas remain planned (⬜).

- ✅ **"Supported sites" popup** *(shipped in v1.1.0)*. The header
  subtitle ends in a "from many sites" / "de múltiples webs" link that opens a
  modal of hand-verified sites (name + logo): YouTube, YouTube Music, Vimeo,
  Dailymotion, Instagram, TikTok, X, Facebook, SoundCloud, BandLab, Twitch,
  Medal — curated, not yt-dlp's full ~1800 list. Extend the typed list as more
  are verified.
- ✅ **Get past Cloudflare-protected sites** *(ships in v1.2.0)*. Root cause: the
  backend's **TLS fingerprint**. Python 3.14 ships OpenSSL 3.6.x, whose
  fingerprint Cloudflare blocks with a 403 before any page loads, and `curl_cffi`
  (impersonation) can't run on 3.14 (yt-dlp wants `curl_cffi <0.15`, no 3.14
  wheel). Confirmed by Seal (Android), whose yt-dlp impersonates. **Fix (verified
  end-to-end — the 403 site resolves from the packaged sidecar, 77 tests pass):**
  - Backend on **Python 3.13** (isolated via `uv`, system Python untouched) with
    `yt-dlp[default,curl-cffi]` → yt-dlp impersonates a browser TLS fingerprint
    automatically for extractors that require it.
  - `scripts/build_backend.py` adds `--collect-all curl_cffi` so impersonation
    survives PyInstaller packaging.
  - **Executable-stack fix:** uv's `libpython3.13.so` has an exec stack (`RWE`)
    the kernel rejects when PyInstaller `dlopen`s it, so the packaged sidecar
    wouldn't start. `scripts/setup.py` copies the runtime to `backend/.python-rt`
    and clears the flag on the **copy** (`patchelf --clear-execstack`, never uv's
    shared file), building the venv from there. **Windows (Python 3.12) is
    unaffected.**
  - Best-effort overall — aggressive challenges, logins (cookies) or DRM still
    won't work.
- ✅ **Threads (Meta) support** *(ships in v1.2.0)*. yt-dlp has no Threads
  extractor, and Threads only serves the media to a real browser TLS
  fingerprint, so a plain request gets a video-less HTML (hence the old
  `Unsupported URL`). A small custom extractor
  (`backend/app/services/threads_extractor.py`, registered on the `YoutubeDL`
  instances via `add_info_extractor` — yt-dlp itself is never modified, so
  updates can't clobber it) downloads the post with curl_cffi impersonation and
  parses the embedded Instagram-style media JSON (video, cover thumbnail,
  caption, duration). It's inserted ahead of the generic extractor so it wins
  for `threads.com`/`.net`, and resolves to the Instagram-hosted video.
- ✅ **More verified sites** *(ships in v1.2.0)*: **Kick** and **Reddit** (native
  yt-dlp extractors) plus **Threads** added to the "supported sites" popup —
  inserted after Twitch, X and Instagram respectively.
- ✅ **Clock-formatted durations** *(ships in v1.2.0)*: durations always read as
  `M:SS` / `H:MM:SS` (e.g. `0:05`) now, instead of yt-dlp's bare seconds for
  sub-minute clips — formatted from the raw seconds in `ytdlp_service`.
- ✅ **Hotlink-protected thumbnails** *(ships in v1.2.0)*: the `/api/thumbnail`
  proxy forwards a `Referer` (the page URL), so CDNs that 403 cross-origin image
  requests now serve the cover. Propagated through the `Thumbnail` component
  (direct → proxy-with-referer → placeholder).
- 🚧 **Audio auto-tagging via Apple Music** *(opt-in, with a review step — in
  `feature/audio-autotag`)*. Tag downloaded audio with real artist / album /
  title / year + cover art for a proper music library. Metadata comes from the
  **iTunes Search API** (Apple Music) — free, key-less, broad streaming coverage,
  and it returns the single / EP / album versions a song appears on, each with
  its own high-res cover (the approach Automatag uses). Tags are written with
  **`mutagen`** (already a yt-dlp dep), so **no new dependencies, nothing to
  bundle, no API key**.
  - **Why not acoustic fingerprinting?** Prototyped AcoustID/Chromaprint +
    MusicBrainz + Cover Art Archive, but it needs a bundled `fpcalc` binary and
    an API key, and its open DB misses non-mainstream/streaming tracks (verified:
    an underground release AcoustID had never seen). Searching Apple Music by the
    file's "Artist - Title" covers far more for YouTube rips, with the review
    step + manual search for the rest. Dropped fingerprinting entirely.
  - **Flow: identify → review → apply.** Backend endpoints `identify` (search by
    filename) / `search` (manual) / `apply` — nothing touches the file until
    confirmed. The modal lists the matching versions to pick from, shows editable
    fields + cover, and a manual search box; Apply writes the tags + cover.
  - **Done (backend + UI):** `autotag_service` + `/api/autotag/{identify,search,
    apply}` and the review modal, wired to a "Tag audio" button after an audio
    download. Tests for filename parsing, response mapping, and per-format tag
    writing (mp3/m4a/flac).
  - **Remaining:** none — single + batch (playlist) tagging are both done in the
    branch; the opt-in toggle was dropped (the cards are unobtrusive, collapsed
    by default).
  - **Format note:** cover embedding works for mp3 / m4a / flac / opus but **not
    wav** (no picture frame in the container). Candidate for **v1.3.0**.

### From the codebase audit (post-v1.3.0)

Security, the found bugs, accessibility, CI, a download-WebSocket test and a
Tauri CSP are **already done** in `feature/autotag-deezer`. What's left is
non-critical:

**Hardening / quality**

- ✅ **TypeScript `strict`** — enabled in both tsconfigs. The code already
  satisfied it (zero fallout), so the frontend is now as strictly typed as the
  backend against the JSON contract.
- ✅ **Frontend unit tests** (Vitest) — `src/lib/` (API client, download socket)
  and the filename parser; run in CI.
- ✅ **Autotag router tests** — `TestClient` tests for
  `POST /api/autotag/{identify,search,apply}` (path guard 403/404, error → 422).
- ✅ **Reproducible ffmpeg** — `fetch_ffmpeg.py` verifies the download against
  BtbN's `checksums.sha256`.
- ✅ **Type-aware ESLint** (`recommendedTypeChecked`).

**Features shipped** (fit the local / high-fidelity philosophy)

- ✅ **Cover art in history + completed card** *(in main)* — extracts the embedded
  album art (`GET /api/cover`, mutagen, path-guarded) for tagged audio; falls back
  to the kind icon. After tagging, the row refreshes and its title becomes
  "Artist - Title".
- ✅ **Re-tag from history** *(in main)* — a tag button on audio rows opens the
  auto-tagger (fixed-open modal) for any past download, not just the latest one.
- ✅ **Better auto-tag matching** *(in main)* — merge Apple Music + Deezer (so an
  original on one and a remix on the other both show), rank the cleanest match
  first (preselected), and strip YouTube-ism noise incl. yt-dlp's fullwidth
  sanitised chars (｜：？…) from the filename query.
- ✅ **Browser icons in the cookies selector** *(in main)* — monochrome logos
  (self-contained `BrowserIcon`, simple-icons paths, no runtime dep).
- ✅ **YouTube search from the URL field** *(v1.6.0)* — typing a query (not a URL)
  shows a live, debounced dropdown of results (thumbnail / channel / views /
  duration) with keyboard nav; picking one analyzes it. Backend `GET /api/search`
  runs a flat `ytsearch`; the frontend caches recent queries.
- ✅ **Trim / clip a section** *(v1.7.0)* — a scissors button in the preview
  reveals start/end inputs (`m:ss`); the backend clips via yt-dlp's
  `download_ranges` (+ `force_keyframes_at_cuts`). Works for audio and video.
- ✅ **yt-dlp version in Settings** *(v1.7.0)* — shows the bundled yt-dlp version
  and whether a newer one is published (informational; it updates with the next
  Yoink release — no in-app yt-dlp update, by design).
- ✅ **Filename template** *(in main)* — a Settings dropdown of safe presets (title
  / uploader-title / date-title / title-id) + a custom field; the backend feeds it
  to yt-dlp's `outtmpl`, sanitised against path traversal.
- ✅ **Bandwidth limit** *(in main)* — a Settings dropdown caps the download speed
  (yt-dlp `ratelimit`).
- ✅ **SponsorBlock** *(v1.5.0)* — Settings switch (off by default; reusable
  `Toggle` with the brand logo + a "?" info popover) and a remove/mark dropdown;
  wires yt-dlp's `SponsorBlock` + `ModifyChapters` postprocessors into both audio
  and video downloads (sponsor / intro / outro / selfpromo / … cats).
- ✅ **Smaller wins (done):** paste URL from clipboard · WAV-can't-hold-cover-art
  hint when auto-tagging · unified the preview checkboxes (subs / chapters /
  multi-audio) onto the `Toggle` switch.

---

## Phase 11 — Immersive (VR) video + download queue ✅ (v1.9.0)

### Immersive / VR video
- ✅ **Detection** — heuristic over the metadata (known immersive studios,
  textual markers like `180`/`360`/`SBS`/`MKX`, refined by aspect ratio). Shown
  as a badge + an opt-in toggle **only when detected**, so plain video can't be
  tagged by mistake. Works for single videos and whole playlists (batch).
- ✅ **Tagging** — a projection **name suffix** (`…_180x180_3dh`, `…_360`,
  `…_MKX200`…) that DeoVR/Heresphere/Quest read, **plus injected Spherical Video
  V2 metadata** (`st3d` + `sv3d`/`equi`) so box-reading players show it in 3D.
  Validated end-to-end with ffprobe (Stereo 3D + Spherical Mapping).
- ✅ **11 layouts** — 180/360 SBS·TB·mono, fisheye 190/200, MKX200/220, RF5.2;
  tagged in `.mp4`/`.mov`. The MP4 injector streams the file (moov-only in RAM),
  repairs `stco`/`co64`, is atomic (temp + fsync + `os.replace`), and bails
  safely on fragmented / multi-sample-entry files it can't grow.
- ✅ **Remembered per channel** — your layout correction is saved per uploader
  and seeds future downloads from the same studio.

### Download queue
- ✅ **Persistent queue across sessions** *(was backlog)* — paste many links,
  download them sequentially with per-item progress, **persist in localStorage**
  (survives restarts), and **resume** interrupted items (yt-dlp continues the
  `.part`). Opened from a header button (badged with the unfinished count),
  replacing the old always-0/1 "active downloads" pill.

### Robustness & fixes (from the codebase audit)
- ✅ **Impersonate Chrome by default** — applied to every yt-dlp request so
  anti-bot TLS fingerprinting stops blocking metadata + downloads (transparent
  where unneeded), plus a tolerant extraction fallback and concurrent HLS/DASH
  fragments.
- ✅ **Proper combobox ARIA on the search field** *(was backlog)*.
- ✅ **Hardened the thumbnail proxy** *(was backlog)* — pins the resolved IP to
  close the DNS-rebinding/TOCTOU window.
- ✅ **Settings input validation** (cookies-from-browser allowlist, proxy scheme).
- ✅ **Real audio bitrate in history** — shows the probed bitrate (e.g.
  `128 kbps`) instead of repeating the format.
- ✅ **Download-size estimate** in the preview, when known.

## Phase 10 — Next (planned)

The remaining features that fit the local / high-fidelity philosophy. No version
assigned yet; roughly in priority order.

- ⬜ **Persist all download defaults** — remember container, audio format,
  subtitles and chapters (today only kind/quality persist). *(Postponed by the
  user for now.)*
- ⬜ **Concurrent playlist downloads** (configurable N) — evaluated and deferred:
  the queue is strictly sequential (one socket / progress bar / history entry at a
  time), so parallelising means redesigning the whole progress UI — real
  regression risk for a modest gain.
- ⬜ **Smaller wins (left):** re-download / re-analyze from history · embed
  thumbnail as cover art on audio · list which playlist items failed.

## Ideas backlog (unscheduled)

A vetted pool of ideas from a project-wide review, grouped by theme. Not
committed and not release-ordered — picked from as capacity allows. Effort tags:
**S** small · **M** medium · **L** large.

### 🎬 Download & conversion

- ⬜ **Search beyond YouTube** (S/M) — a platform selector by the search field
  (YouTube / **SoundCloud** / Bilibili…), switching yt-dlp's search prefix
  (`ytsearch` → `scsearch`). The infra (`/api/search` + dropdown) already exists;
  SoundCloud pairs perfectly with the auto-tagger. Note: only the few platforms
  yt-dlp can *search* — TikTok/Instagram/X/Vimeo only download by URL, no search.
- ⬜ **Split by chapters** (M) — one file per chapter (podcasts, albums, DJ sets)
  via `--split-chapters`; `has_chapters` is already detected.
- ⬜ **Playlist sync / download-archive** (M) — keep a `--download-archive` so a
  playlist/channel only fetches what's new ("folders that update").
- ✅ **Video codec preference** *(in main)* — Settings dropdown (any/H.264/VP9/AV1)
  biasing yt-dlp's `format_sort`, degrading gracefully per resolution.
- ✅ **Audio bitrate picker** *(in main)* — Settings dropdown (best/320/256/192/128)
  for lossy formats via `FFmpegExtractAudio` `preferredquality`.
- ⬜ **Sidecar exports** (S) — optionally save `.info.json`, description,
  thumbnail `.jpg`, comments, and loose `.srt`/`.vtt` (all native to yt-dlp).
- ⬜ **Subtitles as separate files + auto-translate** (M) — extend the existing
  subtitle infra to write `.srt`/`.vtt` and pull YouTube's auto-translations.
- ⬜ **Convert/transcode local files** (M) — drop an existing file and remux /
  re-encode it with the bundled ffmpeg (no URL). Pairs with trim + split.
- ⬜ **Clip → GIF/WebP** (M) — export a trimmed range as an animated GIF/WebP
  (ffmpeg palette), on top of the trim UI.
- ⬜ **Loudness normalization** (M) — ffmpeg `loudnorm` (EBU R128) for a
  consistent-volume library.
- ⬜ **Capture frame / embed poster** (S) — save a frame at a timestamp; embed
  the thumbnail as the video poster (MKV/MP4).
- ✅ **Proxy / SOCKS** *(in main)* — a Settings field for `--proxy`
  (http/https/socks), applied to metadata + downloads.
- ⬜ **Download presets/profiles** (M) — named option bundles ("FLAC + tags",
  "1080p MP4 + ES subs") applied in one click.
- ⬜ **Library subfolders** (M) — path templates (`%(uploader)s/%(title)s`) on top
  of the filename template, carefully sanitised.

### 🎵 Audio library

- ⬜ **Lyrics in auto-tagging** (L) — fetch + embed lyrics from LRCLIB (free, no
  key), alongside cover art and tags.
- ⬜ **Media-server naming presets** (S) — Jellyfin/Plex/Navidrome layouts
  (`Artist/Album/## - Title`), reusing the auto-tagger's metadata.
- ⬜ **NFO sidecars** (M) — generate `.nfo` for Plex/Jellyfin/Kodi recognition.

### 🖥️ UX, UI & accessibility

- ✅ **Desktop notification on finish** *(in main)* — Tauri notification plugin
  fires on completed / failed / queue-summary.
- ✅ **Auto-focus the URL field on launch** *(in main)* — the field focuses on
  mount; the core action is "paste a link".
- ⬜ **Drag-and-drop a link onto the window** (M) — Tauri `onDragDropEvent` + a
  DOM `text/uri-list` fallback → analyze.
- ✅ **Global keyboard shortcuts** *(in main)* — Ctrl/Cmd+L focus URL, Ctrl/Cmd+,
  toggle Settings, Esc close.
- ✅ **Action buttons on the completed card** *(in main)* — Open file / Open
  folder + a dismiss, right on the completion card.
- ✅ **Progress accessibility** *(in main)* — `role="progressbar"` + `aria-valuenow`,
  an `aria-live` status, and `role="status"` on the completed card.
- ✅ **Proper combobox ARIA on the search field** *(v1.9.0)* — `role="combobox"`,
  `aria-expanded`, `aria-controls`, per-option `aria-selected`.
- ⬜ **First-run empty state** (S) — example URL, "type to search YouTube", link to
  supported sites.
- ✅ **Taskbar / window-title progress** *(in main)* — `Yoink — 42%` in the title +
  Tauri `setProgressBar` on the taskbar during a download.
- ✅ **Richer history rows** *(in main)* — relative time, format badge, size, and
  quality (video resolution / audio bitrate, via a persisted column + SQLite
  migration).
- ⬜ **Skip-current vs cancel-all** (M) — don't nuke the whole queue to drop one
  stuck item; surface which items failed.
- ✅ **Honor `prefers-reduced-motion`** *(in main)* — global CSS damps spinners,
  fades and transitions.
- ✅ **Contrast pass** *(in main)* — promote the smallest `zinc-500` hint text (borderline
  WCAG AA).
- ⬜ **Unify PlaylistCard checkboxes** (S) — reuse the `Toggle` switch (raw
  checkboxes still there).
- ⬜ **Responsive PreviewCard** (M) — stack the fixed thumbnail + controls on
  narrow windows.

### 🔌 OS & integrations

- ⬜ **`yoink://` deep link** (M) — the enabler for "send to Yoink" from anywhere,
  sidestepping the local-CORS lock; `single-instance` already focuses the window.
- ⬜ **System tray + close-to-tray + autostart** (S/M) — a real always-available
  download manager.
- ⬜ **Thin CLI over the local API** (S/M) — `yoink <url>` driving the same
  REST+WS backend for scripts.
- ⬜ **Browser extension "Download with Yoink"** (M) — context-menu → `yoink://`
  (avoids relaxing CORS).
- ✅ **Persistent queue across sessions** *(v1.9.0)* — paste many links; the
  queue persists (localStorage) and resumes interrupted items on launch.
- ⬜ **Subscriptions + scheduled downloads** (L) — follow a channel/playlist and
  auto-grab new items (PVR-style), with OPML import/export. Needs tray/autostart.
- ⬜ **More distribution channels** — AUR `yoink-bin` (S), Flatpak/Flathub (M),
  winget + Chocolatey (M). (License is non-commercial: AUR/Flathub/winget OK.)

### 🛠️ Engineering & robustness

- ⬜ **Backend logging/observability** (M) — *biggest gap*: no logging today.
  Structured logs to `~/.yoink/logs/`, capture yt-dlp output on failure, store the
  error in history. Unblocks debugging everything else.
- ✅ **yt-dlp retries** *(in main)* — `retries`/`fragment_retries`/`extractor_retries`
  on downloads, for transient 403/timeout failures.
- ⬜ **Resume partial downloads** (M) — `continuedl` + resume the `.part` on retry.
- ⬜ **Sidecar readiness gate + dynamic port** (M) — poll `/health` before showing
  content; fall back if 8756 is taken (currently hardcoded).
- ⬜ **ruff + mypy in CI** (S) — the project claims strict typing but neither runs;
  add them when billing restores CI.
- ⬜ **Generate TS types from OpenAPI** (M) — kill the manual `download.ts` ↔
  `media.py` contract drift.
- ⬜ **Pin yt-dlp exactly per release** (S) — reproducible builds + a record of
  which version shipped.
- ⬜ **SQLite schema versioning** (S) — `PRAGMA user_version` + idempotent
  migrations before the history schema ever changes.
- ✅ **Harden the thumbnail proxy** *(v1.9.0)* — pins the resolved IP (atomic
  resolve-validate-connect) to close the DNS-rebinding/TOCTOU window.
- ⬜ **More unit tests** (M) — the `_build_options` matrix and `_host_is_blocked`.
- ⬜ **WebSocket open timeout** (S) — fail fast if the handshake hangs on a slow
  backend boot.
- ⬜ **PyInstaller `--onedir`** (M) — faster cold start (no per-launch
  re-extraction); measure size/time trade-off.
- ✅ **Stronger filename-template sanitising** *(in main)* — confines the resolved
  path inside the download dir with `Path.resolve().relative_to()`, on top of the
  string scrub.

## Future — other platforms

Bigger, separate efforts — intentionally last. Desktop (Linux/Windows) stays the
focus; these are their own mini-projects.

### 🍎 macOS build ⬜

Package the Tauri app for macOS (the FastAPI sidecar + ffmpeg bundle should port;
needs a Mac to build / sign / notarize). Once it ships, add **Safari** back to
the cookies "browser" selector — yt-dlp can only read Safari cookies on macOS.

### 🤖 Android (experimental) ⬜

The frontend ports easily (Tauri v2 mobile loads the React UI in a WebView). The
hard part is the engine: the PyInstaller backend sidecar does **not** work on
Android (no spawnable binaries, no `externalBin`), so the local HTTP/WebSocket
server must be replaced. Three routes:

- ⬜ **Embed Python (Chaquopy) + ffmpeg-kit** — run yt-dlp in-process, driven via
  native Tauri commands instead of REST/WS to `localhost`. Keeps Python.
- ⬜ **Native yt-dlp lib (`youtubedl-android`) + ffmpeg-kit** — the Seal approach;
  leaves Python for a Kotlin/Java layer.
- ⬜ **Thin client** — APK is just the UI talking to a remote backend (the desktop
  FastAPI on a PC/NAS). Minimal work, but no longer fully "local".
- ⬜ Android toolchain + plumbing — SDK/NDK/JDK, `tauri android`, scoped-storage
  save paths, runtime permissions.

> Functionally proven on Android (cf. Seal = yt-dlp + ffmpeg in an APK).
> Distribute via direct APK / F-Droid — Google Play typically rejects YouTube
> downloaders. A separate mini-project, not an extension of desktop packaging.
