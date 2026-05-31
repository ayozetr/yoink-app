# yt-dlp — Reference for Yoink

Yoink's download engine is **[yt-dlp](https://github.com/yt-dlp/yt-dlp)**, a
feature-rich fork of youtube-dl. This document distills the parts of yt-dlp that
matter for Yoink: how it works, its dependencies, and the Python embedding API
the backend builds on.

> Condensed and adapted from the [official yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md).
> For exhaustive detail, see that README and the [wiki](https://github.com/yt-dlp/yt-dlp/wiki).

---

## 1. What it is

yt-dlp is a command-line program **and** a Python library to download video and
audio from thousands of sites. It supports format/quality selection, merging
separate video+audio streams (via ffmpeg), audio extraction, metadata and
thumbnail embedding, subtitles, playlists, and more.

Yoink uses yt-dlp **as a library, embedded in Python** — never by parsing its
CLI stdout.

## 2. How it works (pipeline)

```
URL ──▶ Extractor ──▶ "info dict" ──▶ Format selection ──▶ Downloader ──▶ Post-processing ──▶ file(s)
        (per-site)    (metadata +      (-f / filters /      (http, m3u8,    (ffmpeg merge,
                       formats list)    sorting)             dash, …)        audio extract, …)
```

1. **Extractor** — a site-specific module turns a URL into an **info dict**: a
   dictionary-like object with the title, uploader, duration, thumbnails, and a
   list of available **formats**.
2. **Format selection** — a selector expression (`-f`) and optional filters/sort
   pick which format(s) to download. Video-only + audio-only formats can be
   merged.
3. **Download** — the chosen format is fetched with the appropriate protocol
   handler (HTTP/HTTPS, HLS `m3u8`, DASH segments, etc.). `progress_hooks` fire
   during this stage with percent / speed / ETA.
4. **Post-processing** — ffmpeg merges video+audio, extracts/recodes audio,
   embeds thumbnails/metadata, etc.

**Key behavior for metadata:** calling `extract_info(url, download=False)`
performs only step 1 (and resolves formats) — it does **not** download. This is
exactly what Yoink's `/api/info` endpoint does.

## 3. Dependencies

Python **3.10+** (CPython) / **3.11+** (PyPy).

### Strongly recommended (effectively required for Yoink)

| Dependency | Why it matters for Yoink |
| --- | --- |
| **ffmpeg** + **ffprobe** (binaries) | Merging separate video+audio formats and all audio extraction/recoding. Must be the **binaries on `PATH`**, *not* the PyPI package named `ffmpeg`. |
| **yt-dlp-ejs** + a JS runtime (deno/node/bun/QuickJS) | Required for **full YouTube support** (signature solving). Without it some YouTube formats may be unavailable. |

> Official ffmpeg builds tuned for yt-dlp: <https://github.com/yt-dlp/FFmpeg-Builds>.

### Optional (bundled into standalone binaries, marked `*` upstream)

- **Networking:** `certifi` (CA bundle), `brotli`/`brotlicffi` (Brotli),
  `websockets` (websocket downloads), `requests` (HTTPS proxy / keep-alive).
- **Impersonation:** `curl_cffi` — impersonate Chrome/Edge/Safari TLS
  fingerprints for sites that block default clients. Install via the extra:
  `pip install "yt-dlp[default,curl-cffi]"`.
- **Metadata:** `mutagen`, `AtomicParsley` (thumbnail embedding), `xattr` (xattr
  metadata).
- **Misc:** `pycryptodomex` (AES-128 HLS decryption), `secretstorage`
  (`--cookies-from-browser` on Linux/GNOME).

yt-dlp warns at runtime if a dependency needed for the requested task is
missing. The full list of detected dependencies appears at the top of
`yt-dlp --verbose` output.

### In Yoink

`yt-dlp` itself is pinned in [`backend/requirements.txt`](../backend/requirements.txt).
**ffmpeg must be installed separately** (system package manager or the builds
above) and available on `PATH` — it is *not* a pip dependency.

## 4. Python embedding API (what the backend uses)

The entry point is `yt_dlp.YoutubeDL`, used as a context manager. Options are a
plain dict (`ydl_opts`). For the full option list see `help(yt_dlp.YoutubeDL)`
or [`yt_dlp/YoutubeDL.py`](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py).

### Extracting metadata only (no download) — used by `/api/info`

```python
import yt_dlp

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

ydl_opts = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(URL, download=False)
    # extract_info's return value is NOT guaranteed json-serializable;
    # sanitize_info makes it a clean, serializable dict.
    clean = ydl.sanitize_info(info)
```

> **Important:** `YoutubeDL.extract_info` is *dictionary-like* but not guaranteed
> to be a serializable `dict`. Always pass it through `ydl.sanitize_info(...)`
> before returning it as JSON. Yoink does this in `ytdlp_service.extract_info`.

### Downloading + live progress (Yoink Phase 3, planned)

```python
import yt_dlp

def progress_hook(d: dict) -> None:
    if d["status"] == "downloading":
        # d has keys like: downloaded_bytes, total_bytes / total_bytes_estimate,
        # speed (bytes/s), eta (s), filename, plus pre-formatted _percent_str etc.
        ...
    elif d["status"] == "finished":
        # download done; post-processing (e.g. ffmpeg merge) follows
        ...

ydl_opts = {
    # Best video + best audio merged, falling back to best combined:
    "format": "bestvideo*+bestaudio/best",
    "merge_output_format": "mp4",
    "outtmpl": "%(title)s.%(ext)s",
    "paths": {"home": "/path/to/downloads"},
    "progress_hooks": [progress_hook],
    "noplaylist": True,
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    error_code = ydl.download([URL])
```

In Yoink this runs in a **FastAPI background task**, and the hook forwards
progress events over **WebSocket/SSE** to animate the UI progress bar.

### Audio-only extraction (e.g. MP3/M4A)

```python
ydl_opts = {
    "format": "bestaudio/best",
    "postprocessors": [{
        "key": "FFmpegExtractAudio",   # uses ffmpeg
        "preferredcodec": "mp3",       # or "m4a", etc.
    }],
}
```

### Useful `ydl_opts` keys

| Option | Purpose |
| --- | --- |
| `format` | Format selector expression (see §6). |
| `merge_output_format` | Container for merged output, e.g. `"mp4"`, `"mkv"`. |
| `outtmpl` | Output filename template (see [Output Template](https://github.com/yt-dlp/yt-dlp#output-template)). |
| `paths` | Dict of output paths, e.g. `{"home": ..., "temp": ...}`. |
| `progress_hooks` | List of callables receiving the progress dict. |
| `postprocessors` | List of post-processor configs (audio extract, merge, embed). |
| `noplaylist` | Treat a URL with a playlist param as a single video. |
| `quiet`, `no_warnings` | Silence console output (we use a logger instead). |
| `skip_download` | Don't download (paired with `download=False` for info-only). |
| `cookiefile` / `cookiesfrombrowser` | Authenticated/age-gated content. |

> Tip: yt-dlp ships `devscripts/cli_to_api.py` to translate CLI flags into the
> equivalent `ydl_opts` dict.

## 5. The info dict (commonly used fields)

Returned by `extract_info` (per video). Field availability depends on the
extractor — none are guaranteed.

| Field | Meaning |
| --- | --- |
| `id` | Source-specific media id |
| `title` | Title |
| `duration` | Duration in seconds (float/int) |
| `duration_string` | Human-readable duration |
| `uploader` / `channel` | Author/channel name |
| `thumbnail` / `thumbnails` | Best thumbnail URL / list of candidates |
| `webpage_url` | Canonical page URL |
| `extractor` / `extractor_key` | Which extractor handled it |
| `formats` | List of available formats (see §6) |
| `_type` | `"playlist"` for multi-entry results (has `entries`) |

Yoink maps these into the typed `VideoInfo`/`MediaFormat` Pydantic models in
[`backend/app/models/media.py`](../backend/app/models/media.py).

## 6. Format selection

Default (no options) ≈ `bestvideo*+bestaudio/best` (best video + best audio
merged, else best combined). Selectors are passed via the `format` option.

### Special selector names

| Selector | Meaning |
| --- | --- |
| `b` / `best` | Best format with **both** video and audio |
| `b*` / `best*` | Best format with video **or** audio (or both) |
| `bv` / `bestvideo` | Best **video-only** format |
| `bv*` / `bestvideo*` | Best format that **contains video** (maybe audio) |
| `ba` / `bestaudio` | Best **audio-only** format |
| `w` / `worst`, `wv`, `wa`, … | Worst-quality equivalents |

- **Precedence:** `a/b/c` → try `a`, else `b`, else `c`.
- **Merge:** `bestvideo+bestaudio` → download both and mux with ffmpeg.
- **Multiple:** `22,17,18` → download several formats.
- **By extension:** `-f mp4`, `-f webm`, etc.
- **n-th best:** `best.2`, `bv*.3`.

### Filtering — `format[condition]`

Numeric fields (`<`, `<=`, `>`, `>=`, `=`, `!=`): `filesize`, `filesize_approx`,
`width`, `height`, `aspect_ratio`, `tbr`, `abr`, `vbr`, `asr`, `fps`,
`audio_channels`, `stretched_ratio`.

String fields (`=`, `^=` starts, `$=` ends, `*=` contains, `~=` regex):
`ext`, `acodec`, `vcodec`, `container`, `protocol`, `language`, `dynamic_range`,
`format_id`, `format_note`, `resolution`, `url`.

Examples:
- `best[height=720]` — best 720p.
- `bv[height<=?720][tbr>500]` — ≤720p (or unknown height) with bitrate ≥500 kbps
  (`?` keeps formats where the value is unknown).
- `(mp4,webm)[height<480]` — best pre-merged mp4/webm under 480p.

`acodec=none` means no audio; `vcodec=none` means no video — this is how Yoink
derives `has_video` / `has_audio` on each `MediaFormat`.

### Sorting — `-S` / `format_sort`

Override what counts as "best", e.g. `-S +size,+br,+res,+fps` to prefer smaller
size. Recommended over `worst` for "smallest file".

## 7. `progress_hooks` dict

Each hook receives one dict `d`. Most relevant keys:

| Key | When | Meaning |
| --- | --- | --- |
| `status` | always | `"downloading"`, `"finished"`, or `"error"` |
| `downloaded_bytes` | downloading | Bytes downloaded so far |
| `total_bytes` | downloading | Total size (if known) |
| `total_bytes_estimate` | downloading | Estimate when exact size unknown |
| `speed` | downloading | Bytes/second (may be `None`) |
| `eta` | downloading | Seconds remaining (may be `None`) |
| `filename` | always | Destination filename |
| `info_dict` | always | The format's info dict |
| `_percent_str`, `_speed_str`, `_eta_str` | downloading | Pre-formatted strings |

Compute percent as `downloaded_bytes / (total_bytes or total_bytes_estimate)`.
Hooks run on the download thread — in Yoink, marshal events to the WS/SSE layer
rather than blocking.

## 8. How Yoink uses yt-dlp today

- **`backend/app/services/ytdlp_service.py`** is the *only* module that imports
  yt-dlp. It calls `extract_info(url, download=False)` + `sanitize_info`, then
  normalizes the result into typed models.
- **`/api/info`** (`backend/app/routers/info.py`) exposes that as REST; failures
  surface as `MediaExtractionError` → HTTP 422.
- **Planned:** a download service using `progress_hooks` in a background task,
  streaming progress over WebSocket/SSE (see the [roadmap](ROADMAP.md), Phase 3).

## 9. References

- README: <https://github.com/yt-dlp/yt-dlp/blob/master/README.md>
- Embedding section: <https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp>
- Format selection: <https://github.com/yt-dlp/yt-dlp#format-selection>
- Output template: <https://github.com/yt-dlp/yt-dlp#output-template>
- Post-processing options: <https://github.com/yt-dlp/yt-dlp#post-processing-options>
- Wiki: <https://github.com/yt-dlp/yt-dlp/wiki>
- `help(yt_dlp.YoutubeDL)` for the authoritative, version-matched option list.
