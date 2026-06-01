# Releasing Yoink

How a new versioned release is cut and published. Releases are **manual**
(no CI workflow yet). Each release ships three Linux bundles: `.AppImage`,
`.deb` and `.rpm`, each with the FastAPI backend bundled as a PyInstaller
sidecar (so users need no Python).

Prerequisites on the build host:

- Rust toolchain, and on Linux `webkit2gtk` (4.1).
- The backend venv with PyInstaller (`python scripts/setup.py` then
  `backend/.venv/bin/pip install pyinstaller`).
- Bundled **ffmpeg + ffprobe**: run `python scripts/fetch_ffmpeg.py` once per
  platform (downloads LGPL builds to `backend/vendor/ffmpeg/`). The sidecar
  embeds them, so the shipped app needs no system ffmpeg. See
  [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) for the LGPL attribution.

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

## 2. Rebuild the backend sidecar

Whenever the backend changed since the last release, rebuild the sidecar so the
bundles ship the new code:

```bash
python scripts/fetch_ffmpeg.py   # once per platform — downloads ffmpeg/ffprobe
python scripts/build_backend.py
```

`build_backend.py` PyInstaller-bundles `backend/run_backend.py` (collecting
yt-dlp's dynamic extractors + uvicorn internals, and embedding ffmpeg/ffprobe
from `backend/vendor/ffmpeg/` if present) into
`src-tauri/binaries/yoink-backend-<target-triple>`, the name Tauri's
`externalBin` sidecar expects. The packaged backend listens on port **8756**
(matching the frontend's default `VITE_API_BASE_URL`); the bundled ffmpeg is
wired to yt-dlp via `ffmpeg_location` (`app/core/ffmpeg.py`).

## 3. Build the bundles

```bash
APPIMAGE_EXTRACT_AND_RUN=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 NO_STRIP=1 \
  npm run tauri build
```

The `.deb` and `.rpm` are produced by their own packagers and practically never
fail. The **AppImage** step (`linuxdeploy`) is the fragile one — see
troubleshooting below. `APPIMAGE_EXTRACT_AND_RUN=1` is what makes it work on
hosts without FUSE.

The Wayland blank-screen fix is **in the binary** (`src-tauri/src/main.rs`
forces `WEBKIT_DISABLE_DMABUF_RENDERER=1` before any webview code runs), so it
is present in all three bundles automatically — nothing to set per-package or
at runtime.

Output paths:

```
src-tauri/target/release/bundle/appimage/Yoink_<ver>_amd64.AppImage
src-tauri/target/release/bundle/deb/Yoink_<ver>_amd64.deb
src-tauri/target/release/bundle/rpm/Yoink-<ver>-1.x86_64.rpm
```

## 4. Smoke-test

```bash
./src-tauri/target/release/bundle/appimage/Yoink_<ver>_amd64.AppImage &
# the window should open; pasting a URL + Analizar should hit the bundled
# backend on :8000. (ffmpeg must be installed for video+audio merges.)
```

Quick structural check (no GUI needed) — confirm the sidecar is inside:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 ./...AppImage --appimage-extract 'usr/bin/*'
ls squashfs-root/usr/bin   # expect: yoink  yoink-backend
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

> The in-app "Comprobar actualizaciones" check and the release links only work
> once the GitHub repo is **public** — the unauthenticated API returns 404 for
> a private repo.

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
the **Tauri WebKitGTK webview** with origin `tauri://localhost`. Several things
work in dev but break in the packaged app — these all bit us once. Build with
devtools (below) and check the console first.

### CORS — allow the Tauri origin
The webview origin is `tauri://localhost` (Linux/macOS) / `https://tauri.localhost`
(Windows). The backend must allow it or **every `fetch` is blocked** — the
backend returns 200 but the webview drops the response, so the UI silently has
no data (e.g. the Settings modal never opens). Allowed in
`backend/app/core/config.py` → `cors_origins`. Devtools symptom:
`Origin tauri://localhost is not allowed by Access-Control-Allow-Origin`.

### Backend port — avoid 8000
The sidecar listens on a fixed port the frontend hardcodes
(`VITE_API_BASE_URL` default; `YOINK_PORT` for the backend). 8000 is heavily
used and collided on the dev machine, so the sidecar couldn't bind and the app
had no API. We use **8756**. Symptom in the sidecar log:
`error while attempting to bind on address ('127.0.0.1', 8000): address already in use`.

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
orphan — kill it (`kill $(lsof -ti:8756)`) before retesting.

### Debugging the webview (devtools)
Release builds have no devtools. To inspect the packaged app temporarily:

```toml
# src-tauri/Cargo.toml
tauri = { version = "2", features = ["devtools"] }
```

Rebuild, then F12 / right-click → *Inspect* in the window. **Remove the feature
before the real release build.**
