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

- **Current release:** **v2.4.0** — **broader source support** (resolves videos
  whose media is served through the page's own player config), **immersive (VR)
  clips: trimming fixed** + an **audio-less source warning** shown before the
  download, **steadier downloads** (auto-retry of a transient ffmpeg hiccup;
  cancelling mid-merge no longer wedges the next download), **complete Amazon
  playlist import** (per-track cover art + duration), and a **fully localized
  interface** (pluralized counts + per-locale durations across the 14 languages).
- **Previously (v2.3.1):** Windows reliability — **certifi** TLS for every
  non-yt-dlp HTTPS call (cover art / music import / lyrics), a sturdier **cookie
  fallback**, and **playlist de-duplication**.
- **(v2.3.0):** **lyrics in auto-tagging** (LRCLIB plain + an optional synced
  **`.lrc`**), a **cookies browser→file fallback**, the **`.nfo` rewritten from
  the tagged metadata**, a **localized default download dir**, **music-import
  parity** (filter / range / duration summary) + history-as-it-downloads, and
  quick wins (copy-error, paste-and-analyze, low-disk-space guard).
- **(v2.2.0):** **resumable playlist downloads**, playlist filter / shift-click
  range / lazy thumbnails / retry-failed, VR follow-ups, **friendlier yt-dlp
  error messages**, **download presets**, and optional **`.nfo` sidecars**.
- **Earlier (v2.1.0 / v2.0.0):** a **single-download lock**, a **dynamic backend
  port**, the **Advanced options** panel, SSRF-hardened keyless **music import
  from five services**, SoundCloud search, **14 UI languages**. (v1.9.x:
  immersive VR, the queue, hardening.)
- **Platforms:** Linux (AppImage · deb · rpm) + Windows (msi · NSIS), self-updating.
- **Stack:** React 19 / TS / Tailwind · FastAPI / yt-dlp · ffmpeg bundled as a sidecar.
- **Health:** backend (pytest, 314) green · frontend build + e2e green · `npm audit` 0 · strict TS.

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

## 🎯 Next up — toward v2.1.0

The highest value/effort work, in order. Most surfaced from the v1.9.0 audit.
*(Music import, SoundCloud search, 14 languages, logging, resume and the
release polish shipped in v2.0.0.)*

1. ✅ **Backend logging & observability** (M · **high**) *(v2.0.0)* — a
   structured `app`-namespace logger writes to a rotating `~/.yoink/logs/yoink.log`
   + console; extraction/download failures log the real yt-dlp text, the error
   string is persisted on the history row (new `error_message` column) and shown
   under failed items in the sidebar. *(Still open: surfacing live logs in-app.)*
2. ✅ **Sidecar readiness gate + dynamic port** (M · **high**) *(v2.1.0)* — the
   desktop shell now picks the backend port at launch (**8756** when free, else an
   OS-assigned free port), hands it to the sidecar via `YOINK_PORT`, and exposes it
   to the frontend (`backend_port` command) so a busy 8756 no longer breaks
   startup. The splash already gates the UI until the backend answers (settings
   retry), so a busy-port cold start is now handled end-to-end.
3. ✅ **First-run empty state** (S · medium) *(v2.0.0)* — the main column shows a
   download icon + "ready to download" hint until a URL is analyzed.
4. ✅ **Resume partial downloads** (M · medium) *(v2.0.0)* — yt-dlp
   `continuedl` is on, so a retry of an interrupted download continues the `.part`
   instead of restarting (both the in-panel batch and the persistent queue).
   *(Cross-restart playlist resume — routing batches through the persistent queue
   — is the separate Playlists item below.)*
5. ✅ **Persist the remaining download defaults** (S · medium) *(v2.1.0)* — container
   + audio format persisted in v1.9.1; subtitles + chapters now persist too
   (`default_embed_subs` / `default_embed_chapters`), seeding the preview's
   subtitle picker and chapter toggle.

---

## 🧰 Backlog (vetted, by theme)

Not committed and not release-ordered — picked from as capacity allows.

### 🎬 Download & conversion
- ✅ **Import from music services** *(v2.0.0)* —
  paste a track/album/playlist URL from **Spotify, Deezer, Apple Music, Tidal or
  Amazon Music** → resolve it **keyless** (public APIs / embed scrapes, like the
  Threads extractor) → rank a YouTube match with a **spotDL-ported** scorer →
  download + auto-tag with the *exact* source metadata. One source-agnostic
  pipeline (`/api/music/{resolve,match}` + `MusicImportCard`); only the resolver
  differs per service. A single track shows a square-cover preview;
  albums/playlists a track-picker. The spotDL-ported matcher hits **~99.5%** of
  tracks on **2,300+ real songs** across all five sources (token-set title ratio,
  glyph folding, name+artist-aware duration gate, primary-artist + branded-channel
  matching, and a top-5→top-10 second-chance search on a miss). Resolution also
  handles **Deezer share/short links** and **single-track** URLs on every source,
  and download→tag→cover was validated **end-to-end on all five** (Amazon-playlist
  covers, which the embed omits, are backfilled from Deezer at tag time).
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
- ✅ **Search beyond YouTube** *(v2.0.0)* — a
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
- ✅ **Download presets/profiles** *(next)* — save the preview's format selection
  as a named preset (`lib/presets`, localStorage) and apply it in one click; chips
  to apply/delete and an inline "save current" in the preview card.
- ⬜ **Library subfolders** (M) — path templates (`%(uploader)s/%(title)s`).

### 📋 Playlists
*Surfaced testing real YouTube Music "Hits" mixes (`RD…`) and curated `PL` lists —
extraction is solid (49–144 tracks, both URL forms, capped at 200 with a
`truncated` flag); these are curation/scale/persistence gaps.*
- ✅ **Persistent playlist downloads** *(next)* — the in-panel batch
  (`DownloaderPanel` `startQueue`/`runJob`) now persists to `localStorage`
  (`lib/batchStore`: jobs + a done count), so a close / refresh / crash no longer
  loses a multi-item playlist. On the next launch a banner offers to resume the
  pending items through the same flow (keeping the rich preview + batch
  auto-tagging that routing into the queue would have lost).
- ✅ **Filter/search within the entry list** *(next)* — a "filter tracks…" input
  (shown for lists > 8) narrows the entries; selection persists across it and
  select-all acts on the filtered view.
- ✅ **Range + smarter selection** *(next)* — Shift+click a row to extend/clear the
  selection range from the last click (rows are keyboard-operable too).
- ✅ **Batch totals** *(v2.0.0)* — the playlist card
  shows the current selection's count + **total duration** ("23 selected · 1h 18m").
  A rough **size** estimate is still pending (flat entries carry no per-item
  formats, so it needs a probe/heuristic).
- ✅ **Audio-first for music playlists** *(v2.0.0)* — YT Music mixes (`RD…`)
  and album lists (`OLAK…`) are music-intent, so the playlist card now defaults
  `kind` to **audio** for them (detected from the playlist id) instead of video.
- ✅ **Lazy-load the entry thumbnails** *(next)* — `Thumbnail` gained a `loading`
  prop and the playlist list uses `loading="lazy"`, so a 200-item playlist no
  longer fires ~200 proxy requests at once on render.
- ✅ **Per-item retry in the batch summary** *(next)* — the panel keeps the jobs
  that failed (results are in job order) and the summary offers "Retry failed (N)".

### 🎵 Audio library
- ✅ **Auto-tag title parsing for non-Western formats** *(next)* — on top of the
  noise stripper (~93% of titles), the no-dash path now reads two more shapes:
  K-pop `ARTIST 'TITLE'` / `ARTIST "TITLE"` (quoted run = title, preceded text =
  artist; a possessive apostrophe isn't mistaken for a quote) and Bollywood
  `Title | Movie | Cast | …` (≥3 pipe segments → take the leading song). The
  manual edit/search in the tag card still covers the rest; fingerprint-based
  identify remains a possible future upgrade.
- ✅ **Embed source thumbnail as cover** on audio *(next)* — a *fallback* cover
  (yt-dlp `EmbedThumbnail` for mp3/m4a/flac); auto-tagging overrides it with real
  album art when found and preserves an existing cover when it has none.
- ✅ **Lyrics in auto-tagging** *(next)* — LRCLIB (free, keyless): embeds the plain
  lyrics (USLT / ©lyr / LYRICS), an optional synced **`.lrc` sidecar**, and an
  in-card **indicator + preview + per-track toggle**, with a fuzzy free-text
  fallback so multi-artist / accented titles still match.
- ⬜ **Media-server naming presets** (S) — Jellyfin/Plex/Navidrome layouts.
- ✅ **NFO sidecars** *(next)* — an optional Settings toggle writes a Kodi/Jellyfin
  `.nfo` (`<movie>`/`<musicvideo>`) next to each download with the source metadata;
  audio auto-tagging **rewrites** it from the tagged title/artist/album/cover.
- ⬜ **Folder-level music `.nfo` (`album.nfo` / `artist.nfo`)** (M) — the audio
  `.nfo` we write today is a *per-track* Kodi-style `<musicvideo>` file, but
  Jellyfin (and Kodi) read a **song's** metadata from its **embedded tags**, not a
  per-track `.nfo`. For music, `.nfo` only exists at the **album** (`album.nfo`)
  and **artist** (`artist.nfo`) *folder* level — so the per-track audio `.nfo` is
  effectively **ignored** by a Jellyfin music library (the embedded tags, which we
  already write, do the work). To make a sidecar actually useful for music,
  generate `album.nfo`/`artist.nfo` in the correct folders per the Jellyfin/Kodi
  music convention — which first needs downloads organised into `Artist/Album/`
  folders (a library-layout feature, hence the M). Until then the per-track `.nfo`
  stays, since Kodi music-video libraries and other tools still read it.

### 🖥️ UX / UI
- ✅ **Drag-and-drop a link** onto the window — dropping a link anywhere analyzes
  it (drops onto editable fields are left alone); `dragDropEnabled: false` lets
  the webview deliver DOM drops in the packaged app.
- ⬜ **Responsive PreviewCard** (M) — stack the fixed thumbnail + controls on narrow widths.
- ⬜ **Unify PlaylistCard checkboxes** onto `Toggle` (S).
- ✅ **Re-download / re-analyze from history** — a re-analyze button on each
  history row reloads its URL into the analyzer.
- ⬜ **Skip-current vs cancel-all** in the queue (M).
- ⬜ **Reorder the queue** (drag up/down) (M).
- ⬜ **Auto-fill a clipboard URL on window focus** (M) — when the field is empty and
  the clipboard holds a link, pre-fill it (non-destructive) so a paste→analyze is one step.
  *(Tried in v2.3.0 but skipped: a gesture-less clipboard read is blocked by browsers.)*
- ✅ **Paste-and-analyze keyboard gesture** *(v2.3.0)* — `Ctrl/Cmd+Shift+V` pastes a
  link from the clipboard and analyzes it in one shot, from anywhere in the window.
- ✅ **"Copy error" button** *(v2.3.0)* — on a failed download and on history error
  rows, so the raw failure text is one click away.

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

- ✅ **WebSocket open timeout** *(next)* — the download socket fails fast (15s)
  with a clear error if the handshake never opens, instead of hanging on 0%.
- ✅ **SQLite schema versioning** *(next)* — `PRAGMA user_version` + an ordered,
  idempotent migration list; legacy (v0) DBs migrate cleanly on startup.
- ✅ **Kill `download.ts` ↔ `media.py` drift** *(next)* — a contract test asserts
  the hand-written TS types mirror the Pydantic models 1:1 (enforced in pytest),
  plus `scripts/gen_api_types.py` to generate the literal OpenAPI types on demand
  (via npx — `openapi-typescript` still peers on TS 5.x, the app is on TS 6.x).
- ✅ **Pin yt-dlp exactly per release** — already pinned
  (`yt-dlp[default,curl-cffi]==2026.06.09` in `requirements.txt`).
- ⬜ **ruff + mypy in CI** (S) — currently only `pytest` runs (CI itself paused on billing).
- ⬜ **More tests** (S) — `_host_is_blocked`, queue/VR integration in the WS,
  frontend `estimatedSizeBytes`/`formatBytes`.
- ⬜ **PyInstaller `--onedir`** (M) — faster cold start (no per-launch re-extraction).
- ✅ **Slow `.rpm` bundling at release time** (M · build) — Tauri 2.11's rpm
  bundler took ~10–12 min to package the ~170 MB PyInstaller sidecar, while the
  `.deb`/AppImage of the same payload bundle in seconds. **Root-caused** (measured
  on the real sidecar): *not* compression — the binary is incompressible, so even
  `xz -9` is ~45 s, and SHA256/cpio are <1 s — the cost is inside the `rpm` Rust
  crate itself. **Fixed** by building only deb+appimage with Tauri
  (`--bundles deb,appimage`) and repackaging the deb → rpm with
  `scripts/build_rpm.py` (`rpmbuild` under `fakeroot`; its autoreq re-derives the
  same soname `Requires` from the ELF binaries). **~40 s** instead of minutes,
  verified installing cleanly in a Fedora container; the rpm plays no part in
  self-update, so it can't affect existing users. See
  [`releasing.md`](releasing.md) §3/§3b.
- ✅ **Friendlier download/extraction error messages** *(next)* —
  `friendly_download_error()` strips the `ERROR:`/`[extractor]`/"report this issue"
  noise and maps the common cases (bot-check/403/429 → cookies hint, private/
  members-only, unavailable, geo-block, unsupported URL, bad format) before the
  message reaches the WS / history (the full text is still logged).
- ✅ **Pre-flight free-disk-space check** *(v2.3.0)* — `shutil.disk_usage` before a
  download starts; fails early with a clear message (under ~500 MB free) instead of
  mid-write.
- ✅ **Route music-import fetches through `safe_http`** *(v2.1.0)* — `_get`/`_get_json`/
  `_final_url` now use `core/safe_http` (`fetch_public` + the pinned `OPENER`): the
  resolved public IP is pinned and every redirect hop re-validated, on top of the
  host-anchored URL detection.
- ⬜ **Cancel a queued download blocked on the download lock when the client disconnects**
  (S) — a second concurrent job (e.g. a second web tab) currently awaits the process-wide
  lock without noticing a disconnect; race the acquire against the cancel signal.
- ⬜ **Re-tag dialog initial focus with a cold lazy chunk** (S · a11y) — when
  `AutoTagPanel`'s lazy chunk isn't loaded yet, `useFocusTrap` focuses the container
  instead of the first field; re-run the focus pass once the panel mounts.

## 🥽 VR follow-ups

- ✅ **Spherical Video V1** (uuid XML) *(next)* — injected into the video trak for
  360° equirect layouts (alongside the V2 boxes), for older players + YouTube
  re-upload. Scoped to 360° because V1 predates 180° VR and would mislabel it.
- ✅ **MKV `StereoMode` tag** *(next)* — set via a stream-copy ffmpeg remux
  (left_right / top_bottom); MKV has no Spherical V2 boxes.
- ✅ **Post-tag ffprobe validation** *(next)* — after tagging an MP4, confirm
  ffprobe reads the spherical / stereo-3D side data; log a warning if not.
- 🚫 **Fisheye/EAC projection box** — *not feasible as a projection box.* Spherical
  V2 has no fisheye projection type (only equirect / cubemap / mesh); the fisheye
  layouts are signalled by the filename suffix players already parse. Emitting an
  equirect box for a fisheye file would distort it, so it stays suffix + `st3d`.
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

- **Concurrent downloads** — the queue is **sequential by design**, and a
  process-wide **single-download lock** (frontend + an `asyncio.Lock` backstop)
  now enforces it across every engine (panel / queue / music import) so two jobs
  can't collide on the same `.part`. Parallelising means redesigning the whole
  progress/history UI for a modest gain and real regression risk; revisit only with
  a dedicated multi-progress UI.
- **In-app yt-dlp update** — **not happening, by design.** Yoink only *reports* the
  bundled yt-dlp version; it's updated with the next Yoink release (owner's decision).
