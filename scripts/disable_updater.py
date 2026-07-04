"""Flip `createUpdaterArtifacts` to false in a tauri.conf.json copy.

Used on the Windows build VM: the updater signing key must never leave the local
machine, so the VM builds the installers **unsigned** (they're signed here
afterwards with `tauri signer sign`). See docs/releasing.md.

    python scripts/disable_updater.py src-tauri/tauri.conf.json
"""

from __future__ import annotations

import sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
needle = '"createUpdaterArtifacts": true'
if needle in text:
    open(path, "w", encoding="utf-8").write(
        text.replace(needle, '"createUpdaterArtifacts": false')
    )
    print("updater artifacts disabled")
else:
    print("already off")
