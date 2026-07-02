#!/usr/bin/env python3
"""Build the release `.rpm` by repackaging the built `.deb` with rpmbuild — fast.

Why this exists: Tauri's own rpm bundler (the `rpm` Rust crate) takes **10-12
minutes** to package the ~170 MB PyInstaller sidecar, while the `.deb` and
AppImage of the same payload bundle in *seconds*. It's not the compressor
(measured: the sidecar is incompressible, so even `xz -9` is ~45 s, and
SHA256/cpio are <1 s) — the cost is inside the crate itself. So the release flow
builds only `deb` + `appimage` with Tauri (`--bundles deb,appimage`) and runs
this to get the `.rpm` in seconds.

It unpacks the `.deb` file tree and repackages it with **rpmbuild**, whose
automatic dependency generator re-derives the **same soname Requires** Tauri's
rpm declared (`libwebkit2gtk-4.1.so.0()(64bit)`, `libgtk-3.so.0()(64bit)`)
straight from the ELF binaries — so the result is functionally identical and
installs on any rpm distro (Fedora/openSUSE/…), without hand-listing
distro-specific package names.

    python scripts/build_rpm.py                 # newest deb for the current version
    python scripts/build_rpm.py --deb path.deb  # an explicit .deb

Requires `rpmbuild` (the `rpm`/`rpm-tools` package) and `fakeroot` on PATH — no
AUR/`alien` needed. The rpm plays **no part in self-update** (the updater only
uses the AppImage on Linux), so a change here can never break auto-updates for
existing users.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "src-tauri" / "target" / "release" / "bundle"
DEB_DIR = BUNDLE / "deb"
RPM_DIR = BUNDLE / "rpm"

# Metadata to match Tauri's own rpm (checked with `rpm -qp --info`).
SUMMARY = "Yoink — local high-fidelity media downloader"
LICENSE = "CC-BY-NC-SA-4.0"

_HINTS = {
    "rpmbuild": "Arch/CachyOS: pacman -S rpm-tools · Fedora: dnf install rpm-build · Debian/Ubuntu: apt install rpm",
    "fakeroot": "Arch/CachyOS: pacman -S fakeroot · Fedora: dnf install fakeroot · Debian/Ubuntu: apt install fakeroot",
}

_SPEC = """\
Name: yoink
Version: {version}
Release: 1
Summary: {summary}
License: {license}
BuildArch: x86_64

# Autoreq (on by default) scans the ELF binaries and emits the soname Requires
# (libwebkit2gtk-4.1.so.0, libgtk-3.so.0), matching Tauri's rpm exactly — no
# hand-listed, distro-specific package names.

%description
{summary}

%install
mkdir -p %{{buildroot}}
cp -a {tree}/. %{{buildroot}}/
# rpmbuild runs under fakeroot, so this records root ownership in the package
# regardless of who unpacked the tree.
chown -R root:root %{{buildroot}}

%files
{files}
"""


def _app_version() -> str:
    return str(json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"])


def _find_deb(version: str) -> Path | None:
    matches = sorted(DEB_DIR.glob(f"Yoink_{version}_*.deb"), key=lambda p: p.stat().st_mtime, reverse=True)
    if matches:
        return matches[0]
    any_deb = sorted(DEB_DIR.glob("*.deb"), key=lambda p: p.stat().st_mtime, reverse=True)
    return any_deb[0] if any_deb else None


def _extract_deb(deb: Path, dest: Path) -> Path:
    """Unpack the .deb (an `ar` archive) and its data tarball into ``dest/tree``."""
    subprocess.run(["ar", "x", str(deb)], cwd=dest, check=True)
    data = next(dest.glob("data.tar*"))
    tree = dest / "tree"
    tree.mkdir()
    with tarfile.open(data) as tar:
        tar.extractall(tree, filter="data")  # filter: py3.12+ safe extraction
    return tree


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert the built .deb to .rpm (fast, via rpmbuild).")
    parser.add_argument("--deb", type=Path, help="Path to the .deb (default: newest for this version).")
    args = parser.parse_args()

    version = _app_version()
    deb = (args.deb or _find_deb(version))
    if not deb or not deb.exists():
        print(f"! No .deb found in {DEB_DIR} — build it first (npx tauri build --bundles deb,appimage).")
        return 1
    deb = deb.resolve()

    missing = [t for t in ("rpmbuild", "fakeroot", "ar") if not shutil.which(t)]
    if missing:
        print("! Missing tools:")
        for tool in missing:
            print(f"    {tool}: {_HINTS.get(tool, 'install it and retry')}")
        return 1

    RPM_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tree = _extract_deb(deb, tmp_path)
        files = sorted("/" + p.relative_to(tree).as_posix() for p in tree.rglob("*") if p.is_file())
        if not files:
            print("! The .deb contained no files.")
            return 1
        # Quote every %files path: the onedir backend bundles files with spaces in
        # their name (e.g. setuptools' "Lorem ipsum.txt"), which rpmbuild would
        # otherwise split on and reject ("must start with /").
        files_spec = "\n".join(f'"{f}"' for f in files)

        topdir = tmp_path / "rpmbuild"
        out = tmp_path / "out"
        out.mkdir()
        spec = tmp_path / "yoink.spec"
        spec.write_text(
            _SPEC.format(version=version, summary=SUMMARY, license=LICENSE, tree=tree, files=files_spec),
            encoding="utf-8",
        )

        print(f"> Repackaging {deb.name} -> .rpm via rpmbuild ...")
        result = subprocess.run(
            [
                "fakeroot", "rpmbuild", "-bb",
                "--define", f"_topdir {topdir}",
                "--define", f"_rpmdir {out}",
                "--define", "debug_package %{nil}",   # no -debuginfo subpackage
                "--define", "_build_id_links none",    # no /usr/lib/.build-id/ entries (match Tauri)
                str(spec),
            ],
        )
        if result.returncode != 0:
            print("! rpmbuild failed — see its output above.")
            return result.returncode

        produced = sorted(out.rglob("*.rpm"))
        if not produced:
            print("! rpmbuild produced no .rpm.")
            return 1
        target = RPM_DIR / f"Yoink-{version}-1.x86_64.rpm"
        shutil.move(str(produced[0]), target)
        print(f"> Wrote {target}")

    print("\n> rpm -qp --requires (should list the webkit/gtk sonames):")
    subprocess.run(["rpm", "-qp", "--requires", str(target)])
    print(
        "\nVerify on a real rpm distro before publishing, e.g.\n"
        f"    podman run --rm -v {RPM_DIR}:/p:Z fedora dnf -y install /p/{target.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
