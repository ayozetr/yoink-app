# Releasing Yoink

How a new versioned release is cut and published. Releases are **manual**
(no CI workflow yet). Each release ships three Linux bundles: `.AppImage`,
`.deb` and `.rpm`, each with the FastAPI backend bundled as a PyInstaller
sidecar (so users need no Python).

Prerequisites on the build host:

- Rust toolchain, and on Linux `webkit2gtk` (4.1).
- The backend venv with PyInstaller (`python scripts/setup.py` then
  `backend/.venv/bin/pip install pyinstaller`).
- `ffmpeg` is a **runtime** dependency of the app (merges); not needed to build.

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
python scripts/build_backend.py
```

This PyInstaller-bundles `backend/run_backend.py` (collecting yt-dlp's dynamic
extractors + uvicorn internals) into
`src-tauri/binaries/yoink-backend-<target-triple>`, the name Tauri's
`externalBin` sidecar expects. The packaged backend listens on port 8000
(matching the frontend's default `VITE_API_BASE_URL`).

## 3. Build the bundles

```bash
APPIMAGE_EXTRACT_AND_RUN=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 NO_STRIP=1 \
  npm run tauri build
```

The `.deb` and `.rpm` are produced by their own packagers and practically never
fail. The **AppImage** step (`linuxdeploy`) is the fragile one — see
troubleshooting below. `APPIMAGE_EXTRACT_AND_RUN=1` is what makes it work on
hosts without FUSE.

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

### Useful env flags

```bash
APPIMAGE_EXTRACT_AND_RUN=1       # avoid FUSE for the bundler tools (the key one)
WEBKIT_DISABLE_DMABUF_RENDERER=1 # avoids some WebKitGTK rendering issues
NO_STRIP=1                       # skip stripping (avoids linuxdeploy strip quirks)
```
