# Third-party licenses

Yoink bundles third-party software in its desktop builds. This file records the
attribution and license obligations.

## FFmpeg (ffmpeg + ffprobe)

The desktop app bundles the `ffmpeg` and `ffprobe` binaries so downloads work
without a system install. They are used by the download engine (via yt-dlp) to
merge high-quality video+audio and to extract audio (MP3).

- **Project:** FFmpeg — <https://ffmpeg.org>
- **Source code:** <https://github.com/FFmpeg/FFmpeg>
- **License:** GNU **LGPL v2.1 or later**. We deliberately use **LGPL** builds
  (not GPL) to keep distribution obligations light.
- **Build provenance:** prebuilt LGPL binaries from the
  [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) project, fetched
  by `scripts/fetch_ffmpeg.py`. The build scripts (the "scripts used to control
  compilation and installation") are available at that repository.
- **License text:** the full FFmpeg license/notice (`FFMPEG-LICENSE.txt`) is
  shipped inside the app bundle alongside the binaries, and a copy lives in
  `backend/vendor/ffmpeg/` after running the fetch script.

Under the LGPL, the binaries are distributed unmodified; their source and build
scripts are available at the URLs above.

## yt-dlp

The download engine. yt-dlp is released into the public domain
([The Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE)).
Installed as a Python dependency (not separately bundled here).
