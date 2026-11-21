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
# Everything except libc is linked statically, so the binaries are portable.
#
# Usage:
#   scripts/build_ffmpeg.sh                 # native (Linux) -> ffmpeg, ffprobe
#   scripts/build_ffmpeg.sh --windows       # cross-compile (mingw-w64) -> *.exe
#
# The Windows cross build runs on a Linux host (CI builds it on the Linux runner
# and hands the .exe files to the Windows job), so there is one reproducible
# recipe for both platforms. Prereqs: gcc, make, cmake, curl, pkg-config; for
# --windows also the mingw-w64 toolchain (x86_64-w64-mingw32-gcc). nasm is
# optional (without it the build uses --disable-x86asm, i.e. no SIMD, which only
# slows the short audio re-encodes). Output: backend/vendor/ffmpeg/.
set -euo pipefail

FFMPEG_VERSION="${FFMPEG_VERSION:-7.1.1}"
LAME_VERSION="${LAME_VERSION:-3.100}"
MBEDTLS_VERSION="${MBEDTLS_VERSION:-3.6.2}"

TARGET="linux"
[ "${1:-}" = "--windows" ] && TARGET="windows"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/backend/vendor/ffmpeg"
WORK="${FFMPEG_BUILD_DIR:-$ROOT/build/ffmpeg}"
DEPS="$WORK/deps-$TARGET"
JOBS="$(nproc 2>/dev/null || echo 4)"
mkdir -p "$WORK" "$DEPS" "$VENDOR"
cd "$WORK"

# Per-target toolchain.
if [ "$TARGET" = "windows" ]; then
  CROSS="x86_64-w64-mingw32-"
  EXE=".exe"
  LAME_HOST="--host=x86_64-w64-mingw32"
  FF_CROSS=(--arch=x86_64 --target-os=mingw32 --cross-prefix="$CROSS" --enable-cross-compile)
  MBED_CROSS=(-DCMAKE_SYSTEM_NAME=Windows
    -DCMAKE_C_COMPILER=${CROSS}gcc -DCMAKE_CXX_COMPILER=${CROSS}g++
    -DCMAKE_RC_COMPILER=${CROSS}windres)
  # mingw ffmpeg + mbedTLS need the Win32 socket/crypto system libs.
  SYS_LIBS="-lws2_32 -lbcrypt -lcrypt32"
else
  CROSS=""; EXE=""; LAME_HOST=""; FF_CROSS=(); MBED_CROSS=(); SYS_LIBS=""
fi

echo "[1/5] libmp3lame $LAME_VERSION (static, $TARGET)…"
if [ ! -f "$DEPS/lib/libmp3lame.a" ]; then
  [ -f lame.tar.gz ] || curl -fsSL -o lame.tar.gz "https://downloads.sourceforge.net/project/lame/lame/${LAME_VERSION}/lame-${LAME_VERSION}.tar.gz"
  rm -rf "lame-$LAME_VERSION-$TARGET"; tar xzf lame.tar.gz; mv "lame-$LAME_VERSION" "lame-$LAME_VERSION-$TARGET"
  ( cd "lame-$LAME_VERSION-$TARGET" && \
    ./configure $LAME_HOST --prefix="$DEPS" --disable-shared --enable-static --disable-frontend --disable-gtktest >/dev/null && \
    make -j"$JOBS" >/dev/null && make install >/dev/null )
fi

echo "[2/5] mbedTLS $MBEDTLS_VERSION (static, for https, $TARGET)…"
if [ ! -f "$DEPS/lib/libmbedtls.a" ]; then
  [ -f mbedtls.tar.bz2 ] || curl -fsSL -o mbedtls.tar.bz2 "https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-${MBEDTLS_VERSION}/mbedtls-${MBEDTLS_VERSION}.tar.bz2"
  [ -d "mbedtls-$MBEDTLS_VERSION" ] || tar xjf mbedtls.tar.bz2
  rm -rf "mbedtls-build-$TARGET"
  # MBEDTLS_FATAL_WARNINGS=Off: newer GCC (16+) flags -Wunterminated-string-initialization,
  # which mbedTLS's -Werror would otherwise turn into a build failure.
  cmake -S "mbedtls-$MBEDTLS_VERSION" -B "mbedtls-build-$TARGET" \
    -DCMAKE_INSTALL_PREFIX="$DEPS" -DENABLE_TESTING=Off -DENABLE_PROGRAMS=Off \
    -DUSE_SHARED_MBEDTLS_LIBRARY=Off -DUSE_STATIC_MBEDTLS_LIBRARY=On \
    -DMBEDTLS_FATAL_WARNINGS=Off -DCMAKE_POSITION_INDEPENDENT_CODE=On \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 "${MBED_CROSS[@]}" >/dev/null
  cmake --build "mbedtls-build-$TARGET" -j"$JOBS" >/dev/null
  cmake --install "mbedtls-build-$TARGET" >/dev/null
fi

echo "[3/5] ffmpeg $FFMPEG_VERSION source…"
[ -f ffmpeg.tar.xz ] || curl -fsSL -o ffmpeg.tar.xz "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz"
rm -rf "ffmpeg-$FFMPEG_VERSION-$TARGET"; tar xf ffmpeg.tar.xz; mv "ffmpeg-$FFMPEG_VERSION" "ffmpeg-$FFMPEG_VERSION-$TARGET"
cd "ffmpeg-$FFMPEG_VERSION-$TARGET"

ASM_FLAG=""
command -v "${CROSS}nasm" nasm >/dev/null 2>&1 || command -v yasm >/dev/null 2>&1 || ASM_FLAG="--disable-x86asm"
[ -n "$ASM_FLAG" ] && echo "    (nasm/yasm not found → $ASM_FLAG; install nasm for SIMD)"

echo "[4/5] configure ($TARGET: native codecs + libmp3lame + mbedTLS, no external video libs)…"
PKG_CONFIG_PATH="$DEPS/lib/pkgconfig" ./configure \
  --prefix="$WORK/out-$TARGET" "${FF_CROSS[@]}" \
  --enable-libmp3lame --enable-mbedtls --enable-version3 \
  --extra-cflags="-I$DEPS/include" --extra-ldflags="-L$DEPS/lib" \
  --extra-libs="-lmbedtls -lmbedx509 -lmbedcrypto $SYS_LIBS" --pkg-config-flags=--static \
  --enable-small $ASM_FLAG --disable-doc --disable-htmlpages --disable-manpages \
  --disable-txtpages --disable-ffplay --disable-debug --disable-shared --enable-static >/dev/null

echo "[5/5] make -j$JOBS (this takes a few minutes)…"
make -j"$JOBS" >/dev/null
"${CROSS}strip" "ffmpeg$EXE" "ffprobe$EXE"
cp "ffmpeg$EXE" "ffprobe$EXE" "$VENDOR/"
cp COPYING.LGPLv3 "$VENDOR/FFMPEG-LICENSE.txt" 2>/dev/null || true

echo
echo "Done ($TARGET) → $VENDOR"
du -h "$VENDOR/ffmpeg$EXE" "$VENDOR/ffprobe$EXE" | sed 's/^/  /'
