#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Assemble the updater `latest.json` from the signed release artifacts.

    python scripts/make_latest_json.py v<ver> <artifacts-dir>

The Tauri updater self-installs from the Linux AppImage and the Windows NSIS
`-setup.exe`, so `latest.json` maps those two targets to their download URL and
the signature string found in the matching `.sig` file. The CLI does not
reliably emit this file, so it is built by hand (see docs/releasing.md §6). The
release workflow runs this after downloading both build jobs' artifacts; it also
works locally against a folder holding the `.AppImage.sig` and `-setup.exe.sig`.

The tag must match `package.json`'s version (a stray version bump is the classic
release bug), which this script enforces before writing anything.
"""

from __future__ import annotations

import datetime
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "ayozetr/yoink-app"


def _sig(art: Path, pattern: str) -> str:
    matches = sorted(art.glob(pattern))
    if not matches:
        raise SystemExit(f"! no artifact matched {pattern!r} under {art}")
    if len(matches) > 1:
        raise SystemExit(f"! {pattern!r} matched more than one file: {matches}")
    return matches[0].read_text().strip()


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: make_latest_json.py v<ver> <artifacts-dir>")
    tag = sys.argv[1]
    art = Path(sys.argv[2])
    version = tag[1:] if tag.startswith("v") else tag

    pkg_version = json.loads((ROOT / "package.json").read_text())["version"]
    if pkg_version != version:
        raise SystemExit(
            f"! tag {tag} does not match package.json version {pkg_version}; "
            "bump the five version files before tagging (docs/releasing.md §1)."
        )

    base = f"https://github.com/{REPO}/releases/download/{tag}"
    data = {
        "version": version,
        "pub_date": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "platforms": {
            "linux-x86_64": {
                "signature": _sig(art, "Yoink_*_amd64.AppImage.sig"),
                "url": f"{base}/Yoink_{version}_amd64.AppImage",
            },
            "windows-x86_64": {
                "signature": _sig(art, "Yoink_*_x64-setup.exe.sig"),
                "url": f"{base}/Yoink_{version}_x64-setup.exe",
            },
        },
    }

    out = art / "latest.json"
    out.write_text(json.dumps(data, indent=2) + "\n")
    print(f"[OK] wrote {out} (version {version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
