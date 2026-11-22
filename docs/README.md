# Yoink Documentation

This folder holds the project's design docs and explanations.

| Document | What's inside |
| --- | --- |
| [architecture.md](architecture.md) | System design: the two native Rust layers, the communication contract, data flow |
| [desktop.md](desktop.md) | The egui desktop app: structure, state, conventions |
| [backend.md](backend.md) | The native Rust backend (`yoink-core`): structure, modules, conventions |
| [cli.md](cli.md) | The `yoink <url>` command line (built into `yoink-core`): usage, flags, config |
| [ROADMAP.md](ROADMAP.md) | The single source of truth: status, what's shipped (by area), what's next, and the vetted backlog |
| [music-import.md](music-import.md) | Design notes for the multi-service music import (Spotify/Deezer/Apple/Tidal/Amazon) — the spotDL approach, the keyless trade-off, and how it reuses Yoink's pipeline |
| [po-token-webview.md](po-token-webview.md) | Zero-config YouTube PO tokens: minting a session GVS token in the app's WebView (bgutils-js), the backend bridge, and the SSRF-scoped proxy |
| [releasing.md](releasing.md) | Cutting a versioned release (the signed AppImage), building ffmpeg, and the updater/migration |
| [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) | Attribution for bundled software (ffmpeg, yt-dlp) |

See also [`../CLAUDE.md`](../CLAUDE.md) for a high-level guide and conventions.
