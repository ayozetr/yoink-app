# Architecture

Yoink is **two native Rust layers**: an egui desktop app talking to a local
engine (`yoink-core`) that drives yt-dlp and ffmpeg. The app spawns and
supervises the backend on startup, so it's a single self-contained program.

```
┌────────────────────────┐         REST: POST /api/info          ┌──────────────────────────┐
│     Desktop app        │ ───────────────────────────────────▶ │        Backend            │
│   Rust + egui/eframe    │                                       │   yoink-core (Rust/axum)  │
│                        │ ◀─────────────────────────────────── │        (:8756)            │
│                        │     clean JSON (title, formats…)      │                           │
│  - URL input           │                                       │  - yt-dlp wrapper         │
│  - Preview card        │       WS: live download progress      │  - ffmpeg merge           │
│  - Progress bar        │ ◀╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ │  - filesystem (std::path) │
│  - History tab         │       (percent, speed, ETA)           │   (spawned by the app)    │
└────────────────────────┘                                       └──────────────────────────┘
                                                                  (dashed = WS download stream)
```

## Why two layers

- A GUI can't cleanly run yt-dlp or write to arbitrary local folders. A small
  local backend owns the system-level work (process spawning, filesystem,
  ffmpeg) and exposes a clean API, which the desktop app consumes as a client.
- Keeping the engine behind an HTTP/WS API also powers the `yoink` CLI, which
  drives the same `yoink-core` without any UI.

## Communication contract

### 1. Metadata — REST (implemented)

When the user pastes a URL and clicks **Analyze**:

1. Frontend → `POST /api/info` with `{ "url": "..." }`.
2. Backend runs yt-dlp with `download=False` and normalizes the result.
3. Backend → clean JSON: `title`, `duration`, `duration_string`,
   `thumbnail_url`, a list of `formats`, plus capability hints
   `source_lossless`, `best_audio_abr`, `has_audio`, `subtitle_langs`,
   `auto_caption_langs`, `has_chapters`, `audio_langs` (multi-audio), and an
   `is_vr`/`vr_layout` immersive-video heuristic.
4. Frontend populates the preview card and the format/quality selectors.

Typing a query instead of a URL hits `GET /api/search?q=&source=youtube|soundcloud`
(a flat yt-dlp `ytsearch`/`scsearch` — a header toggle picks the platform); the
field shows a live dropdown of matching tracks and picking one analyzes it
through the same `POST /api/info` flow.

Pasting a **music-service** URL (Spotify/Deezer/Apple/Tidal/Amazon) instead hits
`POST /api/music/resolve`, which keyless­ly returns a `MusicImportInfo` tracklist;
the import card then calls `POST /api/music/match` per track (a spotDL-ported
YouTube ranking) and downloads + auto-tags each via the normal flow. See
[`music-import.md`](music-import.md).

For a playlist, the backend additionally resolves the **first entry** to set
`source_lossless` / `best_audio_abr` on the listing, so the playlist UI gates
FLAC/WAV like a single video (assuming a homogeneous playlist). It also **syncs
against the download history**: each entry already downloaded is flagged
`already_downloaded` (matched by a context-free URL key — normalized, minus
playlist/position/tracking params), so the playlist card pre-selects only the new
ones and badges the rest as "Downloaded".

The JSON shape is defined once by the Rust structs in `backend-rs/src/` (serde)
and consumed by the desktop app (`desktop/src/api.rs`).

### 2. Download & progress — WebSockets (implemented)

When the user clicks **Download**:

1. Frontend opens `WS /api/ws/download` and sends a `DownloadRequest`: `kind`
   and `quality`, the output `container` (mp4/mov/mkv) or `audio_format`
   (mp3/m4a/flac/wav), the `embed_subs` / `subtitle_lang` / `embed_chapters` /
   `audio_multistreams` options, an optional `trim_start`/`trim_end` range (an
   inverted range is rejected up front), and `is_vr`/`vr_layout` to tag the
   output as immersive (projection name suffix + Spherical Video V2 metadata, via
   `vr.rs`) — or `auto_vr` to detect + tag VR with no preview step (used
   by the queue). An optional `estimated_size` scales the pre-flight free-disk
   check.
2. Backend runs the yt-dlp job off the async executor (a tokio worker).
3. yt-dlp `progress_hooks` emit percent / speed / ETA.
4. Those events stream back over the same socket as typed events.
5. The frontend animates the progress bar from real events until a terminal
   `completed` / `error` event.
6. ffmpeg merges separate video/audio streams (and extracts/embeds audio,
   subtitles, and chapters) as needed.

When the **normalize audio** setting is on (off by default), an audio download is
loudness-normalized to **-14 LUFS** (EBU R128) with a two-pass ffmpeg `loudnorm`
(`audio_normalize.rs`) before it's finalized and offered for
auto-tagging — best-effort, so a failure leaves the original file untouched.

Downloads run **one at a time** (concurrent downloads are a non-goal): the three
engines (main panel, queue, music import) share an in-memory lock (in
`desktop/src/app.rs`) so two jobs can't write the same `.part` in the shared
download folder. The desktop app spawns the backend on launch (port 8756) via
`desktop/src/backend_proc.rs`.

### 3. Audio auto-tagging — REST (implemented)

After an audio download (single or playlist), the UI offers to tag the file(s)
from the user-selected catalogue — Apple Music (iTunes Search API), Deezer or
MusicBrainz (with cover art from the Cover Art Archive),
both free, key-less and over plain HTTPS via `reqwest` (`autotag_source` in
Settings). The flow is **identify/search → user picks a version and edits →
apply**; nothing is written to the file until **Apply**.

1. `POST /api/autotag/identify` — `{ "path" }`. The backend parses the
   filename's `Artist - Title` and looks it up, returning a `CandidateList` of
   matching releases (single/EP/album, each with cover art).
2. `POST /api/autotag/search` — `{ "artist", "title" }`. Manual catalogue
   search, returning the same `CandidateList`.
3. `POST /api/autotag/lyrics` — `{ "title", "artist", … }`. When the **lyrics**
   setting is on, the card previews the LRCLIB match (in `autotag.rs`:
   exact `/get` → structured search → fuzzy `q` → primary-artist retry) so it can
   show a found/synced/instrumental indicator + a "view lyrics" popup.
4. `POST /api/autotag/apply` — the (possibly user-edited) `TagCandidate` fields
   + `path` (+ a per-track `embed_lyrics` override). The backend writes tags and
   cover art with `lofty` (full tags for mp3/m4a/flac; text-only for
   opus/ogg/wav), embeds the lyrics (and an optional synced `.lrc` sidecar),
   rewrites the `.nfo` from the tagged metadata (`nfo.rs`), and returns
   an `ApplyResponse`.

All file paths are confined to the download directory (path guard). The autotag JSON is defined in `backend-rs/src/autotag.rs`.

### 4. Update check & release notes — implemented

On launch — when the **check-for-updates** setting is on (`AppSettings.check_updates`,
the default; togglable off, the *app only* — yt-dlp stays owner-managed) — the app
reads the release's `latest.json` and compares its version against the running one.
A newer one raises a dismissible banner + a desktop notification. Installing
**self-updates in place** behind a "Downloading…" progress bar: on Linux the new
AppImage (its real path is `$APPIMAGE`) replaces the running one. The download is
**verified against an embedded minisign public key** before it's made executable
and swapped in (fail-closed), and the host/scheme are pinned to GitHub —
`desktop/src/api.rs`. The same signature also lets the legacy Tauri app install the
egui build for the one-time migration.

The **first launch after an update** shows a one-time **"What's new"** popup that
renders `GET /api/release-notes` — the release `body`, trimmed to the part before a
hidden `<!-- /whatsnew -->` marker — with a small built-in Markdown renderer
(`render_markdown` in `desktop/src/app.rs`). The last-seen version is remembered in
`<config>/yoink/`.

### 5. Deep link & browser extension — desktop (implemented)

Besides pasting or dropping a URL, the running app can be fed one from outside via a
`yoink://download?url=<encoded>` deep link. `desktop/src/deeplink.rs` registers the
scheme (via the AppImage's `.desktop` entry) and a per-user single-instance Unix
socket, so a second launch forwards its URL to the live instance (and a cold-start
URL from `argv`) instead of starting a new one. The URL is parsed (http(s) only),
the window is focused, and it's analyzed through the same path as drag-and-drop.

The **"Send to Yoink" browser extension (beta)** (`extension/`, Firefox + Chromium)
is just a thin trigger: a context-menu item / toolbar button that fires that deep
link for the current page (stripping YouTube's auto Radio mix so a single video isn't
sent as a playlist). It needs no host access or network — the download stays entirely
in the local app. It ships as a beta release asset, not on the stores yet.

## Cross-platform notes

- Save paths use `std::path` so they work natively on Linux and Windows.
- The default download directory is `~/Downloads/Yoink`, overridable via
  `YOINK_DOWNLOAD_DIR`.
- ffmpeg is bundled (`YOINK_FFMPEG`); for a source run it falls back to `PATH`.
