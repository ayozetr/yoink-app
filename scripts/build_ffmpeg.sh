#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres
#
# Build a MINIMAL, self-contained ffmpeg + ffprobe for bundling, replacing the
# ~168 MB-each BtbN builds (which ship ~40 external video codec libraries Yoink
# never uses) with ~17 MB-each binaries (~33 MB total, a ~90% cut).
#
# Yoink never decodes or re-encodes video (it always stream-copies); it only
# re-encodes AUDIO (loudnorm, format conversion) and muxes. So this build keeps
# ffmpeg's native demuxers/muxers/parsers/bsf/decoders + the loudnorm filter,
# adds libmp3lame (MP3 encode) and mbedTLS (https, for yt-dlp's ffmpeg-delegated
# HLS/live streams), and pulls in NONE of the heavy external video encoders.
# Everything except glibc is linked statically, so the binaries are portable.
#
# This is the Linux build. The Windows/macOS release builds need the analogous
# recipe on their platforms (MSYS2 / clang) — same configure flags.
#
# Prereqs (Linux): gcc, make, cmake, curl, pkg-config. nasm is optional but
# recommended (without it the build falls back to --disable-x86asm, i.e. no SIMD,
# which only slows the short audio re-encodes). Output: backend/vendor/ffmpeg/.
set -euo pipefail

FFMPEG_VERSION="${FFMPEG_VERSION:-7.1.1}"
LAME_VERSION="${LAME_VERSION:-3.100}"
MBEDTLS_VERSION="${MBEDTLS_VERSION:-3.6.2}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/backend/vendor/ffmpeg"
WORK="${FFMPEG_BUILD_DIR:-$ROOT/build/ffmpeg}"
DEPS="$WORK/deps"
JOBS="$(nproc 2>/dev/null || echo 4)"
mkdir -p "$WORK" "$DEPS" "$VENDOR"
cd "$WORK"

echo "[1/5] libmp3lame $LAME_VERSION (static)…"
if [ ! -f "$DEPS/lib/libmp3lame.a" ]; then
  curl -fsSL -o lame.tar.gz "https://downloads.sourceforge.net/project/lame/lame/${LAME_VERSION}/lame-${LAME_VERSION}.tar.gz"
  tar xzf lame.tar.gz
  ( cd "lame-$LAME_VERSION" && \
    ./configure --prefix="$DEPS" --disable-shared --enable-static --disable-frontend --disable-gtktest >/dev/null && \
    make -j"$JOBS" >/dev/null && make install >/dev/null )
fi

echo "[2/5] mbedTLS $MBEDTLS_VERSION (static, for https)…"
if [ ! -f "$DEPS/lib/libmbedtls.a" ]; then
  curl -fsSL -o mbedtls.tar.bz2 "https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-${MBEDTLS_VERSION}/mbedtls-${MBEDTLS_VERSION}.tar.bz2"
  tar xjf mbedtls.tar.bz2
  rm -rf mbedtls-build
  # MBEDTLS_FATAL_WARNINGS=Off: newer GCC (16+) flags -Wunterminated-string-initialization,
  # which mbedTLS's -Werror would otherwise turn into a build failure.
  cmake -S "mbedtls-$MBEDTLS_VERSION" -B mbedtls-build \
    -DCMAKE_INSTALL_PREFIX="$DEPS" -DENABLE_TESTING=Off -DENABLE_PROGRAMS=Off \
    -DUSE_SHARED_MBEDTLS_LIBRARY=Off -DUSE_STATIC_MBEDTLS_LIBRARY=On \
    -DMBEDTLS_FATAL_WARNINGS=Off -DCMAKE_POSITION_INDEPENDENT_CODE=On \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 >/dev/null
  cmake --build mbedtls-build -j"$JOBS" >/dev/null
  cmake --install mbedtls-build >/dev/null
fi

echo "[3/5] ffmpeg $FFMPEG_VERSION source…"
[ -d "ffmpeg-$FFMPEG_VERSION" ] || {
  curl -fsSL -o ffmpeg.tar.xz "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz"
  tar xf ffmpeg.tar.xz
}
cd "ffmpeg-$FFMPEG_VERSION"
make distclean >/dev/null 2>&1 || true

ASM_FLAG=""
command -v nasm >/dev/null 2>&1 || command -v yasm >/dev/null 2>&1 || ASM_FLAG="--disable-x86asm"
[ -n "$ASM_FLAG" ] && echo "    (nasm/yasm not found → $ASM_FLAG; install nasm for SIMD)"

echo "[4/5] configure (native codecs + libmp3lame + mbedTLS, no external video libs)…"
PKG_CONFIG_PATH="$DEPS/lib/pkgconfig" ./configure \
  --prefix="$WORK/out" \
  --enable-libmp3lame --enable-mbedtls --enable-version3 \
  --extra-cflags="-I$DEPS/include" --extra-ldflags="-L$DEPS/lib" \
  --extra-libs="-lmbedtls -lmbedx509 -lmbedcrypto" --pkg-config-flags=--static \
  --enable-small $ASM_FLAG --disable-doc --disable-htmlpages --disable-manpages \
  --disable-txtpages --disable-ffplay --disable-debug --disable-shared --enable-static >/dev/null

echo "[5/5] make -j$JOBS (this takes a few minutes)…"
make -j"$JOBS" >/dev/null
strip ffmpeg ffprobe
cp ffmpeg ffprobe "$VENDOR/"
cp COPYING.LGPLv3 "$VENDOR/FFMPEG-LICENSE.txt" 2>/dev/null || true

echo
echo "Done → $VENDOR"
du -h "$VENDOR/ffmpeg" "$VENDOR/ffprobe" | sed 's/^/  /'
"$VENDOR/ffmpeg" -hide_banner -version | head -1
