#!/usr/bin/env bash
# Assemble a loadable, per-browser extension folder from the shared source.
#
#   ./build.sh firefox     -> dist/firefox   (background.scripts + gecko id)
#   ./build.sh chromium     -> dist/chromium  (background.service_worker)
#   ./build.sh              -> both
#   ./build.sh package      -> both + zip each into dist/*.zip (release assets)
#
# "Load unpacked" (Chromium) / "Load Temporary Add-on" (Firefox) needs the folder
# to contain a file literally named manifest.json — this just copies the shared
# src/ plus the right manifest.<browser>.json into dist/<browser>/.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

build() {
  local browser="$1" out="$here/dist/$1"
  if [ ! -f "$here/manifest.$browser.json" ]; then
    echo "no manifest.$browser.json" >&2
    exit 1
  fi
  rm -rf "$out"
  mkdir -p "$out"
  cp -r "$here/src/." "$out/"
  cp "$here/manifest.$browser.json" "$out/manifest.json"
  echo "built $out"
}

# Zip a built folder with manifest.json at the archive root (what a browser wants).
# Uses Python's zipfile so it needs no `zip` binary on PATH.
pack() {
  local browser="$1" ver
  ver="$(grep -m1 '"version"' "$here/manifest.$browser.json" | tr -dc '0-9.')"
  local base="$here/dist/send-to-yoink-$ver-$browser"
  rm -f "$base.zip"
  python3 -c "import shutil,sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2])" \
    "$base" "$here/dist/$browser"
  echo "packaged $base.zip"
}

case "${1:-all}" in
  firefox) build firefox ;;
  chromium | chrome) build chromium ;;
  all) build firefox; build chromium ;;
  package)
    build firefox; build chromium
    pack firefox; pack chromium
    ;;
  *) echo "usage: $0 [firefox|chromium|all|package]" >&2; exit 1 ;;
esac
