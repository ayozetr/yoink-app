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

- **Current release:** **v3.4.0** — **resilience & control**: downloads that fail for a
  **transient** reason (a network blip, a momentary 403/429/5xx, a dropped socket)
  now **auto-retry with exponential backoff** instead of going straight to the failed
  pile; a **stale-backend banner** (with a one-click **Restart**) warns when a
  self-update left an older backend running; the **login/cookies hint** now also covers
  a locked browser cookie store; and the **CLI** gains `--video-codec` / `--audio-bitrate`,
  `--list-formats`, and a **`config`** sub-command to read/edit the saved settings.
- **Previously:** **v3.3.0** — a **quality & reliability** pass: **trims no
  longer re-encode** (a forced-keyframe cut fell back to ffmpeg's low-bitrate mpeg4
  on the bundled LGPL build — pixelated; now a stream copy keeps the source
  AV1/VP9/H.264, sharp + fast), **yt-dlp bumped to 2026.08.19** (drops the blocked
  `android_vr` YouTube client that stalled downloads), MP3 tags written as **ID3v2.3**
  so **Windows** shows the embedded cover, a **responsive-layout** hardening pass
  (cover cards, toggles, Settings grids + icon-rail nav), and UX touches — **trim-input
  validation** (accepts `m.ss`, flags bad values), a **"Preparing…"** state before the
  first byte, and an **actionable login/cookies hint** on gated content.
- **Previously:** **v3.2.0** — a **command-line interface** (`scripts/yoink <url>`)
  driving the same engine in-process: single URLs, **batch input** (many URLs / a file /
  stdin, taking only the links), **playlists**, **music-service imports**, **VR**, **trim**,
  **subtitles**, **chapters**, catalogue **auto-tagging**, per-run **overrides**
  (rate limit / proxy / cookies / SponsorBlock / normalize / filename), and **shell
  completion** — see [`docs/cli.md`](cli.md). Plus UI polish for **single wrapped items**
  (an Instagram **story/post** is labelled as such, drops the batch chapters toggle, and
  saves under its container title instead of "Video by …").
- **Previously:** **v3.1.0** — the **"Send to Yoink" browser extension (beta)** is
  **live on both stores**
  ([Firefox](https://addons.mozilla.org/firefox/addon/send-to-yoink/) ·
  [Chrome](https://chromewebstore.google.com/detail/ccbngfpojjboddajeialdgppooagdhkp)),
  installable from a new **Settings ▸ Extension** tab — with a manual-install channel
  and a right-click usage tip — plus **Open-source licenses** under **Settings ▸ About**
  listing Yoink's direct dependencies and their licenses.
- **Previously:** **v3.0.0** — **desktop integration**: a **system tray** with
  close-to-tray, **launch-at-startup**, and six opt-in **global shortcuts**
  (paste-and-analyze, quick-download, cancel, open folder, …), each with its Settings
  toggle; a **`yoink://` deep link** so the browser — or anything — can hand a URL to
  the running app; a **Terms of Use & disclaimer**; a batch of **quality work**
  (memoized main-column panels, a deferred playlist lossless probe,
  cancel-a-queued-download-on-disconnect, re-tag dialog focus a11y, more tests); and an
  **audio-detection fix** for Twitter/X clips whose HLS audio track carries a null
  `acodec`.
- **Previously:** **v2.9.0** — **loudness normalization** (opt-in −14 LUFS),
  a **whole-queue progress bar** ("N of M downloaded"), a **redesigned Settings
  modal** (sidebar + content panel, a branded **About**, brand icons + **language
  flags**, "?" help on the format/subtitles/proxy fields, a read-only **Shortcuts**
  section), a **"notify on complete"** toggle, a thumbnail **`hqdefault` fallback**
  for YouTube's grey placeholder, and a smarter **auto-tag title swap** ("Song –
  Artist").
- **Previously:** **v2.8.0** — an **"Artist – Title (auto-tag)" filename
  template**: pick it in Settings and a downloaded track is renamed to its *tagged*
  name (the one already shown in history), carrying its `.nfo`/`.lrc` sidecars along
  and never clobbering an existing file. Bundles **yt-dlp 2026.07.04** (verified
  across the full URL spread — video, playlists, music imports, Threads, VR), and the
  **preview + playlist format selectors reflow** so they stay readable in a narrow
  (non-maximized) window.
- **Previously (v2.7.0):** **automatic in-app updates**: an *on-by-default*
  (togglable) launch check floats a dismissible banner + a desktop notification when
  a newer release exists, and either the banner or Settings **self-updates in place**
  behind a live-progress "Downloading…" popup (Windows installs passively — no
  click-through). The **first launch after an update shows a "What's new" popup**
  (once; re-openable from Settings) rendering that release's notes. Plus small
  hardening (the proxy setting now requires a host; one shared progress bar).
- **Previously (v2.6.0):** a **reworked download queue** — its own **format** picker,
  and a pasted **album/playlist** becomes one collapsible row whose **tracks you pick
  individually** (music routed through the importer instead of failing on DRM, each
  row labelled with its source); plus **playlist sync**, a **responsive preview card**,
  and a **Skip-current vs Stop** queue control with **live drag-reorder**.
- **Previously (v2.5.1):** **per-track playlist cover art** (each track's own album
  art, not the playlist's — Deezer lookups paced so big lists keep them, streamed
  in progressively), a **unified music-import / playlist card**, **YouTube Music
  playlists as audio-only**, and polish (undraggable covers, a persistent
  "0 selected" summary).
- **Previously (v2.5.0):** **Amazon Music cover art from Amazon**
  (playlist/album + per-track, incl. Amazon-exclusive tracks), **auto-tagging**
  via your **regional Apple Music store** with **fewer irrelevant matches**,
  **lyrics** looked up only when the Setting is on + a **title+duration** fallback
  for renamed acts, a **handier history** (re-analyze a past download,
  **drag-and-drop** a link, tidier same-height rows), **correct YouTube quality
  labels** for non-16:9 videos, and a **faster start** (one-folder backend — no
  per-launch extraction).
- **(v2.4.0):** **broader source support** (resolves videos whose
  media is served through the page's own player config), **immersive (VR) clips:
  trimming fixed** + an **audio-less source warning**, **steadier downloads**
  (auto-retry of a transient ffmpeg hiccup; cancelling mid-merge no longer wedges
  the next download), **complete Amazon playlist import**, and a **fully localized
  interface**.
- **(v2.3.1):** Windows reliability — **certifi** TLS for every
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
- **Stack:** React 19 / TS / Tailwind · FastAPI / yt-dlp · ffmpeg bundled in a
  one-folder backend (PyInstaller `--onedir`, shipped as a Tauri resource).
- **Health:** backend (pytest, 350) green · frontend build + e2e (21) + vitest (56) green · `npm audit` 0 · strict TS · Rust `cargo check`/deep-link tests green.

---

## ✅ Shipped (by area)

A condensed map of what already works.

**Core engine**
- URL analysis (`POST /api/info`) → preview with the real available formats;
  **YouTube search** from the URL field; flat **playlists**.
- **Anti-bot**: yt-dlp + `curl_cffi` browser impersonation (default) gets past most
  Cloudflare/TLS-fingerprint blocks; custom **Threads (Meta)** extractor; optional
  **YouTube PO token** (Settings) passed as the native `youtube:po_token` extractor
  arg to clear the "confirm you're not a bot" wall without cookies.
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
desktop notifications, taskbar/title progress, global shortcuts, **14-language** i18n,
**WCAG-AA** pass (contrast, reduced-motion, ARIA incl. the search combobox),
security-hardened (path guards, SSRF-safe thumbnail proxy w/ pinned DNS, settings
validation), strict TS + tests.

---

## 🎯 The v2.0.0 / v2.1.0 push — ✅ shipped

The highest value/effort work from the v1.9.0 audit — all shipped in v2.0.0/v2.1.0
(kept here as the record). *(Music import, SoundCloud search, 14 languages, logging,
resume and the release polish shipped in v2.0.0.)*

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
- ✅ **Playlist sync** — re-analyzing a playlist flags each entry already in your
  download history (matched by a context-free URL key that ignores playlist/
  tracking params) and pre-selects only the new ones; already-downloaded rows show
  a "Downloaded" badge and stay re-selectable.
- ⬜ **Sidecar exports** (S) — `.info.json` / thumbnail / loose `.srt`/`.vtt`.
- ⬜ **Subtitles as separate files + auto-translate** (M).
- ✅ **Loudness normalization** *(post-v2.8.0, in `main`)* — an optional (off by
  default) leveling of every audio download to **-14 LUFS** (EBU R128, the
  Spotify/YouTube target) via a **two-pass ffmpeg `loudnorm`** (measure → re-encode
  with the measured values, preserving the source sample rate); runs before
  auto-tagging and is best-effort, so a failure leaves the original untouched.
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
- ✅ **Auto-retry with backoff** — a failed job now re-runs itself automatically (up
  to 2 retries, exponential backoff 2s→4s, "Retrying…" on the bar) — but only for
  **transient** failures (a network blip, a momentary 403/429/5xx, a dropped socket),
  never permanent ones (private/removed/unsupported/no-format). Complements yt-dlp's
  fragment-level retries; the manual "Retry failed" stays for what still doesn't land.
- ⬜ **Non-addressable sets (Instagram story-sets / highlights)** (L) — some sources
  return a container that yt-dlp resolves into several **fully-embedded** items with
  **no per-item URL** (`InstagramStoryIE` yields items with a unique `id` but no
  `url`/`webpage_url`, so yt-dlp stamps them all with the **container's** `webpage_url`
  and an identical `title`). Three bugs cascade from that: the card selects by `url`,
  so the items **collapse to one selection** (can't check/uncheck individually);
  Download then fires **one request per item to the same container URL** (each pulls the
  whole set); and the identical title collides the output filename → most land as
  "output file is missing". Fix (needs live testing with IG cookies): (1) select by a
  **unique id**, not `url`; (2) download an item via the container URL + `playlist_items`
  (its original 1-based index) with `noplaylist` off, so yt-dlp fetches just that clip;
  (3) make the output name **unique** when items share a title (append `%(id)s` / an
  index). Same-title collision (3) is general, not IG-only. A single story is fine via
  its own `stories/<user>/<id>/` URL — only the highlight/all-stories container is affected.
- ⬜ **Bundled zero-config PO token** (M) — the opt-in `youtube:po_token` setting still
  makes the user mint a token by hand. Ship a **provider that generates one
  automatically** (a bgutil-style HTTP provider + a bundled JS runtime, or an embedded
  minter) so YouTube's bot-check is cleared out of the box with no cookies and no manual
  token. Gate it behind real-world testing before it becomes the default.

### 🎵 Audio library
- ⬜ **Recalibrate the YouTube-match duration weight** (M · needs a test set) — the
  `matching.score` fold `((nm+am)/2 + tm)/2` weights duration **50%** of the final
  score, and `time_match`'s `exp(-0.1·Δ)` decay is steep (a 10 s intro on an official
  video → tm 37 → score 68). That can misrank an exact-length lyric video above the
  official-with-intro cut. *Already fixed (v3.1.0-ish): a no-duration source no longer
  folds in the neutral `tm=100`, so Amazon-style scores aren't inflated by a flat +50 —
  and it's provably pick-neutral.* The **weight/decay** itself is the open part: lowering
  it (e.g. `0.4·nm + 0.4·am + 0.2·tm`, or duration as a tiebreaker) or softening the
  decay must be **measured against a bench of real songs** (the matcher hit ~99.5% on
  2,300+ tracks) before shipping — a naive change risks regressing that. Also note there
  is **no ISRC** to match on: keyless sources mostly don't expose it, and `ytsearch`
  results carry none, so the match is inherently fuzzy.
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
- ✅ **Responsive PreviewCard** — the single-video preview stacks the thumbnail
  (16:9, full-width) above the info/controls on narrow widths.
- ✅ **Unify PlaylistCard checkboxes** onto `Toggle` (chapters/multi-audio switches).
- ✅ **Re-download / re-analyze from history** — a re-analyze button on each
  history row reloads its URL into the analyzer.
- ✅ **Skip-current vs cancel-all** in the queue — a *Skip* button drops the
  current download and moves on; *Stop* still cancels the whole run.
- ✅ **Reorder the queue** — drag a row by its grip handle to change the order.
- ✅ **Queue: format picker + music/playlist groups** — pick video/audio + format
  for the whole queue; a pasted album/playlist resolves into one collapsible row
  whose tracks/videos you select individually (music routed through the importer:
  match on YouTube → download audio → tag), instead of failing on DRM.
- ⬜ **Auto-fill a clipboard URL on window focus** (M) — when the field is empty and
  the clipboard holds a link, pre-fill it (non-destructive) so a paste→analyze is one step.
  *(Tried in v2.3.0 but skipped: a gesture-less clipboard read is blocked by browsers.)*
- ✅ **Update experience** — an **on-by-default** "check for updates automatically"
  setting (togglable off; the app only; yt-dlp stays owner-managed) raises an in-app
  banner + a desktop notification when a newer release exists, and either (banner or
  Settings) **installs it in place** with a live-progress "Downloading…" popup. The
  **first launch after an update shows a "What's new" popup** (once, then remembered;
  re-openable from Settings) rendering that release's notes, trimmed to the part
  before a hidden `<!-- /whatsnew -->` marker (`GET /api/release-notes` + a small
  markdown renderer).
- ⬜ **Cumulative "What's new"** (M) — the popup shows only the version you landed on.
  When several releases were skipped (e.g. 3.0.0 → 3.2.0), show the notes for **every
  version in between** (3.1.0 + 3.2.0), newest first. Needs the previously-installed
  version remembered across the update, and `GET /api/release-notes` extended to return
  the notes for a version range (each release's pre-`<!-- /whatsnew -->` section,
  concatenated), instead of just the current tag.
- ✅ **Paste-and-analyze keyboard gesture** *(v2.3.0)* — `Ctrl/Cmd+Shift+V` pastes a
  link from the clipboard and analyzes it in one shot, from anywhere in the window.
- ✅ **"Copy error" button** *(v2.3.0)* — on a failed download and on history error
  rows, so the raw failure text is one click away.

### 🔌 OS & integrations
- ✅ **`yoink://` deep link** *(next)* — a `yoink://download?url=<encoded>` scheme
  (tauri-plugin-deep-link + the single-instance `deep-link` feature) lets the browser
  or anything hand a URL to the running app, sidestepping the local-CORS lock. Only
  the `url` param is read and a malformed link is ignored; a cold-start URL is drained
  by the frontend and routed through the same analyze path as drag-and-drop.
- ✅ **System tray + close-to-tray + autostart** *(next)* — an always-on manager: a
  tray (open / quit), close-to-tray, and launch-at-startup, each a Settings toggle.
- ✅ **Global hotkey (Tauri `globalShortcut`)** *(next)* — six opt-in system-wide
  shortcuts (all Ctrl/⌘+Shift+…): paste-and-analyze, quick-download, show/hide,
  paste-only, cancel, open-folder — firing with Yoink in the background, toggleable.
- ✅ **Browser extension** "Send to Yoink" — **(beta)** *(next)* — a MV3 companion
  (Firefox + Chromium) with a context-menu item + toolbar button that fire the
  `yoink://` deep link; strips YouTube's auto Radio mix so a single video isn't sent
  as a playlist. **Published on both stores** *(v3.1.0)* —
  [Firefox Add-ons](https://addons.mozilla.org/firefox/addon/send-to-yoink/) and the
  [Chrome Web Store](https://chromewebstore.google.com/detail/ccbngfpojjboddajeialdgppooagdhkp)
  — with the rolling [`ext-latest`](https://github.com/ayozetr/yoink-app/releases/tag/ext-latest)
  pre-release as the manual-install channel. Both listings link from **Settings ▸
  Extension** in the app. Still labelled **(beta)** on purpose until it has had real
  use; dropping the label is a follow-up.
- ⬜ **Configurable keyboard shortcuts** (M) — the Settings › Shortcuts section is
  read-only today (it lists the fixed bindings, now split into local + global); let
  the user **rebind** them (persisted).
- ✅ **Thin CLI** *(next)* — `scripts/yoink <url>...` drives the same engine in-process
  (no server): reuses saved settings, writes to the same history DB. Handles single URLs,
  **batch input** (several URLs, `-a`/`--batch-file`, or stdin `-` — only the links are
  taken from arbitrary text), **playlists** (`--items 1,3-5` / `--filter` /
  `--skip-existing` / `--list`) and **music-service imports** (Spotify/Deezer/Apple/
  Tidal/Amazon — matched on YouTube and tagged with the exact source metadata), plus
  **VR** (`--vr`/`--vr-layout`), **trim** (`--trim-start`/`--trim-end`), **subtitles**
  (`--subs LANG`), **chapters** (`--chapters`/`--no-chapters`), catalogue **auto-tagging**
  (`--tag`), and per-run **overrides** (`-o`, `-t`, `--rate-limit`, `--proxy`,
  `--cookies-*`, `--sponsorblock`, `--normalize`, `--video-codec`, `--audio-bitrate`).
  Also **format inspection** (`--list-formats`), a **`config`** sub-command that
  reads/edits the saved settings (`yoink config [get|set KEY [VALUE]]`),
  `--info`/`--json`/`--quiet`, `--version` and **shell completion**
  (`--print-completion bash|zsh|fish`). See [`docs/cli.md`](cli.md).
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
- ✅ **More tests** *(next)* — `_host_is_blocked` cases, queue/VR integration in the
  WS, and the frontend `estimatedSizeBytes`/`formatBytes` size helpers.
- ✅ **Render perf: memoize the main-column panels** *(next)* — `DownloaderPanel` /
  `PreviewCard` / `PlaylistCard` / `UrlInput` (+ header, music card) are now wrapped
  in `React.memo` with `useEventCallback`-stabilized props, so a progress tick no
  longer reconciles the whole column. *(Carried over from the v1.9.0 audit — the last
  real perf item.)*
- ✅ **Defer the playlist lossless probe** *(next)* — analyzing a playlist returns the
  flat listing immediately; `source_lossless`/`best_audio_abr` are computed lazily
  (only when the user picks audio) instead of a second full `extract_info` up front,
  halving playlist-analysis latency. *(Carried over from the v1.9.0 audit.)*
- ✅ **PyInstaller `--onedir`** (M) — the backend ships as a one-folder Tauri
  resource spawned by `main.rs` (std::process, stdin-pipe shutdown watchdog),
  not a onefile sidecar, so it starts without re-extracting ~180 MB each launch.
  Trade-off: bigger install (AppImage ~173→255 MB). Verified end-to-end on Linux
  (spawns, binds :8756, ffmpeg/yt-dlp work, no orphan on exit); self-update is
  unaffected (the updater swaps the whole AppImage). Windows launch to be smoke-
  tested on the VM before it ships.
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
- ✅ **Cancel a queued download blocked on the download lock when the client disconnects**
  *(next)* — a second concurrent job now races the lock acquire against the disconnect
  signal (`_acquire_or_disconnect`), so it aborts cleanly instead of hanging on a
  disconnect it never noticed.
- ✅ **Re-tag dialog initial focus with a cold lazy chunk** *(next · a11y)* — when
  `AutoTagPanel`'s lazy chunk isn't loaded yet, `useFocusTrap` re-runs the focus pass
  (via a `MutationObserver`) once the panel mounts, so the first field gets focus
  instead of the container.

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
- ⬜ **Windows on ARM — native ARM64** (L) — the x64 build already runs on
  Snapdragon Win11 via the Prism emulator (fine for download + stream-copy mux,
  slower only for re-encode), so nobody's blocked. A native
  `aarch64-pc-windows-msvc` build is feasible — Tauri + WebView2 are ready, ffmpeg
  ships `winarm64` (BtbN), pydantic-core has ARM64 wheels — but gated on: an ARM64
  Windows build machine (**PyInstaller can't cross-compile**) and, the key unknown,
  a **`curl_cffi`** ARM64 wheel (the anti-bot impersonation dep). Also needs a
  `windows-aarch64` entry + signed builds in `latest.json`.

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
- **Local media conversion / editing** — dropping a local file to transcode/remux,
  clip to GIF/WebP, or grab a frame is **out of scope.** Yoink *downloads*
  audio/video; it isn't a converter, editor or frame grabber — those act on files
  you already have, which is a different tool.
