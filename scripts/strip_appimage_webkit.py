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
import datetime
import json
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPIMAGE_DIR = ROOT / "src-tauri" / "target" / "release" / "bundle" / "appimage"
METAINFO_SRC = ROOT / "src-tauri" / "metainfo" / "app.yoink.desktop.metainfo.xml"


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


def _png_width(path: Path) -> int:
    """The pixel width from a PNG's IHDR, or 0 if it isn't a readable PNG."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return 0
        return struct.unpack(">II", head[16:24])[0]
    except OSError:
        return 0


def _largest_icon(appdir: Path) -> Path | None:
    """The biggest real PNG icon in the AppDir (hicolor theme or AppDir root)."""
    candidates = [
        p
        for p in [*appdir.glob("usr/share/icons/hicolor/*/apps/*.png"), *appdir.glob("*.png")]
        if p.is_file() and not p.is_symlink()
    ]
    if not candidates:
        return None
    return max(candidates, key=_png_width)


def _desktop_file(appdir: Path) -> Path | None:
    files = sorted(appdir.glob("usr/share/applications/*.desktop"))
    return files[0] if files else None


def _normalize_appdir(appdir: Path, version: str) -> None:
    """Make the AppDir catalogue-grade before packaging.

    Tauri/linuxdeploy leave the AppDir usable but rough: `.DirIcon` is an
    *absolute* symlink into the build host (dangling everywhere else, so the
    appimage.github.io test reports ".DirIcon is missing"), the root icon that
    matches the .desktop `Icon=` points at the 32x32 copy, the .desktop has an
    empty `Categories`, and there is no AppStream metainfo. Fix all four so file
    managers, software centres and the AppImage catalogue get a real icon and
    proper metadata.
    """
    icon = _largest_icon(appdir)

    # 1. `.DirIcon` — a real PNG copy (never a symlink), at the best size we have.
    if icon:
        diricon = appdir / ".DirIcon"
        if diricon.is_symlink() or diricon.exists():
            diricon.unlink()
        shutil.copy2(icon, diricon)
        print(f"> .DirIcon -> real {_png_width(icon)}px PNG (was a dangling abs symlink)")

    desktop = _desktop_file(appdir)
    if desktop:
        text = desktop.read_text(encoding="utf-8")

        # 2. Root `<Icon>.png` matching the .desktop — a crisp copy, not the 32x32.
        m = re.search(r"^Icon=(.+)$", text, re.MULTILINE)
        if icon and m:
            root_icon = appdir / f"{m.group(1).strip()}.png"
            if root_icon.is_symlink() or root_icon.exists():
                root_icon.unlink()
            shutil.copy2(icon, root_icon)

        # 3. A non-empty Categories. One main category only (two would make the
        #    app show up twice in the menu — desktop-file-validate warns on it).
        if re.search(r"^Categories=\s*$", text, re.MULTILINE):
            text = re.sub(
                r"^Categories=.*$", "Categories=AudioVideo;", text, flags=re.MULTILINE
            )
            desktop.write_text(text, encoding="utf-8")
            print("> .desktop Categories set to AudioVideo;")

    # 4. AppStream metainfo (none is generated by Tauri).
    if METAINFO_SRC.exists():
        dest_dir = appdir / "usr" / "share" / "metainfo"
        dest_dir.mkdir(parents=True, exist_ok=True)
        xml = (
            METAINFO_SRC.read_text(encoding="utf-8")
            .replace("__VERSION__", version)
            .replace("__DATE__", datetime.date.today().isoformat())
        )
        (dest_dir / METAINFO_SRC.name).write_text(xml, encoding="utf-8")
        print(f"> AppStream metainfo -> usr/share/metainfo/{METAINFO_SRC.name}")


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

    # Fix the icon/.DirIcon/Categories and add AppStream metainfo so the result
    # is a proper, catalogue-grade AppImage.
    _normalize_appdir(appdir, _app_version())

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
