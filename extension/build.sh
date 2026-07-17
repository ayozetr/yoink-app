#!/usr/bin/env bash
# Assemble a loadable, per-browser extension folder from the shared source.
#
#   ./build.sh firefox     -> dist/firefox   (background.scripts + gecko id)
#   ./build.sh chromium     -> dist/chromium  (background.service_worker)
#   ./build.sh              -> both
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

case "${1:-all}" in
  firefox) build firefox ;;
  chromium | chrome) build chromium ;;
  all) build firefox; build chromium ;;
  *) echo "usage: $0 [firefox|chromium|all]" >&2; exit 1 ;;
esac
