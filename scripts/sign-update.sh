#!/usr/bin/env bash
# Sign a release asset for the desktop in-place updater.
#
# The egui desktop app verifies every self-update against an embedded ed25519
# public key (desktop/src/api.rs, UPDATE_PUBKEY). Each updatable asset (the Linux
# AppImage and the Windows .exe) must be shipped alongside a detached signature
# named "<asset>.sig" (a raw 64-byte ed25519 signature), or the app refuses the
# update (fail-closed).
#
# Usage:
#   YOINK_UPDATE_KEY="$(cat private.pem)" scripts/sign-update.sh file1 [file2 ...]
# or
#   YOINK_UPDATE_KEY_FILE=private.pem scripts/sign-update.sh file1 [file2 ...]
#
# In CI the private key comes from the `YOINK_UPDATE_KEY` repo secret.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <asset> [asset ...]" >&2
  exit 2
fi

keyfile="$(mktemp)"
trap 'rm -f "$keyfile"' EXIT
if [[ -n "${YOINK_UPDATE_KEY:-}" ]]; then
  printf '%s' "$YOINK_UPDATE_KEY" > "$keyfile"
elif [[ -n "${YOINK_UPDATE_KEY_FILE:-}" ]]; then
  cp "$YOINK_UPDATE_KEY_FILE" "$keyfile"
else
  echo "error: set YOINK_UPDATE_KEY or YOINK_UPDATE_KEY_FILE (the ed25519 private key PEM)" >&2
  exit 2
fi

for asset in "$@"; do
  openssl pkeyutl -sign -inkey "$keyfile" -rawin -in "$asset" -out "$asset.sig"
  # Sanity-check the signature we just wrote.
  pub="$(mktemp)"
  openssl pkey -in "$keyfile" -pubout -out "$pub" >/dev/null 2>&1
  openssl pkeyutl -verify -pubin -inkey "$pub" -rawin -in "$asset" -sigfile "$asset.sig" >/dev/null
  rm -f "$pub"
  echo "signed: $asset -> $asset.sig ($(wc -c < "$asset.sig") bytes)"
done
