#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Assemble the updater `latest.json` for the egui desktop release.

    python scripts/make_latest_json_egui.py <artifacts-dir>

Reads the signed `Yoink_<ver>_amd64.AppImage.sig` in <artifacts-dir> and writes
`latest.json` beside it, mapping the Linux target to its download URL (on the
`v<ver>` release) and the inline minisign signature. The egui updater and the
legacy Tauri updater both read this file; the signature is the SAME minisign
signature, so one signed AppImage serves both.

(Windows is added here once the egui Windows package exists.)
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "ayozetr/yoink-app"


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: make_latest_json_egui.py <artifacts-dir>")
    art = Path(sys.argv[1])
    version = json.loads((ROOT / "package.json").read_text())["version"]
    tag = f"v{version}"

    sigs = sorted(art.glob("Yoink_*_amd64.AppImage.sig"))
    if len(sigs) != 1:
        raise SystemExit(f"! expected exactly one AppImage .sig in {art}, found {sigs}")
    signature = sigs[0].read_text().strip()

    base = f"https://github.com/{REPO}/releases/download/{tag}"
    data = {
        "version": version,
        "pub_date": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "platforms": {
            "linux-x86_64": {
                "signature": signature,
                "url": f"{base}/Yoink_{version}_amd64.AppImage",
            },
        },
    }

    out = art / "latest.json"
    out.write_text(json.dumps(data, indent=2) + "\n")
    print(f"[OK] wrote {out} (version {version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
