#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Regenerate OPEN_SOURCE_LICENSES.md from Yoink's *direct* dependencies.

Lists only the dependencies Yoink declares and uses directly (not the full
transitive tree, which for a Tauri app is hundreds of crates), across the three
ecosystems:

  * Frontend  — npm         (`package.json` dependencies)
  * Desktop   — Rust        (`src-tauri/Cargo.toml`, resolved for the desktop target)
  * Backend & desktop — Rust (`backend-rs` + `src-tauri`, via cargo metadata)

plus the bundled media tools (ffmpeg / yt-dlp). The result is imported `?raw` by
`src/features/settings/LicensesModal.tsx` and shown under Settings > About.

Run from the repo root:  python scripts/gen_licenses.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The desktop targets Yoink actually ships; direct deps resolve the same on both.
CARGO_TARGETS = ["x86_64-unknown-linux-gnu", "x86_64-pc-windows-msvc"]
# The two Rust crates whose direct deps are attributed: the Tauri desktop shell
# and the native backend.
CARGO_CRATES = [("src-tauri", "yoink"), ("backend-rs", "yoink-core")]


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a command and return stdout, or exit with a clear message on failure."""
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        sys.exit(f"gen_licenses: `{' '.join(cmd)}` failed: {exc}")
    return out.stdout


def _npm() -> list[tuple[str, str, str]]:
    """Direct npm dependencies (package.json `dependencies`), with their licenses."""
    direct = set(json.loads((ROOT / "package.json").read_text())["dependencies"])
    data = json.loads(
        _run(["npx", "--yes", "license-checker", "--production", "--json"], ROOT)
    )
    by_name: dict[str, tuple[str, str]] = {}
    for key, meta in data.items():
        name, _, ver = key.rpartition("@")
        if name in direct and name not in by_name:
            lic = meta.get("licenses", "?")
            if isinstance(lic, list):
                lic = " / ".join(lic)
            by_name[name] = (ver, lic)
    return sorted(((n, v, l) for n, (v, l) in by_name.items()), key=lambda r: r[0].lower())


def _cargo() -> list[tuple[str, str]]:
    """Direct Rust dependencies of the desktop shell (`yoink`) and the native
    backend (`yoink-core`), their normal deps only."""
    result: dict[tuple[str, str], bool] = {}
    for crate_dir, crate_name in CARGO_CRATES:
      for triple in CARGO_TARGETS:
        data = json.loads(
            _run(
                ["cargo", "metadata", "--format-version", "1", "--filter-platform", triple],
                ROOT / crate_dir,
            )
        )
        pkgs = {p["id"]: p for p in data["packages"]}
        nodes = {n["id"]: n for n in data["resolve"]["nodes"]}
        root = data["resolve"].get("root") or next(
            i for i, p in pkgs.items() if p["name"] == crate_name
        )
        for dep in nodes[root]["deps"]:
            if not any(dk.get("kind") is None for dk in dep.get("dep_kinds", [])):
                continue  # skip dev/build-only direct deps
            pkg = pkgs.get(dep["pkg"])
            if not pkg:
                continue
            lic = pkg.get("license") or (
                f"file: {pkg['license_file']}" if pkg.get("license_file") else "?"
            )
            result[(pkg["name"], lic)] = True
    return sorted(result, key=lambda r: r[0].lower())




def main() -> None:
    npm, cargo = _npm(), _cargo()
    out: list[str] = [
        "# Open-source licenses\n",
        "Yoink is built on open-source software. Listed below are Yoink's direct\n"
        "dependencies and their licenses — the libraries it uses directly; each in turn\n"
        "pulls in further open-source libraries under the same permissive licenses.\n",
        "## Bundled media tools\n",
        "- **ffmpeg / ffprobe** — LGPL v3 (built minimal; see THIRD_PARTY_LICENSES.md)",
        "- **yt-dlp** — The Unlicense (public domain) — the download engine\n",
        f"## Frontend — npm ({len(npm)})\n",
        *[f"- **{n}** {('v' + v) if v else ''} — {l}" for n, v, l in npm],
        "",
        f"## Backend & desktop — Rust / cargo ({len(cargo)})\n",
        *[f"- **{n}** — {l}" for n, l in cargo],
        "",
    ]
    dest = ROOT / "OPEN_SOURCE_LICENSES.md"
    dest.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {dest} (npm {len(npm)}, cargo {len(cargo)})")


if __name__ == "__main__":
    main()
