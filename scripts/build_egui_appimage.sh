#!/usr/bin/env bash
# Build the egui desktop app as a self-contained Linux AppImage.
#
# Lays out an AppDir with the egui binary (yoink-desktop) and, beside it, the
# backend it spawns: yoink-core + the pinned standalone yt-dlp + the minimal
# ffmpeg/ffprobe (backend_proc.rs finds them as siblings of the executable).
# linuxdeploy bundles the runtime libraries (incl. GTK, used by the tray) and
# appimagetool packs it. The result is `Yoink_<version>_amd64.AppImage`.
#
# Prereqgs (the release runner installs these): a Rust toolchain, Python 3,
# libgtk-3-dev + libayatana-appindicator3-dev, patchelf, file, curl.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(python3 -c "import json,sys; print(json.load(open('package.json'))['version'])")"
WORK="$ROOT/desktop/target/appimage"
APPDIR="$WORK/AppDir"
TOOLS="$WORK/tools"
OUT="Yoink_${VERSION}_amd64.AppImage"

echo "> Building Yoink $VERSION AppImage"
rm -rf "$WORK"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/512x512/apps" "$TOOLS"

# 1) The egui binary + the backend bundle (yoink-core + yt-dlp + ffmpeg/ffprobe).
cargo build --release --locked --manifest-path desktop/Cargo.toml
python3 scripts/build_core.py   # fills src-tauri/binaries/core/

install -m755 desktop/target/release/yoink-desktop "$APPDIR/usr/bin/yoink-desktop"
for b in yoink-core yt-dlp ffmpeg ffprobe; do
  install -m755 "src-tauri/binaries/core/$b" "$APPDIR/usr/bin/$b"
done

# 2) Desktop entry + icon (AppImage needs both; names must match the icon).
install -m644 desktop/packaging/yoink.desktop "$APPDIR/usr/share/applications/yoink.desktop"
install -m644 desktop/assets/icon.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/yoink.png"

# 3) Fetch the packaging tools (pinned) and bundle.
dl() { # url dest
  if [[ ! -x "$TOOLS/$2" ]]; then
    curl -fsSL "$1" -o "$TOOLS/$2"
    chmod +x "$TOOLS/$2"
  fi
}
LD_VER="1-alpha-20240109-1"
dl "https://github.com/linuxdeploy/linuxdeploy/releases/download/$LD_VER/linuxdeploy-x86_64.AppImage" linuxdeploy
dl "https://github.com/linuxdeploy/linuxdeploy-plugin-gtk/releases/download/1-alpha-20240109-1/linuxdeploy-plugin-gtk-x86_64.AppImage" linuxdeploy-plugin-gtk

export PATH="$TOOLS:$PATH"
export APPIMAGE_EXTRACT_AND_RUN=1   # no FUSE on CI
export NO_STRIP=1                    # some runners' strip chokes on the bundled libs
export OUTPUT="$OUT"
export VERSION

"$TOOLS/linuxdeploy" \
  --appdir "$APPDIR" \
  --executable "$APPDIR/usr/bin/yoink-desktop" \
  --desktop-file "$APPDIR/usr/share/applications/yoink.desktop" \
  --icon-file "$APPDIR/usr/share/icons/hicolor/512x512/apps/yoink.png" \
  --plugin gtk \
  --output appimage

mv -f "$OUT" "$WORK/$OUT"
echo "[OK] $WORK/$OUT ($(du -h "$WORK/$OUT" | cut -f1))"
