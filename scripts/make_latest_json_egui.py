#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Assemble the updater `latest.json` for the egui desktop release.

    python scripts/make_latest_json_egui.py <artifacts-dir>

Scans <artifacts-dir> for the signed release assets and writes `latest.json`
beside them, mapping each target to its download URL (on the `v<ver>` release)
and its inline minisign signature:

  - `Yoink_<ver>_amd64.AppImage.sig`   -> linux-x86_64
  - `Yoink_<ver>_x64-setup.exe.sig`    -> windows-x86_64

At least one must be present. The egui updater and the legacy Tauri updater both
read this file; the signature is the SAME minisign signature (one key), so each
signed asset serves both the egui self-update and the one-time legacy->egui
migration.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "ayozetr/yoink-app"


def _version() -> str:
    cargo = (ROOT / "desktop" / "Cargo.toml").read_text()
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', cargo)
    if not m:
        raise SystemExit("! could not read version from desktop/Cargo.toml")
    return m.group(1)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: make_latest_json_egui.py <artifacts-dir>")
    art = Path(sys.argv[1])
    version = _version()
    tag = f"v{version}"
    base = f"https://github.com/{REPO}/releases/download/{tag}"

    # (target, asset filename) for each platform we may have built.
    assets = {
        "linux-x86_64": f"Yoink_{version}_amd64.AppImage",
        "windows-x86_64": f"Yoink_{version}_x64-setup.exe",
    }
    platforms: dict[str, dict[str, str]] = {}
    for target, asset in assets.items():
        sig = art / f"{asset}.sig"
        if not sig.exists():
            continue
        platforms[target] = {
            "signature": sig.read_text().strip(),
            "url": f"{base}/{asset}",
        }
    if not platforms:
        raise SystemExit(f"! no signed release assets (.sig) found in {art}")

    data = {
        "version": version,
        "pub_date": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "platforms": platforms,
    }

    out = art / "latest.json"
    out.write_text(json.dumps(data, indent=2) + "\n")
    print(f"[OK] wrote {out} (version {version}): {', '.join(sorted(platforms))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
