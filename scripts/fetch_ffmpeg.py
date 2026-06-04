#!/usr/bin/env python3
"""Download static ffmpeg + ffprobe binaries to bundle with the backend.

    python scripts/fetch_ffmpeg.py

Fetches LGPL builds from BtbN/FFmpeg-Builds for the current platform and places
`ffmpeg`/`ffprobe` (or `.exe` on Windows) under `backend/vendor/ffmpeg/`.
`build_backend.py` then embeds them into the PyInstaller sidecar so the app
works without a system ffmpeg. Re-run to refresh; the binaries are gitignored.

LGPL builds keep distribution simple and include libmp3lame (for MP3 output);
YouTube merges are stream copies (remux), so no GPL-only encoders are needed.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "backend" / "vendor" / "ffmpeg"

BASE = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
CHECKSUMS_URL = f"{BASE}/checksums.sha256"


def _asset() -> tuple[str, str]:
    """Return (archive name, archive kind) for the current platform."""
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Windows":
        return "ffmpeg-master-latest-win64-lgpl.zip", "zip"
    if system == "Linux":
        arch = "linuxarm64" if machine in ("aarch64", "arm64") else "linux64"
        return f"ffmpeg-master-latest-{arch}-lgpl.tar.xz", "tar"
    # macOS: BtbN doesn't ship mac; use a different source or Homebrew ffmpeg.
    raise SystemExit(
        f"Unsupported platform for auto-fetch: {system}. "
        "Place ffmpeg/ffprobe in backend/vendor/ffmpeg/ manually."
    )


def _is_license(name: str) -> bool:
    upper = name.upper()
    return upper.startswith(("LICENSE", "COPYING")) or upper == "README.TXT"


def _extract_members(data: bytes, kind: str) -> None:
    """Pull ffmpeg/ffprobe (and the LGPL license) out of the archive."""
    binaries = {"ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"}
    VENDOR.mkdir(parents=True, exist_ok=True)

    def save(name: str, payload: bytes) -> None:
        if name in binaries:
            (VENDOR / name).write_bytes(payload)
        elif _is_license(name):
            # Keep ffmpeg's license/notice alongside the binaries (LGPL).
            (VENDOR / f"FFMPEG-{name}").write_bytes(payload)

    if kind == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                name = Path(info.filename).name
                if name in binaries or _is_license(name):
                    save(name, zf.read(info))
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as tf:
            for member in tf.getmembers():
                name = Path(member.name).name
                if member.isfile() and (name in binaries or _is_license(name)):
                    extracted = tf.extractfile(member)
                    if extracted:
                        save(name, extracted.read())

    # Make the binaries executable (no-op effect on Windows).
    for binary in VENDOR.iterdir():
        if binary.name in binaries:
            binary.chmod(
                binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
            )


def _verify_checksum(data: bytes, asset: str) -> None:
    """Verify the download against BtbN's published checksums.sha256 (integrity).

    BtbN ships a `latest` (moving) tag with no per-asset `.sha256`, but the
    release does carry a global `checksums.sha256`. We match the asset's line and
    compare, so a corrupt or tampered download fails loudly instead of being
    bundled into the app.
    """
    with urllib.request.urlopen(CHECKSUMS_URL) as response:  # noqa: S310 — trusted host
        lines = response.read().decode().splitlines()
    expected = next(
        (
            line.split()[0].lower()
            for line in lines
            if line.split() and line.split()[-1].endswith(asset)
        ),
        None,
    )
    if expected is None:
        raise SystemExit(f"! {asset} not listed in checksums.sha256")
    actual = hashlib.sha256(data).hexdigest().lower()
    if actual != expected:
        raise SystemExit(
            f"! ffmpeg checksum mismatch for {asset}:\n"
            f"  expected {expected}\n  actual   {actual}"
        )
    print("  checksum verified (sha256)")


def main() -> int:
    asset, kind = _asset()
    url = f"{BASE}/{asset}"
    print(f"> Downloading {url} ...")
    with urllib.request.urlopen(url) as response:  # noqa: S310 — trusted host
        data = response.read()
    _verify_checksum(data, asset)
    print(f"  got {len(data) // (1024 * 1024)} MB; extracting ffmpeg + ffprobe...")
    _extract_members(data, kind)

    found = sorted(p.name for p in VENDOR.iterdir())
    if not any(f.startswith("ffmpeg") for f in found):
        print("! ffmpeg not found in the archive.", file=sys.stderr)
        return 1
    print(f"[OK] {', '.join(found)} -> {VENDOR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
