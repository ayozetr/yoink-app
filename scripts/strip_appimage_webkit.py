#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Strip the bundled WebKitGTK from the built AppImage so it uses the system's.

    python scripts/strip_appimage_webkit.py        # newest AppImage for this version
    python scripts/strip_appimage_webkit.py --appdir path/to/Yoink.AppDir

**Why this exists.** `linuxdeploy-plugin-gtk` bundles `libwebkit2gtk-4.1.so.0` and
`libjavascriptcoregtk-4.1.so.0` into the AppImage. But WebKitGTK launches helper
processes (`WebKitNetworkProcess` / `WebKitWebProcess`) from a path baked in at
compile time — `/usr/lib/webkit2gtk-4.1/` on the *host*. So the app loads the
bundled library yet spawns the host's helpers; the moment the host's
`webkit2gtk-4.1` is upgraded to a different version (routine on a rolling distro
like Arch/CachyOS), the two no longer match and the window renders **blank/grey**.

WebKit is on AppImage's de-facto exclude list for exactly this reason: it must
come from the system, not be bundled. So after `tauri build`, we delete the
WebKit/JSC libraries (and the helper-process dirs) from the AppDir and repackage,
leaving the AppImage to resolve WebKit from the host — where the library and its
helpers always match. The `.deb`/`.rpm` already depend on `webkit2gtk-4.1`, so
requiring it for the AppImage too is consistent (it's a near-ubiquitous GTK dep).

The repackaged AppImage is **unsigned** (appimagetool re-embeds it), so the
release flow must re-run `tauri signer sign` on the result and rebuild
`latest.json` from the new signature — see docs/releasing.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPIMAGE_DIR = ROOT / "src-tauri" / "target" / "release" / "bundle" / "appimage"


def _app_version() -> str:
    return str(json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"])

# Relative-to-AppDir paths to remove: the WebKit/JSC shared libraries plus the
# helper-process directories (under both lib and lib64). Everything WebKit then
# resolves from the host, so library and helpers are always the same version.
_REMOVE = [
    "usr/lib/libwebkit2gtk-4.1.so.0",
    "usr/lib/libjavascriptcoregtk-4.1.so.0",
    "usr/lib/webkit2gtk-4.1",
    "usr/lib64/libwebkit2gtk-4.1.so.0",
    "usr/lib64/libjavascriptcoregtk-4.1.so.0",
    "usr/lib64/webkit2gtk-4.1",
]


def _find_appdir() -> Path | None:
    appdirs = sorted(APPIMAGE_DIR.glob("*.AppDir"))
    return appdirs[0] if appdirs else None


def _find_appimagetool() -> Path | None:
    """The appimagetool packaged with Tauri's downloaded plugins, else on PATH."""
    cache = Path.home() / ".cache" / "tauri"
    hits = sorted(cache.glob("linuxdeploy-plugin-appimage*.AppImage"))
    if hits:
        return hits[0]
    which = shutil.which("appimagetool")
    return Path(which) if which else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Strip bundled WebKitGTK from the AppImage.")
    parser.add_argument("--appdir", type=Path, help="AppDir to repackage (default: the built one).")
    args = parser.parse_args()

    appdir = args.appdir or _find_appdir()
    if not appdir or not appdir.is_dir():
        print(f"! No AppDir found in {APPIMAGE_DIR} — run `tauri build` first.")
        return 1

    tool = _find_appimagetool()
    if not tool:
        print(
            "! appimagetool not found. Tauri downloads it to ~/.cache/tauri/ during a "
            "`tauri build --bundles appimage`; run that once, or install appimagetool."
        )
        return 1

    # Remove the bundled WebKit/JSC so the host's is used (versions always match).
    removed = []
    for rel in _REMOVE:
        target = appdir / rel
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(rel)
        elif target.exists() or target.is_symlink():
            target.unlink()
            removed.append(rel)
    if not removed:
        print("! Nothing to strip — the AppDir has no bundled WebKit/JSC (already stripped?).")
        # Not fatal: still repackage so the output is consistent.
    else:
        print("> Removed from the AppDir:")
        for rel in removed:
            print(f"    {rel}")

    # Repackage. The output name mirrors Tauri's (Yoink_<ver>_amd64.AppImage), so
    # the signed result lands exactly where the release flow expects it (the AppDir
    # itself is just "Yoink.AppDir", so the version comes from package.json).
    output = APPIMAGE_DIR / f"{appdir.stem}_{_app_version()}_amd64.AppImage"
    env = {**os.environ, "APPIMAGE_EXTRACT_AND_RUN": "1", "OUTPUT": output.name}
    print(f"> Repackaging {appdir.name} -> {output.name} (WebKit from the system) ...")
    result = subprocess.run(
        [str(tool), "--appdir", str(appdir)],
        cwd=str(APPIMAGE_DIR),
        env=env,
    )
    if result.returncode != 0 or not output.exists():
        print("! appimagetool failed to repackage the AppDir.")
        return result.returncode or 1

    # The old updater signature no longer matches the repackaged file.
    sig = output.with_suffix(output.suffix + ".sig")
    if sig.exists():
        sig.unlink()
    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"> Wrote {output.name} ({size_mb:.0f} MB).")
    print(
        "  NOTE: this AppImage is unsigned — re-run `tauri signer sign` on it and "
        "rebuild latest.json from the new .sig before publishing (see docs/releasing.md)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
