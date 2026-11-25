# Third-party licenses

Yoink bundles third-party software in its desktop builds. This file records the
attribution and license obligations.

## FFmpeg (ffmpeg + ffprobe)

The desktop app bundles the `ffmpeg` and `ffprobe` binaries so downloads work
without a system install. They are used by the download engine (via yt-dlp) to
merge high-quality video+audio, to extract/recode audio (MP3/M4A/FLAC/WAV), and
to embed subtitles, chapters and metadata.

- **Project:** FFmpeg — <https://ffmpeg.org>
- **Source code:** <https://github.com/FFmpeg/FFmpeg> (we build the pinned
  release **7.1.1**).
- **License:** GNU **LGPL v3 or later** (the build enables `--enable-version3`
  so it can link mbedTLS; still **LGPL**, not GPL — no GPL-only components are
  enabled).
- **Build provenance:** we build a **minimal, self-contained** ffmpeg/ffprobe
  ourselves with [`scripts/build_ffmpeg.sh`](../scripts/build_ffmpeg.sh) — only
  FFmpeg's native codecs plus libmp3lame (MP3 encoding) and mbedTLS (https); none
  of the heavy external video codec libraries, since Yoink never decodes or
  re-encodes video (it stream-copies). This is ~33 MB total vs the ~336 MB of the
  previous all-codecs prebuild. `scripts/build_ffmpeg.sh` (BtbN LGPL prebuilts)
  remains as a fallback.
- **Corresponding source & relinking (LGPL):** the complete source of FFmpeg and
  of the statically linked libraries is the upstream of each pinned version
  (FFmpeg 7.1.1, LAME 3.100, mbedTLS 3.6.2); the exact configuration and build
  steps are in `scripts/build_ffmpeg.sh`. Because the LGPL libraries are linked
  statically, the user may rebuild/relink a modified FFmpeg by re-running that
  script against modified sources; object files for relinking are available on
  request.
- **License text:** the full FFmpeg license/notice (`FFMPEG-LICENSE.txt`) ships
  inside the app bundle alongside the binaries, and a copy lives in
  `backend/vendor/ffmpeg/` after the build.

### Statically linked into FFmpeg

- **LAME (libmp3lame)** — MP3 encoder, **LGPL v2 or later**. Source (pinned
  3.100): <https://lame.sourceforge.io/>.
- **Mbed TLS (mbedtls)** — TLS for `https`, **Apache-2.0**. Source (pinned
  3.6.2): <https://github.com/Mbed-TLS/mbedtls>.

## yt-dlp

The download engine. yt-dlp is released into the public domain
([The Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE)).
Installed as a Python dependency (not separately bundled here).
