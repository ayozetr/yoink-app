# Yoink Documentation

This folder holds the project's design docs and explanations.

| Document | What's inside |
| --- | --- |
| [architecture.md](architecture.md) | System design: the two layers, the communication contract, data flow |
| [frontend.md](frontend.md) | Frontend structure, components, conventions |
| [backend.md](backend.md) | Backend structure, the yt-dlp wrapper, the API |
| [yt-dlp.md](yt-dlp.md) | yt-dlp reference: how it works, dependencies, the Python embedding API |
| [ROADMAP.md](ROADMAP.md) | Forward-looking plan: status, what's shipped (by area), what's next, and the vetted backlog |
| [PLAN.md](PLAN.md) | Tactical improvement plan from the whole-app audit: verified bugs, UX/field redistribution, accessibility, performance and polish, phased by value/effort |
| [spotify-import.md](spotify-import.md) | Design notes for the "Import from Spotify" backlog item — the spotDL approach, the credentials/keyless trade-off, and how it would reuse Yoink's existing pipeline |
| [releasing.md](releasing.md) | Cutting a versioned release (Linux + Windows), bundling ffmpeg, and packaged-app troubleshooting |
| [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) | Attribution for bundled software (ffmpeg LGPL, yt-dlp) |

See also [`../CLAUDE.md`](../CLAUDE.md) for a high-level guide and conventions.
