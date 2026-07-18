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

# Zip dist/<browser>/ to <base>.zip with manifest.json at the archive root (what a
# browser wants). Uses Python's zipfile so it needs no `zip` binary on PATH.
zip_build() {
  local browser="$1" base="$2"
  rm -f "$base.zip"
  python3 -c "import shutil,sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2])" \
    "$base" "$here/dist/$browser"
}

# Versioned zip for a Yoink *app* release asset (send-to-yoink-<ver>-<browser>.zip).
pack() {
  local browser="$1" ver
  ver="$(grep -m1 '"version"' "$here/manifest.$browser.json" | tr -dc '0-9.')"
  local base="$here/dist/send-to-yoink-$ver-$browser"
  zip_build "$browser" "$base"
  echo "packaged $base.zip"
}

# Push the current build to the rolling `ext-latest` GitHub pre-release — the stable
# manual-install channel, independent of the Yoink app releases. Version-less asset
# names keep the download URLs stable; --clobber replaces them in place. Needs `gh`.
publish_manual() {
  build firefox; build chromium
  local ff="$here/dist/send-to-yoink-firefox" ch="$here/dist/send-to-yoink-chromium"
  zip_build firefox "$ff"
  zip_build chromium "$ch"
  gh release upload ext-latest "$ff.zip" "$ch.zip" --clobber
  echo "updated ext-latest with send-to-yoink-{firefox,chromium}.zip"
}

# Submit the Firefox build to addons.mozilla.org (AMO) and get it signed. Reads the
# AMO API credentials from extension/.env (git-ignored). `listed` = public store
# (first submit needs the listing filled on AMO; later submits just add a version);
# `unlisted` = AMO-signed .xpi you self-host. Bump the manifest version before each.
publish_firefox() {
  build firefox
  local envf="$here/.env"
  if [ -f "$envf" ]; then set -a; . "$envf"; set +a; fi
  : "${AMO_JWT_ISSUER:?set AMO_JWT_ISSUER in extension/.env}"
  : "${AMO_JWT_SECRET:?set AMO_JWT_SECRET in extension/.env}"
  npx --yes web-ext sign \
    --channel="${AMO_CHANNEL:-listed}" \
    --api-key="$AMO_JWT_ISSUER" --api-secret="$AMO_JWT_SECRET" \
    --source-dir "$here/dist/firefox" \
    --artifacts-dir "$here/dist"
}

case "${1:-all}" in
  firefox) build firefox ;;
  chromium | chrome) build chromium ;;
  all) build firefox; build chromium ;;
  package)
    build firefox; build chromium
    pack firefox; pack chromium
    ;;
  publish-firefox) publish_firefox ;;
  publish-manual) publish_manual ;;
  *) echo "usage: $0 [firefox|chromium|all|package|publish-firefox|publish-manual]" >&2; exit 1 ;;
esac
