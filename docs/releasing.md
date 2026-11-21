# Releasing Yoink

How a new versioned release is cut and published. The **recommended** path is
GitHub Actions (see [§0](#0-releasing-via-github-actions-recommended)) — it
builds and signs every bundle on hosted Linux + Windows runners, so no local
build host or Windows VM is needed. The manual local flow (§1 onward) still
works and documents exactly what the workflow does. Each release ships three
Linux bundles: `.AppImage`,
`.deb` and `.rpm`, each with the native Rust backend (`yoink-core`) plus the
bundled `yt-dlp` and a minimal `ffmpeg` as a Tauri *resource* launched by
`main.rs`, so users need no Python, yt-dlp or ffmpeg.

## 0. Releasing via GitHub Actions (recommended)

`.github/workflows/release.yml` builds and **signs** all five bundles on hosted
runners (`ubuntu-latest` + `windows-latest`), then drafts the GitHub release with
`latest.json` attached — replacing the local build host and the Windows VM.

Steps:

1. **Bump the five version files** and refresh the licenses + release notes
   locally (§1, §1b) and commit — the workflow builds whatever the tag points at,
   it does **not** bump for you. `make_latest_json.py` fails the run if the tag and
   `package.json` disagree, so a stray version is caught before publishing.
2. **Tag and push:**
   ```bash
   git tag -a v<ver> -m "Yoink v<ver>"
   git push origin v<ver>
   ```
3. The **Release** workflow runs (watch it with `gh run watch`): it builds
   yoink-core, bundles deb+AppImage (stripping the bundled WebKit and
   re-signing the AppImage) and the rpm on Linux, the msi+NSIS installers on
   Windows, assembles `latest.json`, and creates a **draft** GitHub release with
   the installers + `latest.json` attached (not the `.sig` files).
4. **Edit the draft's notes** (keep the hidden `<!-- /whatsnew -->` marker before
   the Downloads table — see §5) and **Publish**. Publishing makes it
   `releases/latest`, so `latest.json` goes live for the in-app updater.

A manual `workflow_dispatch` run (Actions tab → *Release* → *Run workflow*) builds
and uploads the bundles as run artifacts **without** creating a release — handy to
test the pipeline on a branch.

**Signing in CI.** The updater key lives in two repo secrets, never in the repo:
`TAURI_SIGNING_PRIVATE_KEY` (the contents of `~/.tauri/yoink.key`) and
`TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. Set/rotate them with
`gh secret set TAURI_SIGNING_PRIVATE_KEY < ~/.tauri/yoink.key` (gh encrypts the
value client-side). The signing job runs only on a `v*` tag push or a manual
dispatch; fork pull requests never run it and GitHub never hands them the secrets.
The workflow uses only first-party `actions/*` actions plus the runner's
preinstalled toolchain — no third-party action can read the secrets.

> Prefer to keep the key off CI entirely? Flip the two `tauri build` steps to
> build **unsigned** (set `createUpdaterArtifacts:false` in `tauri.conf.json`,
> drop the signing env + the AppImage re-sign step),
> download the run artifacts, and sign locally with `tauri signer sign` as in §6.

---

Prerequisites on the build host (for the **manual local** flow, §1 onward):

- **Rust toolchain** (the backend and the Tauri shell are both Rust), and on
  Linux `webkit2gtk` (4.1).
- **Python 3** (only to run the build scripts — `build_core.py` etc.; the app
  ships no Python).
- For the **minimal ffmpeg** build (`scripts/build_ffmpeg.sh`): `gcc`, `make`,
  `cmake`, `curl`, `pkg-config`; optionally `nasm` for SIMD. For the Windows
  cross build (`--windows`): the `mingw-w64` toolchain. See
  [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) for the attribution.
- For the `.rpm` (built by repackaging the `.deb` — see §3b): **`rpmbuild`** and
  **`fakeroot`** on PATH. Arch/CachyOS: `pacman -S rpm-tools fakeroot`; Fedora:
  `dnf install rpm-build fakeroot`; Debian/Ubuntu: `apt install rpm fakeroot`.

## 1. Bump the version

The version string lives in **five** places — all must match:

| File | Field |
| ---- | ----- |
| `package.json` | `"version"` |
| `src-tauri/tauri.conf.json` | `"version"` |
| `src-tauri/Cargo.toml` | `[package] version` |
| `src-tauri/Cargo.lock` | the `yoink` package entry |
| `backend-rs/Cargo.toml` | `[package] version` (the backend's `/api/version`) |

The frontend's in-app version badge reads `__APP_VERSION__`, which Vite injects
from `package.json` at build time — no separate edit needed. Grep the previous
number across these files before building to catch a stray one.

Commit the bump together with any docs/README/icon updates.

### 1b. Refresh the open-source licenses

`OPEN_SOURCE_LICENSES.md` (repo root) is the list shown under **Settings › About →
Open-source licenses**. It is **inlined into the frontend bundle at build time** (a
Vite `?raw` import in `LicensesModal.tsx`) — the app never fetches it at runtime, so
whatever is in the file when you run the build is what ships. Regenerate it so the
listed versions match this release, with deps in sync with the lockfiles:

```bash
python scripts/gen_licenses.py   # reads node_modules/ + `cargo metadata`
```

It reports **installed** versions, so run it *after* any `npm install` / `cargo update`
/ `pip install -U`. Commit the result; the frontend build (§3, via `npm run build`)
bakes it into the bundle.

## 2. Build the backend bundle

Whenever the backend changed since the last release, rebuild it so the bundles
ship the new code:

```bash
bash scripts/build_ffmpeg.sh    # once per platform — build minimal ffmpeg+ffprobe
#   (Windows: build_ffmpeg.sh --windows cross-compiles the .exe on Linux via mingw-w64)
python scripts/build_core.py
```

`build_core.py` runs `cargo build --release` on `backend-rs`, then assembles
`src-tauri/binaries/core/` with the three binaries the app needs:

- `yoink-core` — the native Rust backend (axum).
- `yt-dlp` — the official standalone binary, pinned in `scripts/ytdlp-version.txt`
  and downloaded for the target platform.
- `ffmpeg` + `ffprobe` — the minimal self-contained build from
  `backend/vendor/ffmpeg/` (see [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)).

`tauri.conf.json` bundles that folder as the `core` `resources` entry.
`src-tauri/src/main.rs` launches `yoink-core` directly (`std::process`), passing
the port via `YOINK_PORT` and setting `YOINK_YTDLP`/`YOINK_FFMPEG` to the sibling
binaries, with a stdin pipe as a shutdown watchdog; it kills the process group
(and any ffmpeg grandchild) on exit. The packaged backend listens on **8756**
(matching the frontend's default `VITE_API_BASE_URL`).

Because `yoink-core` is a single native binary (no Python runtime), there is no
PyInstaller step and none of its former gotchas (the `curl_cffi` collection or
the Linux executable-stack `libpython` fix).

## 3. Build the bundles

Build **only** the `.deb` + AppImage with Tauri, then make the `.rpm` from the
`.deb` (see below) — **do not** let Tauri bundle the rpm:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 NO_STRIP=1 \
  npx tauri build --bundles deb,appimage
```

> **Why skip Tauri's rpm.** Tauri's rpm bundler (the `rpm` Rust crate) has historically been
> **much slower** to package the bundled binaries (yt-dlp + ffmpeg) than the
> `.deb`/AppImage of the same payload, which bundle in *seconds*.
> So we build deb+appimage here and convert the deb to rpm in §3b (seconds).
> The rpm plays **no part in self-update** (the updater only uses the AppImage on
> Linux — see §6), so this can't affect existing users' auto-updates.

The `.deb` packager practically never fails. The **AppImage** step
(`linuxdeploy`) is the fragile one — see troubleshooting below.
`APPIMAGE_EXTRACT_AND_RUN=1` is what makes it work on hosts without FUSE.

The Wayland blank-screen fix is **in the binary** (`src-tauri/src/main.rs`
forces `WEBKIT_DISABLE_DMABUF_RENDERER=1` before any webview code runs), so it
is present in all bundles automatically — nothing to set per-package or
at runtime.

### 3a. Strip the bundled WebKit from the AppImage (required)

```bash
python scripts/strip_appimage_webkit.py
```

`linuxdeploy` bundles `libwebkit2gtk-4.1.so.0` + `libjavascriptcoregtk-4.1.so.0`
into the AppImage, but WebKit spawns its helper processes
(`WebKitNetworkProcess`/`WebKitWebProcess`) from a compile-time path on the
**host** (`/usr/lib/webkit2gtk-4.1/`). So the app loads the *bundled* library yet
runs the *host's* helpers; the moment the host upgrades `webkit2gtk-4.1` (routine
on a rolling distro — Arch/CachyOS), the versions diverge and the window renders
**blank/grey**. This script deletes the WebKit/JSC libraries (and helper dirs)
from the AppDir and repackages, so the AppImage uses the host's WebKit, where the
library and its helpers always match (the `.deb`/`.rpm` already depend on
`webkit2gtk-4.1`, so this is consistent). Run it **after** `tauri build` and
**before** signing — it repackages the AppImage, which invalidates the `.sig`
Tauri emitted (the script removes that stale `.sig`), so the AppImage must be
re-signed with `tauri signer sign` in [§6](#6-signed-updater-artifacts-self-update).

The same script also **normalises the AppDir** before repackaging, so the result
is catalogue-grade (the [appimage.github.io](https://appimage.github.io) test
rejected v4.3.0 for a dangling `.DirIcon`): it replaces `.DirIcon` and the root
`Icon=` PNG with a real 256×256 image (Tauri/linuxdeploy leave `.DirIcon` an
absolute symlink into the build host, and the root icon pointing at the 32×32
copy), sets a single `Categories=AudioVideo;`, and installs the AppStream
metainfo from `src-tauri/metainfo/app.yoink.desktop.metainfo.xml` (its
`__VERSION__`/`__DATE__` are filled from the build). After a release lands, comment
`/retest` on the catalogue PR.

### 3b. Make the `.rpm` from the `.deb` (seconds, not minutes)

```bash
python scripts/build_rpm.py
```

This unpacks the freshly-built `.deb` and repackages the file tree with
`rpmbuild` (run under `fakeroot` for root-owned files), whose automatic
dependency generator re-derives the **soname `Requires`** from the ELF binaries
(`libwebkit2gtk-4.1.so.0()(64bit)`, `libgtk-3.so.0()(64bit)`, …) — so the result
installs on any rpm distro without hand-listing distro-specific package names.
It writes `src-tauri/target/release/bundle/rpm/Yoink-<ver>-1.x86_64.rpm` in **~40
seconds** (vs Tauri's 10–12 min). Verified: installs cleanly in a Fedora
container, pulling `gtk3` + `webkit2gtk4.1`.

> **Re-verify after a big packaging change**: `rpm -qp --requires <rpm>` should
> list the webkit/gtk sonames, `rpm -qp --list` the six files, and a clean
> install should pull the deps:
> `docker run --rm -v <rpm-dir>:/p:ro fedora dnf -y install /p/<file>.rpm`.
> *Fallback if `rpmbuild` is ever unavailable:* let Tauri grind the rpm with
> `npx tauri build --bundles rpm` (slow), as earlier releases did.

Output paths:

```
src-tauri/target/release/bundle/appimage/Yoink_<ver>_amd64.AppImage
src-tauri/target/release/bundle/deb/Yoink_<ver>_amd64.deb
src-tauri/target/release/bundle/rpm/Yoink-<ver>-1.x86_64.rpm   # from §3b
```

### 3c. Browser extension — NOT an app-release asset

The **"Send to Yoink" browser extension** (`extension/`) ships on its **own channels**,
**decoupled** from app releases — you do **not** re-attach it to every Yoink release:

- **Stores** — Firefox AMO / Chrome Web Store (`./build.sh publish-firefox`, etc.).
- **Manual install** — the rolling **`ext-latest`** GitHub *pre-release* with stable,
  version-less `.zip` URLs, refreshed only when the extension changes:
  ```bash
  cd extension && ./build.sh publish-manual && cd ..   # gh release upload ext-latest … --clobber
  ```

`ext-latest` is a **pre-release on purpose** so it stays out of `releases/latest` and
can't shadow the app's updater. The app's **Settings ▸ Extension** tab links to it. Full
flow + first-time setup: [`extension/README.md`](../extension/README.md). *(v3.0.0
shipped the extension zips as app-release assets for the launch; from then on it's the
`ext-latest` channel.)*

## 4. Smoke-test

```bash
./src-tauri/target/release/bundle/appimage/Yoink_<ver>_amd64.AppImage &
# the window should open; pasting a URL + Analizar should hit the bundled
# backend on :8756. (ffmpeg is bundled — no system install needed.)
```

> **Verify the backend launch, especially on Windows.** `yoink-core` is spawned
> by `main.rs`, so the launch path is exercised here — confirm it answers on
> :8756 and that closing the app leaves **no** orphan `yoink-core` (nothing
> holding the port). The **Windows** build must be smoke-tested the same way
> before publishing, since the resource path + process spawn can't be checked
> from Linux. (Auto-update is unaffected either way — the updater
> replaces the whole AppImage/installer and doesn't care what's inside.)

Quick structural check (no GUI needed) — confirm the backend folder is inside:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 ./...AppImage --appimage-extract
ls squashfs-root/usr/bin                       # expect: yoink
ls squashfs-root/usr/lib/Yoink/core             # expect: yoink-core  yt-dlp  ffmpeg  ffprobe
rm -rf squashfs-root
```

## 5. Tag and publish

```bash
git tag -a v<ver> -m "Yoink v<ver>"
git push origin v<ver>
gh release create v<ver> \
  "src-tauri/target/release/bundle/appimage/Yoink_<ver>_amd64.AppImage" \
  "src-tauri/target/release/bundle/deb/Yoink_<ver>_amd64.deb" \
  "src-tauri/target/release/bundle/rpm/Yoink-<ver>-1.x86_64.rpm" \
  --title "Yoink v<ver>" --notes "<release notes>"
```

The browser extension is **not** an asset here — it lives on its own channel
(`ext-latest` + the stores; see §3c). Update it with `./build.sh publish-manual` only
when the extension itself changes.

Verify with `gh release view v<ver> --json assets`.

> **Release-notes format for the in-app "What's new" popup.** Put a hidden
> `<!-- /whatsnew -->` marker on its own line right before the `## Downloads`
> table. The popup (`GET /api/release-notes`) renders everything **before** the
> marker, so the downloads table + self-update boilerplate stay on GitHub but out
> of the in-app view. (Falls back to splitting before `## Downloads` if the marker
> is missing.)

> The in-app "Comprobar actualizaciones" check and the release links only work
> once the GitHub repo is **public** — the unauthenticated API returns 404 for
> a private repo.

## 6. Signed updater artifacts (self-update)

The in-app updater (`tauri-plugin-updater`) only works if each build is **signed
with the updater private key** and the release ships a `latest.json`. The public
key lives in `tauri.conf.json` (`plugins.updater.pubkey`); `bundle.createUpdaterArtifacts`
is on, so a signed build emits a `.sig` next to each bundle.

**Linux — sign *after* the WebKit strip.** Tauri signs the AppImage during
`tauri build`, but §3a repackages it (invalidating that signature), so the
AppImage is signed last, with `tauri signer sign`:

```bash
export TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.tauri/yoink.key)"      # path or contents
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="$(cat ~/.tauri/pass)"  # a temp file — never inline the password
APPIMAGE_EXTRACT_AND_RUN=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 NO_STRIP=1 \
  npx tauri build --bundles deb,appimage
python scripts/strip_appimage_webkit.py   # §3a — repackage without bundled WebKit (drops the stale .sig)
npx tauri signer sign --private-key "$(cat ~/.tauri/yoink.key)" \
  --password "$(cat ~/.tauri/pass)" \
  src-tauri/target/release/bundle/appimage/Yoink_<ver>_amd64.AppImage
python scripts/build_rpm.py   # §3b — the rpm from the deb (the updater never uses it, so it needs no sig)
```

This writes a fresh `.sig` next to the **stripped AppImage**
(`…/Yoink_<ver>_amd64.AppImage.sig`) — the only Linux artifact the updater
self-installs from. Each `.sig` holds one base64 signature string. The
`.deb`/`.rpm` need no signature (the updater offers their users a "view release"
link instead of auto-installing — see the note below).

**Windows — sign locally, never on the build VM.** The signing key must not leave
your machine, so the Windows installers are built **unsigned** on the VM
(`createUpdaterArtifacts: false` there — see [Windows builds](#windows-builds))
and then signed **here** with `tauri signer sign`, which signs an already-built
file without rebuilding. Copy the `.msi`/`-setup.exe` back from the VM, then:

```bash
npx tauri signer sign --private-key "$(cat ~/.tauri/yoink.key)" \
  --password "$(cat ~/.tauri/pass)" /path/to/Yoink_<ver>_x64-setup.exe
```

That writes `Yoink_<ver>_x64-setup.exe.sig` beside the installer. The updater
self-installs from the NSIS `-setup.exe`, so that's the one that must be signed.

> The password lives **temporarily** in `~/.tauri/pass` (`printf %s 'PW' >
> ~/.tauri/pass`) so it never appears inline in a command or shell history; delete
> it after the release with `shred -u ~/.tauri/pass`. The key (`~/.tauri/yoink.key`)
> and password stay out of the repo, CI and the VM — always.

**Build `latest.json` from those signatures** — the CLI does not reliably emit
it, so assemble it by hand. It maps each updater target to its installer URL and
the signature **string** (the contents of the matching `.sig`). The updater
self-installs from the AppImage on Linux and the NSIS `-setup.exe` on Windows,
so those are the two targets:

```json
{
  "version": "1.2.0",
  "pub_date": "2026-06-02T21:19:27Z",
  "platforms": {
    "linux-x86_64":   { "signature": "<contents of …_amd64.AppImage.sig>",   "url": "https://github.com/ayozetr/yoink-app/releases/download/v<ver>/Yoink_<ver>_amd64.AppImage" },
    "windows-x86_64": { "signature": "<contents of …_x64-setup.exe.sig>", "url": "https://github.com/ayozetr/yoink-app/releases/download/v<ver>/Yoink_<ver>_x64-setup.exe" }
  }
}
```

**Attach to the GitHub release** the `latest.json` plus the installers
(AppImage/deb/rpm/exe/msi) — and **not** the standalone `.sig` files. The updater
reads each signature from the `"signature"` field inside `latest.json`, never
from separate assets, so uploading the `.sig` files is redundant (v1.0.0/v1.1.0
shipped without them). The endpoint points at
`releases/latest/download/latest.json`, so that file must be an asset of the
**latest** release.

Notes:
- The **private key never goes in the repo or CI logs** — keep it in a password
  manager / local secret. Only the public key is committed (in `tauri.conf.json`).
- The updater self-installs on **Windows** and the **Linux AppImage** only; the
  app detects this (the `is_appimage` command) and offers ".deb/.rpm" users a
  "view release" link instead.
- Self-update only kicks in **from a version that already shipped the updater**
  (v1.1.0+). Earlier installs must update once by hand.

---

## Windows builds

The recommended path is **CI** (§0): `release.yml` builds and signs the Windows
installers on a `windows-latest` runner. The Windows `ffmpeg`/`ffprobe` are
**cross-compiled on the Linux runner** (`build_ffmpeg.sh --windows`, mingw-w64)
and handed to the Windows job as an artifact, so the Windows machine only builds
`yoink-core` + the Tauri installers.

To build Windows **manually** (e.g. on a local Windows box — Tauri needs WebView2
+ the MSVC toolchain, which aren't on Linux):

Prerequisites: **Rust** (MSVC toolchain) + **VS Build Tools** (C++ workload),
**Node**, **Python**, **Git**, **WebView2 Runtime**. From the repo root (the
shell is PowerShell, so chain with `;`, not `&&`):

```powershell
npm ci                                    # frontend deps
bash scripts/build_ffmpeg.sh --windows    # or copy the CI-built ffmpeg.exe/ffprobe.exe
python scripts/build_core.py              # cargo build + fetch yt-dlp.exe + assemble core
npm run tauri build                       # -> target\release\bundle\{msi,nsis}\
```

Output: `Yoink_<ver>_x64_en-US.msi` (WiX) and `Yoink_<ver>_x64-setup.exe` (NSIS).
The backend port (8756), CORS and ffmpeg bundling work the same. WebView2 is
Chromium-based, so the WebKitGTK rendering quirks (blur ghosting) don't apply on
Windows.

**Build unsigned, sign locally** (to keep the signing key off the build machine):
set `createUpdaterArtifacts:false` in `tauri.conf.json`, drop the signing env,
build **unsigned**, copy the `.msi`/`-setup.exe` back, and sign the `-setup.exe`
here with `tauri signer sign` — see [§6](#6-signed-updater-artifacts-self-update).

---

## Troubleshooting the AppImage (`linuxdeploy`)

The AppImage is assembled by `linuxdeploy` + its `gtk` plugin. With no
`--verbose`, the only message on failure is the useless
`failed to run linuxdeploy`. Rebuild just the AppImage with logs:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 npx tauri build --bundles appimage --verbose
```

### A. `failed to run linuxdeploy` with no real error (FUSE)

The bundler tools (`linuxdeploy`, `appimagetool`) are themselves AppImages and
try to mount via **FUSE**. On hosts without FUSE (containers, some sandboxes)
they fail instantly. Fix — make them extract-and-run instead of mounting:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 npm run tauri build
```

This is the failure we hit for the first v0.5.0 build; the env flag fixed it.

### B. A polluted host library path (e.g. VMware)

Symptom — `linuxdeploy` deploys a library from an unrelated path, then fails
resolving *its* deps:

```
[gtk/stdout] Deploying shared library /usr/lib/vmware/lib/libgdk_pixbuf-2.0.so.0/...
[gtk/stdout] ERROR: Could not find dependency: libcroco-0.6.so.3
```

The `linuxdeploy-plugin-gtk` script collects GTK libs with a **recursive**
`find` under `/usr/lib`; VMware Workstation ships ancient GTK copies under
`/usr/lib/vmware/lib/` that still need the obsolete `libcroco`. Purely a
contaminated build host.

Fix — patch the plugin's `find` to skip VMware (the plugin is downloaded to
`~/.cache/tauri/linuxdeploy-plugin-gtk.sh`; re-apply if Tauri re-downloads it):

```bash
done < <(find "$directory" -not -path "*/vmware/*" \( -type l -o -type f \) -name "$library" -print0)
```

…or build on a host without VMware.

> **Heads-up:** Tauri re-downloads the plugin into `~/.cache/tauri/` whenever it
> is missing — a clean cache, a fresh machine, or the first AppImage build of a
> session — which **silently reverts this patch**. v1.5.0's first build hit
> exactly this (the previous release's patch was gone). Always verify the patch
> is present **right before** the AppImage build:
>
> ```bash
> grep -q vmware ~/.cache/tauri/linuxdeploy-plugin-gtk.sh \
>   && echo "patch OK" || echo "PATCH MISSING — re-apply before building"
> ```

### C. Blank/white window on Wayland

Symptom: the app launches (icon in the taskbar) but the window stays blank/
white, or crashes with `Gdk-Message: Error 71`. This is WebKitGTK's DMABUF
renderer misbehaving on Wayland.

Fix — **already in the binary**: `src-tauri/src/main.rs` sets
`WEBKIT_DISABLE_DMABUF_RENDERER=1` at startup (unless the user already set it),
so all three bundles boot on Wayland. If you ever see it again, run with the
variable exported to confirm:

```bash
WEBKIT_DISABLE_DMABUF_RENDERER=1 ./Yoink_<ver>_amd64.AppImage
```

Note: this must be set at **runtime** — setting it only for `tauri build` does
nothing for the end user, which is why it lives in `main.rs`.

### Useful env flags

```bash
APPIMAGE_EXTRACT_AND_RUN=1       # avoid FUSE for the bundler tools (build-time)
WEBKIT_DISABLE_DMABUF_RENDERER=1 # Wayland blank screen — set at RUNTIME (in main.rs)
NO_STRIP=1                       # skip stripping (avoids linuxdeploy strip quirks)
```

---

## Packaged-app gotchas (WebKitGTK + the backend)

The dev server runs in your **system browser** (Chromium); the bundle runs in
the **Tauri webview** — WebKitGTK on Linux (origin `tauri://localhost`),
WebView2/Chromium on Windows (origin `http://tauri.localhost`). Several things
work in dev but break in the packaged app — these all bit us once. Build with
devtools (below) and check the console first.

### CORS — scoped to local origins
The webview origin differs per platform: `tauri://localhost` (Linux/macOS) and
`http://tauri.localhost` (Windows — note `http`, not `https`). `main.rs` (the backend) allows those plus the dev server via a scoped CORS
layer, not a blanket `*`, so a random web page open in a browser can't reach the local
API. If you change the webview origin (e.g. enabling https on Windows) update the
regex, or the UI silently gets no data (Settings won't open). Devtools symptom:
`... is not allowed by Access-Control-Allow-Origin`.

### Backend port — avoid 8000
The backend listens on a fixed port the frontend hardcodes
(`VITE_API_BASE_URL` default; `YOINK_PORT` for the backend). 8000 is heavily
used and collided on the dev machine, so the backend couldn't bind and the app
had no API. We use **8756**. Symptom in the backend log:
`error while attempting to bind on address ('127.0.0.1', 8000): address already in use`.

### Backend startup race — retry the initial load
`yoink-core` is a native binary and starts in well under a second, but the
first request can still arrive before it has bound the port. The frontend
retries the initial
settings/history fetch (`App.tsx`) until the backend answers, and a startup
splash (`Splash.tsx`) covers the wait. Symptom if this regresses:
`net::ERR_CONNECTION_REFUSED` on load and the app stuck with no data.

### No `filter: blur()` / `backdrop-filter` on scrolled content
WebKitGTK fails to repaint content scrolled over a large CSS blur, leaving
**ghost/duplicated text** that clears on window resize. Avoid a large CSS blur
behind anything that scrolls: use a `radial-gradient` instead of `blur-3xl`, and
solid translucent backgrounds instead of `backdrop-blur`. Don't reintroduce these.

### Kill the backend on exit
The spawned backend does **not** die with the app by default — it lingers
holding the port, so the next launch talks to a **stale** backend (e.g. one
built before a fix). `main.rs` stores the `CommandChild` and kills it on
`RunEvent::Exit`/`ExitRequested`. A leftover `yoink-core` on the port is an
orphan — kill it before retesting (especially after installing several test
builds in a row, where an *old* backend with stale CORS keeps serving 8756):
- Linux: `kill $(lsof -ti:8756)`
- Windows: `Get-Process yoink-core,yoink -ErrorAction SilentlyContinue | Stop-Process -Force`

### Debugging the webview (devtools)
Release builds have no devtools. To inspect the packaged app temporarily:

```toml
# src-tauri/Cargo.toml
tauri = { version = "2", features = ["devtools"] }
```

Rebuild, then F12 / right-click → *Inspect* in the window. **Remove the feature
before the real release build.**
