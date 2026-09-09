"""Flip `createUpdaterArtifacts` to false in a tauri.conf.json copy.

Used on the Windows build VM: the updater signing key must never leave the local
machine, so the VM builds the installers **unsigned** (they're signed here
afterwards with `tauri signer sign`). See docs/releasing.md.

    python scripts/disable_updater.py src-tauri/tauri.conf.json

Whitespace-tolerant, and it *fails loudly* when the key is missing entirely —
a silent "nothing changed" here would let the VM emit updater artifacts that are
only supposed to be produced (and signed) on the trusted host.
"""

from __future__ import annotations

import re
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    text = fh.read()

pattern = re.compile(r'("createUpdaterArtifacts"\s*:\s*)true')
new_text, count = pattern.subn(r"\1false", text)

if count:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    print("updater artifacts disabled")
elif re.search(r'"createUpdaterArtifacts"\s*:\s*false', text):
    print("already off")
else:
    sys.exit(f"error: createUpdaterArtifacts not found in {path}")
