/**
 * In-app self-update helper, built on the Tauri updater plugin.
 *
 * The updater can auto-install on Windows (always) and on Linux only when the
 * app runs as an AppImage — .deb/.rpm packages can't be replaced in place. On
 * every other target (or when running in a plain browser during dev) we fall
 * back to a "view release" link.
 *
 * All entry points are defensive: outside the Tauri runtime, or when the update
 * endpoint is offline / returns 404, `check()` throws — callers treat that as
 * "couldn't check" rather than crashing.
 */

import type { Update } from "@tauri-apps/plugin-updater";

/** Public GitHub releases page used by the manual "view release" fallback. */
export const RELEASES_URL = "https://github.com/ayozetr/yoink-app/releases/latest";

/** True when we're running inside the Tauri webview (vs. a plain browser). */
function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/**
 * Whether this platform/packaging can auto-install an update in place.
 *
 * Windows can always self-update; Linux only when shipped as an AppImage.
 * Returns false outside Tauri or on any error.
 */
export async function canAutoUpdate(): Promise<boolean> {
  if (!isTauri()) return false;
  try {
    const { platform } = await import("@tauri-apps/plugin-os");
    const plat = platform();
    if (plat === "windows") return true;
    if (plat === "linux") {
      const { invoke } = await import("@tauri-apps/api/core");
      return await invoke<boolean>("is_appimage");
    }
    return false;
  } catch {
    return false;
  }
}

/** Result of an update check. */
export type UpdateCheck =
  | { status: "tauri-unavailable" }
  | { status: "error" }
  | { status: "up-to-date" }
  | {
      status: "available";
      version: string;
      update: Update;
      /**
       * Whether this update can be installed in place (Windows / Linux
       * AppImage). When false, the UI offers only a "view release" link.
       */
      autoInstallable: boolean;
    };

/**
 * Check for a newer release.
 *
 * Never throws: a missing runtime, offline endpoint, or 404 all resolve to a
 * sensible non-update state.
 */
export async function checkForUpdate(): Promise<UpdateCheck> {
  if (!isTauri()) return { status: "tauri-unavailable" };
  try {
    const { check } = await import("@tauri-apps/plugin-updater");
    const update = await check();
    if (!update) return { status: "up-to-date" };
    return {
      status: "available",
      version: update.version,
      update,
      autoInstallable: await canAutoUpdate(),
    };
  } catch {
    return { status: "error" };
  }
}

/**
 * Download + install the given update, then relaunch the app.
 *
 * `onProgress` (0–1) reflects download progress when total size is known.
 */
export async function installUpdate(
  update: Update,
  onProgress?: (fraction: number) => void,
): Promise<void> {
  let total = 0;
  let downloaded = 0;
  await update.downloadAndInstall((event) => {
    switch (event.event) {
      case "Started":
        total = event.data.contentLength ?? 0;
        break;
      case "Progress":
        downloaded += event.data.chunkLength;
        if (total > 0) onProgress?.(Math.min(downloaded / total, 1));
        break;
      case "Finished":
        onProgress?.(1);
        break;
    }
  });
  const { relaunch } = await import("@tauri-apps/plugin-process");
  await relaunch();
}
