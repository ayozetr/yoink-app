# Music import — design notes (the spotDL approach)

> **Status: implemented** (→ v2.0.0, unreleased on `main`). Generalized beyond
> Spotify to **Spotify / Deezer / Apple Music / Tidal / Amazon Music** behind one
> keyless pipeline. The code lives in `backend/app/services/music_import.py`
> (resolvers) + `matching.py` (the YouTube ranking) + `routers/music.py`, with the
> `MusicImportCard` on the frontend. This document is the original design rationale.

Originally the **"Import from Spotify"** backlog item in
[`ROADMAP.md`](ROADMAP.md). It captures how [spotDL](https://github.com/spotDL/spotify-downloader)
solves this and what that means for Yoink.

## The core idea (why this is even possible)

You **cannot** download audio from Spotify — it is DRM-protected paid streaming.
spotDL's insight (and the only viable approach) is to **never touch Spotify's
audio**:

1. Read a Spotify URL's **metadata** (title, artist, album, cover, track #, year).
2. **Find the matching track on YouTube** and download *that*.
3. **Embed the Spotify metadata** (+ cover, + optional lyrics) into the file.

Spotify supplies the *"what"*; YouTube + yt-dlp supply the *"audio"*.

**Yoink already owns 2 of the 3 pieces:** the yt-dlp downloader, bundled ffmpeg,
and a multi-source auto-tagger (Apple Music / Deezer / MusicBrainz). The only
genuinely missing piece is the **Spotify tracklist**.

## spotDL v4 — the facts that matter for us

| Aspect | Detail |
| --- | --- |
| Install / license | `pip install spotdl` · MIT · needs **FFmpeg** (Yoink already bundles it) |
| Spotify credentials | **Ships a default, shared client id/secret** (`f8a606e5…`) → works with zero setup; overridable via `--client-id/--client-secret` or `--user-auth` |
| Operations | `download` (default), `save`, `sync`, `meta`, `url`, `web` |
| Audio formats | mp3 (default), m4a, opus, flac, ogg, wav |
| Bitrate ceiling | **128 kbps** (256 kbps m4a only with a YT Music Premium login) — the same ceiling Yoink already hits on YouTube |
| Lyrics providers | Genius, Musixmatch, AZLyrics, Synced (`--generate-lrc`) |
| Output template | `{title}`, `{artists}`, `{album}`, `{track-number}`, `{year}`, … |
| Programmatic API | `from spotdl import Spotdl` → `Spotdl(client_id, client_secret)` → `.search([urls])` → `songs` → `.download_songs(songs)` |

## The credentials question (this is the crux for Yoink)

Yoink's standing rule is **no API keys in the repo** — the auto-tagger uses only
keyless catalogues (iTunes / Deezer / MusicBrainz). Spotify's official Web API
needs credentials, so there are two honest stances:

- **Lean on spotDL's default credentials.** They are *public and shared across
  every spotDL user*, so Yoink would not ship *its own* secret — but it would
  depend on a shared key that is rate-limited and could be revoked upstream.
  Pragmatic, zero user setup, but fragile and not really "ours".
- **Stay truly keyless.** Scrape the **public Spotify embed page**
  (`open.spotify.com/embed/<type>/<id>`) — its inline JSON carries the full
  tracklist (title / artist / album / cover / duration) with **no credentials at
  all**. This is the same pattern as our custom Threads extractor; more fragile
  to a Spotify page change, but it keeps the "no keys" promise. *(Verified: the
  embed page exposes title/artist/cover unauthenticated.)*

## Two ways to integrate it

**The distinction:** Option A borrows spotDL's *approach* but **does not depend
on spotDL** (we implement the keyless metadata step ourselves and reuse Yoink's
pipeline). Option B pulls in **spotDL itself** as a dependency.

### Option A — Reuse Yoink's own pipeline, no spotDL *(recommended)*

Borrow only the **idea**, not the tool — there is **no spotDL dependency**:

1. Resolve the Spotify URL → a tracklist by scraping the **public embed page**
   (keyless; our own small extractor).
2. Turn each track into a query — `"<artist> <title>"` — and hand it to Yoink's
   **existing** flow: the persistent download **queue** → yt-dlp
   (`ytsearch1:`/`ytmsearch`) → the **auto-tagger**, seeded with the *exact
   Spotify fields* instead of guessing from the filename.

- **Pros:** native Yoink progress/UI, the queue's resume, Yoink's own tagger
  (arguably better than spotDL's), **no shared credentials, stays keyless**, no
  heavy dependency.
- **Cons:** we write the Spotify→query glue and the YouTube match-ranking.

### Option B — Embed spotDL as a backend library

`pip install spotdl`, then `Spotdl(...).search(urls)` + `download_songs(...)`.

- **Pros:** least code; battle-tested YouTube matching + lyrics out of the box.
- **Cons:** a heavy dependency whose **own** download + tag pipeline *bypasses*
  Yoink's (separate progress, separate tagger, separate settings, separate
  ffmpeg wiring); relies on the shared default credentials; tight version
  coupling. It would feel bolted-on, not native.

## Recommended flow (Option A)

```
Spotify URL
  → resolve tracklist        (keyless embed JSON)        [new: a small extractor]
  → per track: "artist title" → yt-dlp ytsearch1/ytmsearch → best match   [reuse]
  → download via the queue   (sequential, resumable)                      [reuse]
  → auto-tag with the Spotify fields (title/artist/album/cover/#/year)    [reuse]
  → (optional) lyrics via LRCLIB — embedded + a synced .lrc (shipped)     [reuse]
```

The only **new** backend code is the Spotify tracklist extractor + the match
ranking; everything downstream is plumbing Yoink already has.

## Match ranking — port spotDL's logic, don't depend on it

Option A's one weak spot vs Option B is picking the *right* YouTube result.
spotDL is MIT-licensed, so we can **re-implement its scoring** (it's just maths +
word lists — no Spotify access, no dependency) and run it over yt-dlp's
`ytmsearchN:` candidates. The algorithm, adapted:

**1. Search.** Query YouTube *Music* (cleaner metadata + official audio) with
`ytmsearch5:"<artist> <title>"`. yt-dlp returns candidates with title, uploader/
channel, and duration.

**2. Normalize** both sides before comparing — lowercase, strip diacritics,
slugify, drop hyphens, sort the tokens, so word order and punctuation don't hurt.

**3. Score each candidate** (each signal 0–100):

| Signal | How |
| --- | --- |
| `name_match` | fuzzy ratio of Spotify title vs candidate title |
| `artist_match` | fuzzy ratio of the main artist + all artists vs the channel/title |
| `album_match` | fuzzy ratio of album name (when present) |
| `time_match` | `exp(-0.1 * abs(spotify_secs - candidate_secs)) * 100` |

**4. Penalize the wrong *kind*** with a forbidden-words list — *remix,
remastered, live, acoustic, 8d, concert, acapella, slowed, instrumental, cover,
karaoke, bassboost, reverb, sped up*. Each forbidden word the candidate has **but
the Spotify track doesn't** subtracts ~15 from `name_match` (and the reverse must
not fire — if the track *is* a remix, don't punish "remix").

**5. Combine:** `avg = (artist_match + name_match) / 2`; fold in `album_match`
when it's low/available, then `time_match`; cap at 100.

**6. Accept / reject:** skip a candidate if `name_match < 60`, `artist_match < 70`,
`time_match < 25`, or (`time_match < 50` and `avg < 75`). Take the highest scorer
that survives; if none do, surface the top result for the user to confirm rather
than guessing.

**Notes for Yoink:**
- The fuzzy ratio can be stdlib `difflib.SequenceMatcher` (zero deps, keeps the
  no-extra-deps spirit) or `rapidfuzz` (faster/better, one dep) — start with
  difflib, swap if accuracy demands it.
- spotDL's single best signal is the **ISRC** (exact recording id) for a
  pinpoint match — but the **keyless embed page may not expose the ISRC** (it's
  an API field). Without it we lean on the fuzzy score above, which is still what
  spotDL falls back to for most tracks. If a track won't match, the manual
  search/edit in the tag card is the safety net.

This closes the gap: **keyless + native pipeline (A) + spotDL-grade matching**,
with nothing depending on spotDL itself.

## Caveats (state these in the UI)

- **It's the YouTube version, not the Spotify master** — bitrate (128 kbps),
  edits, or the wrong cut (live/remix/sped-up) can differ. Matching is never
  100% — surface the picked video so the user can correct it.
- **Legal:** spotDL's own note applies — *users are responsible for their use*;
  no support for downloading copyrighted material. Same posture Yoink already
  takes.
- **Never the Spotify stream itself** (DRM) — this is metadata + a YouTube proxy,
  nothing more.

## Status

**Implemented** (Option A) and generalized to Spotify / Deezer / Apple Music /
Tidal / Amazon Music — `services/music_import.py` (keyless resolvers, SSRF-guarded
fetches) + `matching.py` (the spotDL-ported ranking) + `routers/music.py`, with
the `MusicImportCard` on the frontend and a music-group path in the download
queue. This file remains the design reference for *why* it works this way.

## Sources

- [spotDL repo](https://github.com/spotDL/spotify-downloader) ·
  [docs / usage](https://spotdl.readthedocs.io/en/latest/usage/)
- [Programmatic API discussion (#2060)](https://github.com/spotDL/spotify-downloader/issues/2060)
