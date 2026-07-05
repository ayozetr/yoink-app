# Architecture

Yoink is a **local microservice**: a reactive web UI talking to a local Python
engine that wraps yt-dlp.

```
┌────────────────────────┐         REST: POST /api/info          ┌──────────────────────────┐
│      Frontend          │ ───────────────────────────────────▶ │        Backend            │
│  React + TS + Tailwind │                                       │     FastAPI (Python)      │
│      (Vite, :5173)     │ ◀─────────────────────────────────── │        (:8000)            │
│                        │     clean JSON (title, formats…)      │                           │
│  - URL input           │                                       │  - yt-dlp wrapper         │
│  - Preview card        │       WS: live download progress      │  - ffmpeg merge           │
│  - Progress bar        │ ◀╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ │  - filesystem (pathlib)   │
│  - History sidebar     │       (percent, speed, ETA)           │                           │
└────────────────────────┘                                       └──────────────────────────┘
                                                                  (dashed = WS download stream)
```

## Why two layers

- The browser cannot run yt-dlp or write to arbitrary local folders. A small
  local backend owns the system-level work (process spawning, filesystem,
  ffmpeg) and exposes a clean API.
- The frontend stays a pure view/interaction layer, easy to iterate on.

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

The JSON shape is defined once in `backend/app/models/media.py` (Pydantic) and
mirrored in `src/types/download.ts` (TypeScript).

### 2. Download & progress — WebSockets (implemented)

When the user clicks **Download**:

1. Frontend opens `WS /api/ws/download` and sends a `DownloadRequest`: `kind`
   and `quality`, the output `container` (mp4/mov/mkv) or `audio_format`
   (mp3/m4a/flac/wav), the `embed_subs` / `subtitle_lang` / `embed_chapters` /
   `audio_multistreams` options, an optional `trim_start`/`trim_end` range (an
   inverted range is rejected up front), and `is_vr`/`vr_layout` to tag the
   output as immersive (projection name suffix + Spherical Video V2 metadata, via
   `services/vr.py`) — or `auto_vr` to detect + tag VR with no preview step (used
   by the queue). An optional `estimated_size` scales the pre-flight free-disk
   check.
2. Backend runs the yt-dlp job off-thread (`asyncio.to_thread`).
3. yt-dlp `progress_hooks` emit percent / speed / ETA.
4. Those events stream back over the same socket as typed events.
5. The frontend animates the progress bar from real events until a terminal
   `completed` / `error` event.
6. ffmpeg merges separate video/audio streams (and extracts/embeds audio,
   subtitles, and chapters) as needed.

When the **normalize audio** setting is on (off by default), an audio download is
loudness-normalized to **-14 LUFS** (EBU R128) with a two-pass ffmpeg `loudnorm`
(`services/audio_normalize.py`) before it's finalized and offered for
auto-tagging — best-effort, so a failure leaves the original file untouched.

Downloads run **one at a time** (concurrent downloads are a non-goal): the three
frontend engines (main panel, queue, music import) share an in-memory lock
(`src/lib/downloadLock.ts`) and the backend serializes jobs with a process-wide
`asyncio.Lock`, so two jobs can't write the same `.part` in the shared download
folder. In the desktop app the backend port is chosen at launch (8756, or an
OS-assigned free port when it's taken) and handed to the frontend via the
`backend_port` command.

### 3. Audio auto-tagging — REST (implemented)

After an audio download (single or playlist), the UI offers to tag the file(s)
from the user-selected catalogue — Apple Music (iTunes Search API), Deezer or
MusicBrainz (with cover art from the Cover Art Archive),
both free, key-less and over plain HTTPS via stdlib `urllib` (`autotag_source` in
Settings). The flow is **identify/search → user picks a version and edits →
apply**; nothing is written to the file until **Apply**.

1. `POST /api/autotag/identify` — `{ "path" }`. The backend parses the
   filename's `Artist - Title` and looks it up, returning a `CandidateList` of
   matching releases (single/EP/album, each with cover art).
2. `POST /api/autotag/search` — `{ "artist", "title" }`. Manual catalogue
   search, returning the same `CandidateList`.
3. `POST /api/autotag/lyrics` — `{ "title", "artist", … }`. When the **lyrics**
   setting is on, the card previews the LRCLIB match (`services/lyrics.py`:
   exact `/get` → structured search → fuzzy `q` → primary-artist retry) so it can
   show a found/synced/instrumental indicator + a "view lyrics" popup.
4. `POST /api/autotag/apply` — the (possibly user-edited) `TagCandidate` fields
   + `path` (+ a per-track `embed_lyrics` override). The backend writes tags and
   cover art with `mutagen` (full tags for mp3/m4a/flac; text-only for
   opus/ogg/wav), embeds the lyrics (and an optional synced `.lrc` sidecar),
   rewrites the `.nfo` from the tagged metadata (`services/nfo.py`), and returns
   an `ApplyResponse`.

All file paths are confined to the download directory (path guard). Models live
in `backend/app/models/autotag.py`, mirrored in `src/types/autotag.ts`.

### 4. Update check & release notes — REST (implemented)

On launch — when the **check-for-updates** setting is on (`AppSettings.check_updates`,
the default; togglable off, the *app only* — yt-dlp stays owner-managed) — the
frontend calls `GET /api/version`, which compares the running version against the
latest GitHub release. A newer one raises a dismissible bottom banner + a desktop
notification. Installing (from the banner or Settings) **self-updates in place**
via the Tauri updater behind a "Downloading…" progress popup (Windows always;
Linux only as an AppImage — `.deb`/`.rpm` fall back to the release page).

The **first launch after an update** shows a one-time **"What's new"** popup
(remembered in localStorage, re-openable from Settings) that renders
`GET /api/release-notes` — the current version's GitHub release `body`, trimmed to
the part before a hidden `<!-- /whatsnew -->` marker (model `ReleaseNotes`) — with
a tiny built-in Markdown renderer (`components/ui/Markdown.tsx`).
`GET /api/ytdlp-version` reports the bundled yt-dlp version but is informational
only (no in-app yt-dlp update).

## Cross-platform notes

- Save paths use `pathlib` so they work natively on Linux and Windows.
- The default download directory is `~/Downloads/Yoink`, overridable via
  `YOINK_DOWNLOAD_DIR`.
- ffmpeg must be on the `PATH` for high-quality merges.
