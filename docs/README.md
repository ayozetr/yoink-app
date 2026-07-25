# Yoink Documentation

This folder holds the project's design docs and explanations.

| Document | What's inside |
| --- | --- |
| [architecture.md](architecture.md) | System design: the two layers, the communication contract, data flow |
| [frontend.md](frontend.md) | Frontend structure, components, conventions |
| [backend.md](backend.md) | Backend structure, the yt-dlp wrapper, the API |
| [cli.md](cli.md) | The `yoink <url>` command-line front-end: usage, all flags, and how it reuses the engine |
| [yt-dlp.md](yt-dlp.md) | yt-dlp reference: how it works, dependencies, the Python embedding API |
| [ROADMAP.md](ROADMAP.md) | The single source of truth: status, what's shipped (by area), what's next, and the vetted backlog |
| [music-import.md](music-import.md) | Design notes for the multi-service music import (Spotify/Deezer/Apple/Tidal/Amazon) — the spotDL approach, the keyless trade-off, and how it reuses Yoink's pipeline |
| [releasing.md](releasing.md) | Cutting a versioned release (Linux + Windows), bundling ffmpeg, and packaged-app troubleshooting |
| [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) | Attribution for bundled software (ffmpeg LGPL, yt-dlp) |

See also [`../CLAUDE.md`](../CLAUDE.md) for a high-level guide and conventions.
