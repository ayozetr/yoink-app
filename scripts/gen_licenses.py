#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Regenerate docs/DEPENDENCIES.md from Yoink's *direct* dependencies.

Lists only the dependencies Yoink declares and uses directly (not the full
transitive tree), across the three Rust crates it ships:

  * `desktop`        — the native egui desktop app
  * `backend-rs`     — the native backend (yoink-core)
  * `desktop-minter` — the PO-token minter

plus the bundled media tools (ffmpeg / yt-dlp). The result is embedded by the
desktop app (`desktop/src/app.rs`, `include_str!`) and shown under Settings.

Run from the repo root:  python scripts/gen_licenses.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Yoink ships a Linux AppImage; direct deps resolve the same across targets.
CARGO_TARGET = "x86_64-unknown-linux-gnu"
# The Rust crates whose direct deps are attributed.
CARGO_CRATES = [
    ("desktop", "yoink-desktop"),
    ("backend-rs", "yoink-core"),
    ("desktop-minter", "yoink-minter"),
]


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a command and return stdout, or exit with a clear message on failure."""
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        sys.exit(f"gen_licenses: `{' '.join(cmd)}` failed: {exc}")
    return out.stdout


def _cargo() -> list[tuple[str, str]]:
    """Direct (normal) Rust dependencies of each shipped crate, with licenses."""
    result: dict[tuple[str, str], bool] = {}
    for crate_dir, crate_name in CARGO_CRATES:
        data = json.loads(
            _run(
                ["cargo", "metadata", "--format-version", "1", "--filter-platform", CARGO_TARGET],
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
    cargo = _cargo()
    out: list[str] = [
        "# Open-source licenses\n",
        "Yoink is built on open-source software. Listed below are Yoink's direct\n"
        "dependencies and their licenses — the libraries it uses directly; each in turn\n"
        "pulls in further open-source libraries under the same permissive licenses.\n",
        "## Bundled media tools\n",
        "- **ffmpeg / ffprobe** — LGPL v3 (built minimal; see THIRD_PARTY_NOTICES.md)",
        "- **yt-dlp** — The Unlicense (public domain) — the download engine\n",
        f"## Rust / cargo ({len(cargo)})\n",
        *[f"- **{n}** — {l}" for n, l in cargo],
        "",
    ]
    dest = ROOT / "docs" / "DEPENDENCIES.md"
    dest.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {dest} (cargo {len(cargo)})")


if __name__ == "__main__":
    main()
