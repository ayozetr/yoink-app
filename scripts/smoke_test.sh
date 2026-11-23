#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres
#
# End-to-end smoke test: real downloads through the real yt-dlp + bundled ffmpeg,
# verified with ffprobe. This is the layer the unit tests can't cover — it catches
# runtime breakage (ffmpeg flags/codecs, trimming, VR metadata, tag writing) that
# "correct arguments" tests miss.
#
# Not run in per-PR CI (it needs the network and hits a site that rate-limits
# rapid requests). Run it by hand before a release, or in a nightly job:
#
#   bash scripts/smoke_test.sh [URL]
#
# Everything lands in a temp dir and is deleted at the end; your real library and
# history are never touched. Requires a built yoink-core, the bundled ffmpeg, and
# yt-dlp on PATH (or $YOINK_YTDLP).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-https://www.youtube.com/watch?v=_JZom_gVfuw}"   # Notorious B.I.G. - Juicy: 2160p, in the catalogue
CORE="${YOINK_CORE:-$ROOT/backend-rs/target/release/yoink-core}"
FF_DIR="${YOINK_FFMPEG:-$ROOT/backend/vendor/ffmpeg}"
FFPROBE="$FF_DIR/ffprobe"
PAUSE="${SMOKE_PAUSE:-8}"   # seconds between downloads, to avoid rate-limit 403s

[ -x "$CORE" ] || { echo "! yoink-core not built at $CORE (cargo build --release in backend-rs/)"; exit 1; }
[ -x "$FFPROBE" ] || { echo "! ffprobe not found at $FFPROBE (bash scripts/build_ffmpeg.sh)"; exit 1; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export YOINK_DATA_DIR="$TMP/data" YOINK_FFMPEG="$FF_DIR"
mkdir -p "$YOINK_DATA_DIR"
PASS=0; FAIL=0
probe() { "$FFPROBE" -v error -show_entries "$1" -of default=nw=1 "$2" 2>/dev/null; }
only()  { ls "$1"/*."$2" 2>/dev/null | head -1; }

# check <name> <condition-cmd...> : pass if the command succeeds
check() {
  local name="$1"; shift
  if "$@"; then echo "  PASS  $name"; PASS=$((PASS+1)); else echo "  FAIL  $name"; FAIL=$((FAIL+1)); fi
}

dl() { # dl <subdir> <args...>  (downloads URL into $TMP/<subdir>)
  local d="$TMP/$1"; shift; mkdir -p "$d"
  timeout 240 "$CORE" "$@" -o "$d" --quiet --no-progress "$URL" >/dev/null 2>&1
  echo "$d"
}

echo "> Yoink smoke test  (url: $URL)"
echo "> core: $CORE"
echo

echo "[audio formats]"
for f in mp3 flac opus m4a wav; do
  d="$(dl "a_$f" --audio -f "$f")"; file="$(only "$d" "$f")"
  check "audio/$f" test -n "$file"
  sleep "$PAUSE"
done

echo "[video + quality]"
d="$(dl v_mp4 --video -c mp4 -q 360)"; f="$(only "$d" mp4)"
check "video mp4 360p" test -n "$f"
check "  has video+audio" bash -c "probe stream=codec_type '$f' | grep -q video && probe stream=codec_type '$f' | grep -q audio"
sleep "$PAUSE"

echo "[trim]  (the regression this script exists for)"
d="$(dl tr_a --audio -f mp3 --trim-start 5 --trim-end 8)"; f="$(only "$d" mp3)"
check "audio trim 5-8 produced a file" test -n "$f"
if [ -n "$f" ]; then
  dur="$(probe format=duration "$f" | cut -d= -f2)"
  check "  duration ~3s (got ${dur}s)" bash -c "awk 'BEGIN{exit !($dur>2 && $dur<4)}'"
fi
sleep "$PAUSE"

echo "[autotag]  (a mainstream track, so the catalogue matches)"
# A different, well-known track so the catalogue (iTunes/Deezer) reliably matches:
# Dr. Dre - Nuthin' But A "G" Thang.
d="$TMP/tag"; mkdir -p "$d"
timeout 240 "$CORE" --audio -f mp3 --tag -o "$d" --quiet --no-progress \
  "https://www.youtube.com/watch?v=8GliyDgAGQI" >/dev/null 2>&1
f="$(only "$d" mp3)"
check "autotag wrote a title tag" bash -c "[ -n '$f' ] && probe format_tags=title '$f' | grep -q ."
sleep "$PAUSE"

echo "[nfo sidecar]"
"$CORE" config set nfo_sidecars true >/dev/null 2>&1
d="$(dl nfo --video -q 360 -c mp4)"
check "nfo sidecar written" bash -c "ls '$d'/*.nfo >/dev/null 2>&1"
"$CORE" config set nfo_sidecars false >/dev/null 2>&1
sleep "$PAUSE"

echo "[normalize]"
d="$(dl norm --audio -f mp3 --normalize)"
check "normalized audio produced" bash -c "ls '$d'/*.mp3 >/dev/null 2>&1"
sleep "$PAUSE"

echo "[sponsorblock]"
d="$(dl sb --video -q 360 -c mp4 --sponsorblock)"
check "sponsorblock download completed" bash -c "ls '$d'/*.mp4 >/dev/null 2>&1"
sleep "$PAUSE"

echo "[vr]"
d="$(dl vr --video -q 360 -c mp4 --vr-layout 180_sbs)"; f="$(ls "$d"/*.mp4 2>/dev/null | head -1)"
check "vr file produced" test -n "$f"
check "  spherical metadata injected" bash -c "[ -n '$f' ] && probe stream_side_data=side_data_type '$f' | grep -qi spherical"

echo
echo "> $PASS passed, $FAIL failed"
exit $(( FAIL > 0 ? 1 : 0 ))
