# Releasing

Yoink ships as a signed Linux **AppImage** that self-updates in place. Releases
are built by GitHub Actions (`.github/workflows/release.yml`). A Windows build is
being ported.

## Cut a release

1. **Bump the version** in `desktop/Cargo.toml`, `backend-rs/Cargo.toml` and
   `desktop-minter/Cargo.toml` (keep them in sync). The updater manifest reads the
   version from `desktop/Cargo.toml` (`make_latest_json_egui.py`).
2. **Tag and push:** `git tag v<ver> && git push origin v<ver>`.
3. CI builds + signs the AppImage and **drafts** the release with `latest.json`.
4. **Edit the draft's notes** (keep the hidden `<!-- /whatsnew -->` marker before
   the Downloads section — the "What's new" popup trims to the part before it) and
   **publish**. Publishing makes `latest.json` live for the in-app updater and for
   the legacy→egui migration.

Running the workflow manually (`workflow_dispatch`) builds the AppImage and
uploads it as an artifact without drafting a release.

## What the build does

`scripts/build_egui_appimage.sh` (run by the workflow):

1. `cargo build --release` the egui app, and `scripts/build_core.py` builds
   `yoink-core`, fetches the pinned standalone `yt-dlp` (version in
   `scripts/ytdlp-version.txt`) and copies the minimal `ffmpeg`/`ffprobe` from
   `backend/vendor/ffmpeg/` (built once by `scripts/build_ffmpeg.sh`) into
   `desktop/target/core/`.
2. Lays out an AppDir with `yoink-desktop` and those four binaries beside it
   (`backend_proc.rs` finds `yoink-core` + yt-dlp/ffmpeg as siblings), plus the
   `.desktop` entry and icon.
3. `linuxdeploy` (+ the GTK plugin) bundles the runtime libraries and
   `appimagetool` packs `Yoink_<ver>_amd64.AppImage`. No WebKit — far smaller than
   the old Tauri bundle (~100 MB vs ~210 MB).

## Signing & the updater

The AppImage is signed with **minisign** (`cargo tauri signer sign`, which reads
the key from the `TAURI_SIGNING_PRIVATE_KEY` + `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`
repo secrets — the **same key** the legacy app used). `make_latest_json_egui.py`
puts the signature (inline, base64) and the download URL into `latest.json`.

The egui updater (`desktop/src/api.rs`) reads `latest.json`, downloads the
AppImage (https + GitHub host pinned), and **verifies the minisign signature
against the embedded public key** (`UPDATE_PUBKEY`) before replacing `$APPIMAGE`
and relaunching — fail-closed, so a tampered or wrong-host download never runs.
Because it's the same key the legacy Tauri app embedded, that one signed AppImage
is also accepted by the legacy app's own updater (reading the same `latest.json`),
which is how existing users migrate to the egui build; from then on the egui app
updates itself.

## Troubleshooting

- **AppImage won't start on another machine:** a system library wasn't bundled.
  Confirm the GitHub runner installed `libgtk-3-dev`,
  `libayatana-appindicator3-dev`, `libxdo-dev` and that the GTK plugin ran. Build
  on the oldest supported runner (`ubuntu-22.04`) for glibc compatibility.
- **Update rejected ("signature verification failed"):** the AppImage was signed
  with a different key than `UPDATE_PUBKEY`, or re-compressed after signing. Sign
  the final AppImage and don't modify it afterwards.
- **`cargo tauri signer sign` not found:** the workflow installs `tauri-cli` via
  `taiki-e/install-action`; locally, `cargo install tauri-cli`.
