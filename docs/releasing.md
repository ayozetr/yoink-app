# Releasing Yoink

How a new versioned release is cut and published. Releases are **manual**
(no CI workflow yet). Each release ships three Linux bundles: `.AppImage`,
`.deb` and `.rpm`, each with the FastAPI backend bundled as a PyInstaller
**one-folder** distribution (a Tauri *resource*, launched by `main.rs`) so users
need no Python. It's `--onedir`, not `--onefile`: the app starts faster (no
per-launch extraction of the ~180 MB payload) at the cost of a bigger install
(the AppImage grew from ~173 MB to ~255 MB — the auto-update download grows to
match).

Prerequisites on the build host:

- Rust toolchain, and on Linux `webkit2gtk` (4.1).
- **Python 3.13** for the backend venv (not 3.14): `curl_cffi`'s impersonation —
  which lets yt-dlp pass Cloudflare/anti-bot 403s — only has wheels for the
  versions yt-dlp supports on 3.13, and 3.14's newer OpenSSL fingerprint is
  itself blocked by some sites. `scripts/setup.py` picks 3.13 automatically (via
  `uv python find 3.13`; isolated, the system Python is untouched). Install it
  once with `uv python install 3.13` if needed.
- On **Linux**, **`patchelf`** on PATH: setup clears the executable stack on a
  copy of uv's 3.13 runtime so the packaged sidecar starts (see §2).
- The backend venv with PyInstaller (`python scripts/setup.py` then
  `backend/.venv/bin/pip install pyinstaller`).
  - **After building the sidecar, confirm impersonation survived packaging:**
    run the built `yoink-backend ... --list-impersonate-targets` (or test a
    Cloudflare URL); if targets are empty, PyInstaller dropped `curl_cffi`'s
    native libs — add `--collect-all curl_cffi` in `scripts/build_backend.py`.
- Bundled **ffmpeg + ffprobe**: run `python scripts/fetch_ffmpeg.py` once per
  platform (downloads LGPL builds to `backend/vendor/ffmpeg/`). The sidecar
  embeds them, so the shipped app needs no system ffmpeg. See
  [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) for the LGPL attribution.
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
| `backend/app/core/config.py` | `app_version` |

The frontend's in-app version badge reads `__APP_VERSION__`, which Vite injects
from `package.json` at build time — no separate edit needed. Grep the previous
number across these files before building to catch a stray one.

Commit the bump together with any docs/README/icon updates.

## 2. Rebuild the backend

Whenever the backend changed since the last release, rebuild it so the bundles
ship the new code:

```bash
python scripts/fetch_ffmpeg.py   # once per platform — downloads ffmpeg/ffprobe
python scripts/build_backend.py
```

`build_backend.py` PyInstaller-bundles `backend/run_backend.py` (collecting
yt-dlp's dynamic extractors + uvicorn internals + `curl_cffi` for impersonation,
and embedding ffmpeg/ffprobe from `backend/vendor/ffmpeg/` if present) as a
**one-folder** (`--onedir`) distribution and copies the folder to
`src-tauri/binaries/yoink-backend/`, which `tauri.conf.json` bundles as a
`resources` entry (`→ backend/`). `src-tauri/src/main.rs` launches the exe inside
it directly (`std::process`), passing the port via `YOINK_PORT` and keeping a
stdin pipe open as a shutdown watchdog; it kills the process (and any ffmpeg
grandchild) on exit. The packaged backend listens on **8756** (matching the
frontend's default `VITE_API_BASE_URL`); the bundled ffmpeg is wired to yt-dlp
via `ffmpeg_location` (`app/core/ffmpeg.py`), which resolves `sys._MEIPASS`
(the `_internal/` folder in a onedir build).

> **Linux sidecar — executable-stack fix (automated).** uv's managed
> `libpython3.13.so` is built with an executable stack (`GNU_STACK = RWE`).
> PyInstaller extracts and `dlopen`s it at runtime, and a hardened kernel then
> refuses to start the sidecar with `cannot enable executable stack as shared
> object requires`. `scripts/setup.py` handles this: on Linux it copies the 3.13
> runtime to `backend/.python-rt` and clears the flag on the **copy**
> (`patchelf --clear-execstack` — never uv's shared file), then builds
> `backend/.venv` from there, so the bundled `libpython` is `GNU_STACK = RW` and
> the sidecar starts. Requirement: **`patchelf` on PATH** at setup time (setup
> warns if missing). `backend/.python-rt` is git-ignored and rebuilt by setup.
> Still **verify the sidecar starts** before releasing. **Windows (Python 3.12)
> is unaffected** (its libpython has no exec stack).

## 3. Build the bundles

Build **only** the `.deb` + AppImage with Tauri, then make the `.rpm` from the
`.deb` (see below) — **do not** let Tauri bundle the rpm:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 NO_STRIP=1 \
  npx tauri build --bundles deb,appimage
```

> **Why skip Tauri's rpm.** Tauri's rpm bundler (the `rpm` Rust crate) takes
> **10–12 min** to package the ~170 MB PyInstaller sidecar, while the `.deb` and
> AppImage of the same payload bundle in *seconds*. It isn't the compressor
> (the sidecar is incompressible — even `xz -9` is ~45 s) but the crate itself.
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

## 4. Smoke-test

```bash
./src-tauri/target/release/bundle/appimage/Yoink_<ver>_amd64.AppImage &
# the window should open; pasting a URL + Analizar should hit the bundled
# backend on :8756. (ffmpeg is bundled — no system install needed.)
```

> **Verify the backend launch, especially on Windows.** The backend is bundled
> as a one-folder resource and spawned by `main.rs`, so the launch path is
> exercised here — confirm the backend actually answers on :8756 and that closing
> the app leaves **no** orphan `yoink-backend` (nothing holding the port). This
> was verified on Linux end-to-end; the **Windows** build must be smoke-tested the
> same way on the VM before publishing, since the resource path + process spawn
> can't be checked from Linux. (Auto-update is unaffected either way — the updater
> replaces the whole AppImage/installer and doesn't care what's inside.)

Quick structural check (no GUI needed) — confirm the backend folder is inside:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 ./...AppImage --appimage-extract
ls squashfs-root/usr/bin                       # expect: yoink
ls squashfs-root/usr/lib/Yoink/backend         # expect: yoink-backend  _internal
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

**Linux — sign at build time** by exporting the key before `npm run tauri build`:

```bash
export TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.tauri/yoink.key)"      # path or contents
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="$(cat ~/.tauri/pass)"  # a temp file — never inline the password
APPIMAGE_EXTRACT_AND_RUN=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 NO_STRIP=1 \
  npx tauri build --bundles deb,appimage
python scripts/build_rpm.py   # §3b — the rpm from the deb (the updater never uses it, so it needs no sig)
```

This emits a `.sig` next to the **AppImage** (`…/Yoink_<ver>_amd64.AppImage.sig`) —
the only Linux artifact the updater self-installs from. Each `.sig` holds one
base64 signature string. The `.deb`/`.rpm` need no signature (the updater offers
their users a "view release" link instead of auto-installing — see the note below).

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

The Windows installers (`.msi` + NSIS `.exe`) must be built **on Windows** —
Tauri uses WebView2 + the MSVC toolchain, so there's no cross-compile from
Linux. (You can drive it over SSH on a Windows box/VM; the shell there is
PowerShell, so chain commands with `;`, not `&&`.)

Prerequisites on the Windows machine: **Rust** (MSVC toolchain) + **VS Build
Tools** (C++ workload), **Node**, **Python**, **Git**, **WebView2 Runtime**.

The scripts are cross-platform; from the repo root:

```powershell
python scripts/setup.py                               # venv + deps + npm install
backend\.venv\Scripts\python -m pip install pyinstaller
python scripts/fetch_ffmpeg.py                        # downloads the win64 ffmpeg
python scripts/build_backend.py                       # -> yoink-backend-...-windows-msvc.exe
npm run tauri build                                   # -> target\release\bundle\{msi,nsis}\
```

Output: `Yoink_<ver>_x64_en-US.msi` (WiX) and `Yoink_<ver>_x64-setup.exe` (NSIS).
The backend port (8756), CORS and ffmpeg bundling work the same. WebView2 is
Chromium-based, so the WebKitGTK rendering quirks (blur ghosting) don't apply on
Windows.

**Driving the VM over SSH.** The shell is PowerShell, so chain with `;`. Sync the
repo as a tarball (excluding `node_modules`/`.venv`/`target`/`vendor`/…) and
extract it **over** the existing checkout to reuse the cached venv/node_modules/
target — much faster; re-run `setup.py` only when deps change. SSH output can
carry banner noise (OpenSSH/post-quantum notices) — filter it if scripting.

**Build unsigned on the VM, sign locally.** The signing key must not touch the
VM, so flip `createUpdaterArtifacts` to `false` in the VM's copy of
`tauri.conf.json` before `npm run tauri build`, produce the `.msi`/`-setup.exe`
**unsigned**, copy them back, and sign the `-setup.exe` here with `tauri signer
sign` — see [§6](#6-signed-updater-artifacts-self-update). Minimal toggle script:

```python
# disable_updater.py  →  python disable_updater.py src-tauri/tauri.conf.json
import sys
p = sys.argv[1]
c = open(p, encoding="utf-8").read()
n = '"createUpdaterArtifacts": true'
open(p, "w", encoding="utf-8").write(
    c.replace(n, '"createUpdaterArtifacts": false')) if n in c else print("already off")
```

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

## Packaged-app gotchas (WebKitGTK + sidecar)

The dev server runs in your **system browser** (Chromium); the bundle runs in
the **Tauri webview** — WebKitGTK on Linux (origin `tauri://localhost`),
WebView2/Chromium on Windows (origin `http://tauri.localhost`). Several things
work in dev but break in the packaged app — these all bit us once. Build with
devtools (below) and check the console first.

### CORS — scoped to local origins
The webview origin differs per platform: `tauri://localhost` (Linux/macOS) and
`http://tauri.localhost` (Windows — note `http`, not `https`). `main.py` allows
those plus the dev server via an `allow_origin_regex` (`config.cors_origin_regex`),
not a blanket `*`, so a random web page open in a browser can't reach the local
API. If you change the webview origin (e.g. enabling https on Windows) update the
regex, or the UI silently gets no data (Settings won't open). Devtools symptom:
`... is not allowed by Access-Control-Allow-Origin`.

### Backend port — avoid 8000
The sidecar listens on a fixed port the frontend hardcodes
(`VITE_API_BASE_URL` default; `YOINK_PORT` for the backend). 8000 is heavily
used and collided on the dev machine, so the sidecar couldn't bind and the app
had no API. We use **8756**. Symptom in the sidecar log:
`error while attempting to bind on address ('127.0.0.1', 8000): address already in use`.

### Slow sidecar startup — retry the initial load
The PyInstaller sidecar unpacks ffmpeg (~155 MB) and starts uvicorn, which takes
several seconds — notably on Windows. The frontend retries the initial
settings/history fetch (`App.tsx`) until the backend answers, and a startup
splash (`Splash.tsx`) covers the wait. Symptom if this regresses:
`net::ERR_CONNECTION_REFUSED` on load and the app stuck with no data.

### No `filter: blur()` / `backdrop-filter` on scrolled content
WebKitGTK fails to repaint content scrolled over a large CSS blur, leaving
**ghost/duplicated text** that clears on window resize. `BackgroundGlow` uses a
`radial-gradient` instead of `blur-3xl`, and glass panels use a solid
translucent background instead of `backdrop-blur`. Don't reintroduce these.

### Kill the sidecar on exit
The spawned backend does **not** die with the app by default — it lingers
holding the port, so the next launch talks to a **stale** backend (e.g. one
built before a fix). `main.rs` stores the `CommandChild` and kills it on
`RunEvent::Exit`/`ExitRequested`. A leftover `yoink-backend` on the port is an
orphan — kill it before retesting (especially after installing several test
builds in a row, where an *old* sidecar with stale CORS keeps serving 8756):
- Linux: `kill $(lsof -ti:8756)`
- Windows: `Get-Process yoink-backend,yoink -ErrorAction SilentlyContinue | Stop-Process -Force`

### Debugging the webview (devtools)
Release builds have no devtools. To inspect the packaged app temporarily:

```toml
# src-tauri/Cargo.toml
tauri = { version = "2", features = ["devtools"] }
```

Rebuild, then F12 / right-click → *Inspect* in the window. **Remove the feature
before the real release build.**
