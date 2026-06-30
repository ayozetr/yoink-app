#!/usr/bin/env python3
"""Build the release `.rpm` by converting the already-built `.deb` — fast.

Why this exists: Tauri's own rpm bundler (the `rpm` Rust crate) takes **10-12
minutes** to package the ~170 MB PyInstaller sidecar, while the `.deb` and
AppImage of the same payload bundle in *seconds*. It's not the compressor
(measured: the sidecar is incompressible, so even `xz -9` is ~45 s) — the cost is
inside the crate itself. So the release flow builds only `deb` + `appimage` with
Tauri (`--bundles deb,appimage`) and runs this to get the `.rpm` in seconds.

`alien` converts the `.deb` to `.rpm` via `rpmbuild`, whose automatic dependency
generator re-derives the **same soname Requires** Tauri's rpm declared
(`libwebkit2gtk-4.1.so.0()(64bit)`, `libgtk-3.so.0()(64bit)`, …) straight from
the ELF binaries — so the result is functionally equivalent and installs on any
rpm distro (Fedora/openSUSE/…), without hand-listing distro-specific package
names. Run under `fakeroot` so the packaged files stay root-owned.

    python scripts/build_rpm.py                 # newest deb for the current version
    python scripts/build_rpm.py --deb path.deb  # an explicit .deb

Requires `alien`, `rpmbuild` and (recommended) `fakeroot` on PATH. The rpm does
**not** affect self-update — the updater only uses the AppImage on Linux — so a
conversion change can never break auto-updates for existing users.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "src-tauri" / "target" / "release" / "bundle"
DEB_DIR = BUNDLE / "deb"
RPM_DIR = BUNDLE / "rpm"

# Install hints per distro family, shown when a tool is missing.
_HINTS = {
    "alien": "Arch: yay -S alien · Fedora: dnf install alien · Debian/Ubuntu: apt install alien",
    "rpmbuild": "Arch: pacman -S rpm-tools · Fedora: dnf install rpm-build · Debian/Ubuntu: apt install rpm",
    "fakeroot": "Arch: pacman -S fakeroot · Fedora: dnf install fakeroot · Debian/Ubuntu: apt install fakeroot",
}


def _app_version() -> str:
    data = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    return str(data["version"])


def _find_deb(version: str) -> Path | None:
    """The newest `.deb` for this version (so a stale older build isn't picked)."""
    matches = sorted(
        DEB_DIR.glob(f"Yoink_{version}_*.deb"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if matches:
        return matches[0]
    # Fall back to any deb, newest first, if the name doesn't match the pattern.
    any_deb = sorted(DEB_DIR.glob("*.deb"), key=lambda p: p.stat().st_mtime, reverse=True)
    return any_deb[0] if any_deb else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert the built .deb to .rpm (fast).")
    parser.add_argument("--deb", type=Path, help="Path to the .deb (default: newest for this version).")
    args = parser.parse_args()

    version = _app_version()
    deb = args.deb or _find_deb(version)
    if not deb or not deb.exists():
        print(f"! No .deb found in {DEB_DIR} — build it first (npm run tauri build --bundles deb,appimage).")
        return 1
    deb = deb.resolve()

    if not shutil.which("alien") or not shutil.which("rpmbuild"):
        print("! Missing conversion tools — need both `alien` and `rpmbuild`:")
        for tool in ("alien", "rpmbuild"):
            if not shutil.which(tool):
                print(f"    {tool}: {_HINTS[tool]}")
        return 1

    fakeroot = shutil.which("fakeroot")
    if not fakeroot:
        # Without fakeroot the packaged files would be owned by the build user
        # instead of root — installable but not clean. Warn, don't hard-fail.
        print(f"! `fakeroot` not found ({_HINTS['fakeroot']}) — files may not be root-owned.")

    RPM_DIR.mkdir(parents=True, exist_ok=True)
    # alien writes the .rpm into its working directory; use a temp one and move it.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cmd: list[str] = []
        if fakeroot:
            cmd.append(fakeroot)
        # -r/--to-rpm · --scripts keeps the maintainer scripts (desktop/icon cache
        # updates) · --keep-version stops alien bumping the release from -1 to -2.
        cmd += ["alien", "--to-rpm", "--scripts", "--keep-version", str(deb)]
        print(f"> Converting {deb.name} -> .rpm via alien ...")
        result = subprocess.run(cmd, cwd=tmp_path)
        if result.returncode != 0:
            print("! alien failed — see its output above.")
            return result.returncode

        produced = sorted(tmp_path.glob("*.rpm"))
        if not produced:
            print("! alien produced no .rpm.")
            return 1
        # Match the name the release docs/`gh release create` expect.
        target = RPM_DIR / f"Yoink-{version}-1.x86_64.rpm"
        shutil.move(str(produced[0]), target)
        print(f"> Wrote {target}")

    # Best-effort: show the dependencies so they can be eyeballed before publishing.
    if shutil.which("rpm"):
        print("\n> rpm -qp --requires (verify these resolve on the target distro):")
        subprocess.run(["rpm", "-qp", "--requires", str(target)])
    print(
        "\nVerify before publishing: install it on a Fedora box/container, e.g.\n"
        f"    podman run --rm -v {RPM_DIR}:/p:Z fedora bash -c 'dnf -y install /p/{target.name} && yoink --version || true'"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
