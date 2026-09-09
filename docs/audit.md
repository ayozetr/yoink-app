# Yoink — code audit findings (2026-09-09)

Full-project read-only audit run as six parallel passes (backend engine,
backend data/integrations, backend routers, frontend core flows, frontend
UI/features, native/build/extension). **44 findings: 0 High · 13 Medium · 31
Low.** Nothing critical.

These are audit findings, not verified fixes — a few are flagged *uncertain* by
the reviewer and need a confirming test before acting. This file is a to-do
backlog; none are fixed yet. Line numbers are approximate (as of this commit).

Recurring theme worth calling out: three independent **SSRF / request-forgery**
angles on client- or web-influenced URLs — the deep link (M6-1), the media
proxy (M3-1), and `safe_http` port scope (L2-7) — all feed yt-dlp/`fetch_public`
which reach private or arbitrary hosts. Tightening them together would close the
whole class.

## Medium-severity summary (triage first)

| # | Area | File | Issue |
|---|------|------|-------|
| M1-1 | engine | `services/audio_normalize.py:41` | ffmpeg/ffprobe have no timeout and run under the download lock → a hung encode deadlocks the whole queue |
| M1-2 | engine | `services/download_service.py:865` | lock released before the worker is reaped on cancel → abandoned ffmpeg races the next job on the shared `.part` |
| M1-3 | engine | `services/audio_normalize.py:112` | loudnorm re-encode lacks `-map`/`-c:v copy` → embedded cover can be dropped *(uncertain)* |
| M2-1 | data | `services/updates.py:54` | GitHub cache is a racy read-modify-write to a shared `.tmp` → corruption / lost key / wasted API budget |
| M2-2 | data | `services/autotag_service.py:676` | library relocation silently overwrites an existing sibling sidecar (data loss) |
| M2-3 | data | `services/settings_store.py:52` | cookies/proxy/po_token nulled when the key is absent → wipes env-configured secrets at startup |
| M3-1 | routers | `routers/media.py:44` | thumbnail/cover GETs lack the Origin guard the WS uses → open image proxy / SSRF to public hosts |
| M4-1 | frontend | `features/queue/QueuePanel.tsx:206` | every progress tick re-renders the entire queue list (no memoized row) |
| M4-2 | frontend | `features/queue/QueuePanel.tsx:549` | end-of-queue notification count is off by one (stale `itemsRef`) |
| M5-1 | frontend | `features/settings/TermsModal.tsx:22` (+`LicensesModal`) | Escape in the sub-modal also closes the Settings modal underneath |
| M5-2 | frontend | `components/ui/WhatsNewModal.tsx:47` | modal lacks `role="dialog"`/`aria-modal` and a focus trap |
| M6-1 | native | `src-tauri/src/main.rs:49` | deep-link target isn't scheme/host-validated → drive-by `yoink://` SSRF |
| M6-2 | build | `scripts/build_rpm.py:84` | `_find_deb` silently repackages an arbitrary `.deb` under the new version |

---

## Backend — engine core

- **[Med · resource-leak]** `services/audio_normalize.py:41` — **ffmpeg/ffprobe have no `timeout`, and run while the global download lock is held.**
  `_run_ffmpeg` (:40) and `_sample_rate`'s ffprobe (:67) call `subprocess.run` with no `timeout=` (vr.py uses 30/1800). They run on the worker thread while `_download_lock` is held (acquired download_service.py:783, released after `worker.result()`). A hung loudnorm on a corrupt/huge input never returns → the process-wide lock is never released and every later download (all clients) wedges forever.
  *Fix:* bounded `timeout=` on both calls; treat `TimeoutExpired` as a normalization failure (return False, keep the original file).

- **[Med · concurrency]** `services/download_service.py:865` — **lock released before the worker is reaped on cancel.**
  In the `finally`, the lock is released before `await asyncio.gather(worker, …)`. On a mid-merge cancel the worker is still in un-interruptible ffmpeg; releasing the lock lets a queued job start a second yt-dlp run in the same dir. The inline "can't collide" comment only holds when filenames differ — a cancelled-then-re-queued *same* URL collides on the shared `.part`.
  *Fix:* await (or bounded-join) the worker before releasing the lock on the cancel path.

- **[Med · bug — UNCERTAIN]** `services/audio_normalize.py:112` — **loudnorm re-encode may drop the embedded cover.**
  Second pass uses `-map_metadata 0` but no `-map 0` / `-c:v copy` / `-disposition:v attached_pic`. It runs after yt-dlp's `EmbedThumbnail`; the cover is a stream, not metadata, so auto stream selection can drop/mangle it. Hits the case `normalize_audio` on + auto-tag off/failed.
  *Fix:* add `-map 0 -c:v copy -disposition:v:0 attached_pic`. *Confirm:* normalize an audio file with an embedded thumbnail and compare cover before/after.

- **[Low · correctness]** `services/download_service.py:762` — **`.nfo` for a playlist-wrapper is built from the container, not the entry.**
  `nfo.from_info(info, …)` gets the wrapper dict for the Instagram-style shape `_final_path` handles, so title/plot/duration come from the container ("Story by X", `duration=None`), not the clip. (Adjacent to the recent `_final_path` fix.)
  *Fix:* build the `.nfo` from the same entry node `_final_path` resolved.

- **[Low · correctness]** `services/ytdlp_service.py:149` — **`has_audio` false-negative when explicit-silent and unknown formats coexist.**
  `has_audio = has_real_audio or not explicit_silent`; a lone `acodec:"none"` format flips the verdict to False even when an unknown-state muxed track probably has sound — contradicting the docstring and firing a spurious "no audio" warning.
  *Fix:* let a `None`-state format suppress the confirmed-silent conclusion.

- **[Low · correctness]** `core/ytdlp_options.py:166` — **cookie fallback surfaces the browserless error, not the real one.**
  Retries on *any* first-attempt failure with the browser dropped; for a genuinely cookie-needing failure (private/members-only) the propagated message is the second, browserless attempt's — undercutting the "Settings → cookies" guidance.
  *Fix:* re-raise the *first* attempt's exception when the fallback also fails.

- **[Low · concurrency]** `services/download_service.py:735` — **post-download steps aren't cancel-aware and block WS teardown.**
  `apply_vr`, `audio_normalize.normalize`, `nfo.write` don't check `cancel_event`; a cancel during a multi-GB VR box injection or loudnorm can't interrupt them, and the `finally`'s `gather(worker)` blocks until they finish → "Cancel" feels stuck.
  *Fix:* check `cancel_event.is_set()` before each best-effort post step.

- **[Low · bug]** `services/audio_normalize.py:55` — **`_measure` grabs the first `{…}` block in stderr, then indexes keys unguarded.**
  `re.search(r"\{[^{}]+\}", …)` could match a non-loudnorm brace block; the later `measured['input_i']` (:102-105) is an unguarded dict access that would raise on a malformed measurement.
  *Fix:* match the block containing `"input_i"` (or the last one) and use `.get()`.

*Clean:* `vr.py` (MP4 box math verified), `embedded_vr_extractor.py`, `threads_extractor.py`, `po_token.py`, `ffmpeg.py`.

## Backend — data & integrations

- **[Med · data-integrity]** `services/updates.py:54` — **GitHub cache write is a racy read-modify-write to a shared `.tmp`.**
  `/api/version` and `/api/release-notes` can run concurrently on FastAPI's threadpool; both do read → mutate one key → write `github_cache.json.tmp` → `os.replace`. Interleaving corrupts JSON and last-writer-wins loses a key (e.g. the update-check entry) → wasted 60 req/h budget.
  *Fix:* a module `threading.Lock` around writes + a unique temp filename (pid/uuid).

- **[Med · data-integrity]** `services/autotag_service.py:676` — **relocation/rename can silently overwrite a sibling file.**
  `organize_music_library` (+ `rename_to_tagged` :630) only checks `target.exists()` for the audio file, then renames every stem-prefixed sibling into the destination; POSIX `rename` replaces silently. A pre-existing `Artist - Title.nfo/.lrc/.jpg` from another track is overwritten; a stray `.part` gets moved too.
  *Fix:* check `dest.exists()` per sibling (skip/uniquify) and restrict moves to known sidecar suffixes.

- **[Med · correctness]** `services/settings_store.py:52` — **cookies/proxy/po_token nulled unconditionally when the key is absent.**
  Unlike every other field, lines 52-58 assign from `data.get(...)` with no presence guard. Loading a `settings.json` that predates a field (or a partial hand-edit) wipes values set via `YOINK_PROXY`/`YOINK_PO_TOKEN`/etc. env vars to `None` at startup.
  *Fix:* guard each with `if "proxy" in data:` etc.

- **[Low · security]** `services/settings_store.py:28` — **string settings allow an output-path escape via a hand-edited settings.json.**
  `filename_template` (fed to yt-dlp `outtmpl`), `download_dir`, `rate_limit`, `proxy`, `po_token` are unvalidated. A template with `../`/absolute path writes outside the download dir. Local-file trust only, hence Low.
  *Fix:* reject templates with path separators/`..`; confine the resolved output under `download_dir`.

- **[Low · security]** `models/autotag.py:47` — **autotag path fields are arbitrary absolute paths, unconfined.**
  `ApplyRequest.path`/`IdentifyRequest.path` are free-form; the service reads/tags/renames/relocates whatever path is given. CORS-locked to localhost limits exposure. *(Router may constrain — confirm in `routers/autotag.py`; that pass reported `_validate_audio_path` does confine via `resolve()`+`parents`, so this is likely already mitigated at the router.)*
  *Fix:* require the resolved path to be within `download_dir` before any read/write.

- **[Low · correctness]** `services/updates.py:186` — **version parser conflates prereleases and pads short tags.**
  `_parse_version` drops `-rcN`/`+build` (so `1.2.3-rc1 == 1.2.3`) and returns variable-length tuples (`(1,0) < (1,0,0)`). rc treated equal to release; spurious/missing `update_available`. Low because real tags are `X.Y.Z`.
  *Fix:* pad to fixed length; order prereleases below their release.

- **[Low · security]** `core/safe_http.py:183` — **blocks internal IPs but not arbitrary ports on public hosts.**
  A client-supplied `cover_url` like `http://<public-host>:22/` is fetched — external port-interaction / request-forgery primitive (internal SSRF is correctly closed).
  *Fix:* restrict client-influenced fetches to ports 80/443.

- **[Low · correctness]** `services/music_import.py:282` — **a mid-paging Spotify error discards all fetched pages.**
  `_sp_api_tracks` returns `None` on a page-N failure; `_resolve_spotify` then falls back to the ≤100-track embed even though pages 1..N-1 succeeded → silent truncation.
  *Fix:* return the items gathered so far (mark `truncated`), or only fall back when zero pages were retrieved.

- **[Low · correctness]** `services/updates.py:149` — **`whats_new` cached indefinitely under a client-controlled `since` key.**
  No `max_age`; distinct `?since=` values grow the cache blob unbounded, and an edited release body never refreshes.
  *Fix:* give whatsnew entries a TTL (or key only on `current`) and prune.

- **[Low · maintainability]** `models/autotag.py:1` — **docstrings say Apple Music only, but Deezer/MusicBrainz are supported.**
  *Fix:* reword to "Apple Music / Deezer / MusicBrainz".

*Clean:* `core/humanize.py`, `core/logging_config.py`, `models/music.py`, `services/matching.py` (scoring verified), `services/lyrics.py`, `services/history_store.py` (SQL parameterized, migrations idempotent).

## Backend — routers

- **[Med · security]** `routers/media.py:44` — **thumbnail/cover GETs lack the Origin guard the WS handler applies.**
  Plain GETs with no Origin/Sec-Fetch check; any web page can load them via `<img>`/`fetch(no-cors)` (CORS-exempt). Turns the backend into a blind image proxy / SSRF-to-public-hosts (16 MB cap, attacker-controlled `Referer` forwarded) and can probe `/api/cover?path=` for files under the download dir. `download_ws` (download.py:116) already validates Origin for exactly this reason.
  *Fix:* apply the same origin allowlist (or require `Sec-Fetch-Site: same-origin`) to both media GETs.

- **[Low · correctness]** `routers/download.py:179` — **a send on a just-disconnected socket can raise a non-`WebSocketDisconnect`.**
  The send loop only catches `WebSocketDisconnect`; Starlette raises `RuntimeError` when sending after close → surfaces as "Exception in ASGI application" when the user closes the tab mid-download.
  *Fix:* also catch `RuntimeError` around the send loop (treat as a disconnect).

- **[Low · security]** `routers/settings.py:83` — **PUT `/settings` creates an arbitrary absolute directory before validating.**
  `Path(payload.download_dir).mkdir(parents=True, exist_ok=True)` runs on any absolute path, then that path becomes the trust root for every path-confinement guard. CORS/preflight is the only barrier.
  *Fix:* defer `mkdir` until all validation passes; consider rejecting system locations.

*Clean:* `info.py` (503/422 split sound), `music.py`, `history.py` (`/open` guard correct), `autotag.py` (`_validate_audio_path` confines), `main.py` (CORS anchored `^…$`, `fullmatch`).

## Frontend — core flows

- **[Med · perf]** `features/queue/QueuePanel.tsx:206,817` — **every progress tick re-renders the whole queue list.**
  `setProgress` fires several times/second; `items.map(...)` (rows + expanded children, unmemoized) reconciles entirely though only the active row changed.
  *Fix:* memoized `QueueRow`; pass only the active row its live percent; keep other props stable.

- **[Med · correctness]** `features/queue/QueuePanel.tsx:549` — **end-of-queue notification count is off by one.**
  `finish()` reads `itemsRef.current`, synced only in a post-commit effect; the last item's terminal `update()` (drain, :527) runs synchronously right before with no flush → the "N completed, M failed" notify undercounts the final item (row statuses are correct).
  *Fix:* accumulate a local `{done,failed}` tally in the drain loop.

- **[Low · correctness]** `features/downloader/DownloaderPanel.tsx:242` — **batch notifications capture a stale translator / setting.**
  `runJob`'s terminal branch reads `t(...)`/`notifyOnComplete` from the closure at `startQueue` time; a language or toggle change during a long batch yields the old language/flag. QueuePanel mirrors these into refs; this panel doesn't.
  *Fix:* mirror `t`/`notifyOnComplete` into refs.

- **[Low · correctness]** `features/queue/QueuePanel.tsx:469,601` — **Skip ignored during music "match"; Stop during tagging re-downloads.**
  `handleRef`/`rejectRef` are null during `await matchMusic`, so `skipCurrent()` no-ops; `stop()` during `await applyAudioTags` resets the row to pending → the already-downloaded+tagged file re-downloads next run.
  *Fix:* honor skip after `matchMusic`; treat a downloaded track as done even if tagging was interrupted.

- **[Low · perf]** `features/queue/QueuePanel.tsx:248,611` — **drag-reorder persists the whole queue to localStorage on every `dragenter`.**
  Each pointer move over a new row `setItems` → effect `JSON.stringify`s + writes the full queue.
  *Fix:* debounce, or persist on `onDrop`/`onDragEnd`.

- **[Low · memory-leak]** `lib/downloadSocket.ts:88` — **`onerror` doesn't clear the open-timeout timer.**
  `onopen`/`onclose` clear `openTimer`; `onerror` doesn't and doesn't set `closed`. Harmless today only thanks to two downstream guards — fragile.
  *Fix:* clear `openTimer` (and/or set `closed`) in `onerror`.

- **[Low · correctness]** `features/downloader/DownloaderPanel.tsx:369,623` — **a batch abandoned mid-session by a new analyze isn't resumable until reload.**
  `resetDownload({keepBatch})` keeps the localStorage batch but sets `resumeJobs=null`, which is only seeded at mount → the resume banner won't reappear this session.
  *Fix:* re-seed `resumeJobs` from the still-pending jobs when keeping the batch.

- **[Low · perf]** `features/downloader/components/UrlInput.tsx:31` — **search cache is module-global and never invalidated.**
  Session-lifetime LRU (cap 25) with no TTL → stale hits served after results change.
  *Fix:* add a small TTL, or document as intended.

- **[Low · correctness]** `App.tsx:133` — **initial-load loop retries `fetchSettings` forever with no ceiling.**
  Intentional (late backend still connects) and cancel-safe, but an unbounded 2s poll if the backend never comes up.
  *Fix:* if unbounded is intended, none; else cap attempts + a persistent "backend unreachable" state.

*Clean:* `lib/downloadLock.ts`, `batchStore.ts`, `queueStore.ts`, `updater.ts`, `desktop.ts`, `windowProgress.ts`, `features/history/HistorySidebar.tsx`; the WS terminal-vs-close ordering is correct.

## Frontend — UI & features

- **[Med · a11y]** `features/settings/TermsModal.tsx:22` (& `LicensesModal.tsx:22`) — **Escape in the stacked sub-modal also closes Settings underneath.**
  The sub-modals' window Escape listener calls `onClose()` without `stopPropagation()`; App's global Escape (App.tsx:271) then also closes Settings (a `role="dialog"` sub-modal isn't a listbox/popover). AutoTagPanel's lyrics modal already guards this with capture-phase + `stopPropagation`.
  *Fix:* capture-phase + `e.stopPropagation()` in the sub-modals (or have App bail on a nested dialog).

- **[Med · a11y]** `components/ui/WhatsNewModal.tsx:47` — **no `role="dialog"`/`aria-modal`, no focus trap.**
  Focus isn't trapped (Tab reaches the page behind); and App's mod-key guard keys off `[role="dialog"][aria-modal="true"]`, so Ctrl/Cmd+, still toggles Settings and Ctrl/Cmd+L focuses the hidden URL field while it's open.
  *Fix:* add `role="dialog" aria-modal="true"` + `aria-label` + `useFocusTrap`.

- **[Low · security]** `components/ui/Markdown.tsx:36` — **link `href` rendered without scheme sanitization.**
  `[text](url)` → `<a href={url}>` verbatim; React doesn't block `javascript:`/`data:`. Feeds GitHub release-note Markdown. Low (author's own releases) but no defense-in-depth.
  *Fix:* allow only `http:`/`https:`/`mailto:`, else render as text.

- **[Low · i18n]** `i18n/locales/en.ts:182,183,150` — **count-bearing strings not pluralized.**
  `autotag.batchTitle` ("Tag {{count}} songs"), `autotag.applyMarked`, `music.import` used with `{count}` but no `_one`/`_other` → "Tag 1 songs". `music.songs_one/_other` does it right.
  *Fix:* split into `_one`/`_other` across the 14 locales.

- **[Low · a11y]** `lib/useFocusTrap.ts:46` — **Shift+Tab escapes when focus is parked on the container.**
  The handler only redirects at first/last focusable; focus on the `tabIndex={-1}` container itself is neither, so Shift+Tab leaves the dialog. Rare (mount focuses first focusable) but reachable via the late-mount MutationObserver path.
  *Fix:* treat `activeElement === container` as a boundary.

- **[Low · maintainability]** `features/settings/SettingsModal.tsx:129` — **`templateExample` always appends `.mp3`.**
  The filename-template preview hardcodes `.mp3` regardless of default kind/container → misleading for video templates. Cosmetic.
  *Fix:* derive the sample extension from `default_kind`/`default_container`, or drop it.

*Clean:* type contracts (`music.ts`/`autotag.ts`/`download.ts` in sync incl. `genre`); i18n key usage resolves against `en.ts` (dynamic hint keys present); `Select.tsx` Escape doesn't double-close; `format.ts`, `presets.ts`, `notify.ts`, `vrPrefs.ts`, `Toggle`, `Thumbnail`, `ProgressBar`, etc.

## Native / build / extension

- **[Med · security]** `src-tauri/src/main.rs:49` — **deep-link target isn't scheme/host-validated before it drives an analyze.**
  `deep_link_target` only checks non-empty; the frontend path (`App.tsx:217`) also skips validation, unlike drag-and-drop (`^https?://`, App.tsx:310). A web page firing `yoink://download?url=http://169.254.169.254/…` (behind the browser's protocol prompt) hands that URL to yt-dlp, which fetches outside `safe_http` (`InfoRequest.url` is `HttpUrl`, permitting private/loopback). Drive-by internal-host GET with no user paste.
  *Fix:* in `deep_link_target`, reject non-http(s) schemes and private/loopback/link-local hosts (and mirror in the backend before extraction).

- **[Med · correctness]** `scripts/build_rpm.py:84` — **`_find_deb` silently repackages an arbitrary `.deb` under the new version.**
  If `Yoink_{version}_*.deb` misses, it falls back to the newest `*.deb` by mtime, but the rpm's `Version` comes from `package.json` → a stale/drifted deb ships as a mislabeled release. Silent.
  *Fix:* fail loudly when the versioned glob misses; assert the chosen deb's filename version equals `version`.

- **[Low · security]** `src-tauri/tauri.conf.json:24` — **CSP `img-src … https:` allows any HTTPS host.**
  Load-bearing today: cover art renders as direct remote `<img src={cover_url}>` (music/autotag panels), bypassing the host-guarded proxy. Broad `img-src` is a pixel-exfiltration channel if any untrusted string reaches an `<img>`.
  *Fix:* route remote covers through `/api/cover` (as thumbnails already are) and drop `https:`, or scope to known CDN hosts.

- **[Low · build-packaging]** `scripts/build_rpm.py:126,133` — **`%files` lists only regular files (no dir ownership; symlinks dereferenced).**
  Built from `p.is_file()` only → rpm owns no directories (left behind on uninstall; perms unmanaged); `is_file()` follows symlinks so a symlink is packaged as its target.
  *Fix:* emit `%dir` entries; handle symlinks. Verify with `rpm -qp --dump`.

- **[Low · correctness]** `scripts/disable_updater.py:16` — **brittle exact-string match can silently leave the updater enabled.**
  Replaces literal `"createUpdaterArtifacts": true`; any formatting difference prints "already off" and changes nothing → the unsigned Windows VM could emit updater artifacts meant for the trusted host only.
  *Fix:* parse JSON, assert the key exists and was `true`, error if absent.

- **[Low · bug]** `src-tauri/src/main.rs:89,387` — **port probe is TOCTOU-racy (acknowledged) and a spawn failure advertises a dead port.**
  `pick_backend_port` binds/drops before uvicorn binds (race, benign). Worse: when `spawn_backend` returns `None` (exe missing/spawn error), `advertised` falls back to `DEFAULT_PORT` with nothing listening → the UI appears hung with no signal.
  *Fix:* surface a visible error on spawn failure instead of advertising an unbound port.

- **[Low · build-packaging — UNCERTAIN]** `scripts/build_rpm.py:61` — **autoreq over the bundled `.so` payload may leak extra Requires.**
  Default `AutoReq` scans every ELF incl. `_internal/*.so`; could demand extra distro packages and fail to install on some rpm distros.
  *Fix:* verify with `rpm -qp --requires` against Tauri's own rpm on clean Fedora/openSUSE; make the podman test gating.

- **[Low · maintainability]** `src-tauri/src/main.rs:200` — **`kill_backend` depends on `pkill`/`taskkill` being present.**
  Grandchild cleanup shells out; if absent, an ffmpeg grandchild can linger.
  *Fix:* spawn the backend in a new process group and kill the group.

*Clean / least-privilege:* the extension (`background.js` + manifests — MV3, no `host_permissions`, no content-script `matches`, URL `encodeURIComponent`-encoded); `fetch_ffmpeg.py` (sha256-verified, basename extraction); the Tauri updater config (pinned HTTPS endpoint + minisign pubkey); `ci.yml` intentionally disabled (billing lock).
