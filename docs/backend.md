# Backend

The backend is **`yoink-core`**, a native Rust service (lives in `backend-rs/`).
It is an [axum](https://github.com/tokio-rs/axum) HTTP/WebSocket server that
drives the bundled `yt-dlp` and `ffmpeg` binaries, manages the local filesystem,
and streams download progress to the frontend. There is no Python runtime.

The original Python/FastAPI backend (the one this replaced) is preserved on the
`legacy` branch.

## Running it

```bash
cd backend-rs
cargo run                 # serve the API on :8756 (set YOINK_PORT to change)
cargo build --release     # optimized binary at target/release/yoink-core
cargo fmt && cargo clippy # format + lint (CI gates on both)
cargo test                # unit tests (e.g. the spotDL matcher parity test)
```

The backend shells out to external binaries:

- `yt-dlp` — found on `PATH`, or at `YOINK_YTDLP`.
- `ffmpeg` / `ffprobe` — found at `YOINK_FFMPEG` (a directory), or on `PATH`.

In the packaged desktop app the Tauri shell sets both env vars to the bundled
binaries next to `yoink-core` (see [`releasing.md`](releasing.md)).

## Module map (`backend-rs/src/`)

| File | Responsibility |
|------|----------------|
| `main.rs` | App factory + every HTTP/WS route. Metadata (`/api/info`, `/api/search`), the download WebSocket (`/api/ws/download`, progress + history), settings, logs, history (rusqlite), `/api/open`, release notes, and the shared yt-dlp helpers (transient retry + browser-cookie fallback, 503-vs-422 classification). |
| `matching.rs` | The spotDL-ported YouTube match scorer. A `#[cfg(test)]` test pins its scores to the Python implementation. |
| `music.rs` | Keyless music-service import: Spotify, Deezer, Apple Music, Tidal and Amazon resolvers, plus Deezer enrichment behind a shared rate-limit gate, and ISRC resolution. |
| `autotag.rs` | Catalogue lookups (Apple Music, Deezer, MusicBrainz), lyrics (LRCLIB), and tag/cover writing with `lofty`. |
| `nfo.rs` | Kodi/Jellyfin `.nfo` sidecars (movie / musicvideo, plus folder-level album/artist). |
| `library.rs` | Media-server music-folder relocation (`<Artist>/<Album>/…`) and rename-to-tagged. |
| `vr.rs` | VR detection, Spherical Video V2/V1 box injection into MP4, and the MKV StereoMode remux. |
| `audio_normalize.rs` | Two-pass ffmpeg `loudnorm` (-14 LUFS) and the HLS-trim fallback, both with ffmpeg timeouts. |

## Conventions

- Strictly typed; `cargo clippy -D warnings` and `cargo fmt --check` are clean
  and enforced in CI.
- OS-agnostic paths via `std::path` (Linux + Windows).
- The Rust structs serialize (serde) to the JSON contract that the TypeScript
  types in `src/types/` describe — keep both sides in sync. The endpoint
  behaviours are documented in [`architecture.md`](architecture.md); the
  high-level guide and the full repo layout are in
  [`../CLAUDE.md`](../CLAUDE.md).
