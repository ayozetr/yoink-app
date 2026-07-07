/**
 * Desktop-only (Tauri) behaviours: close-to-tray, launch-at-startup, and a global
 * shortcut. Each call no-ops in a plain browser. The Rust shell owns the actual
 * behaviour (tray, window hide/show, autostart registration, shortcut) — these just
 * drive its commands. Mirrors the `minimize_to_tray` / `launch_at_startup` /
 * `global_hotkey` settings, following the lazy-import + `isTauri` guard pattern used
 * across `src/lib` (see `apiBase.ts`).
 */

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** Invoke a Rust command, swallowing errors and no-oping outside Tauri. */
async function call<T>(
  cmd: string,
  args?: Record<string, unknown>,
): Promise<T | undefined> {
  if (!isTauri()) return undefined;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<T>(cmd, args);
  } catch {
    return undefined;
  }
}

/** Close-to-tray: hide the window on close instead of quitting. */
export async function setMinimizeToTray(enabled: boolean): Promise<void> {
  await call("set_minimize_to_tray", { enabled });
}

/** Register/unregister launching Yoink at system startup. */
export async function setAutostart(enabled: boolean): Promise<void> {
  await call("set_autostart", { enabled });
}

/** Register/unregister the global shortcut (Ctrl/⌘+Shift+Y). */
export async function setGlobalHotkey(enabled: boolean): Promise<void> {
  await call("set_global_hotkey", { enabled });
}

/** Push the desktop settings to the Rust shell (called on load + on save). */
export async function syncDesktopSettings(s: {
  minimize_to_tray: boolean;
  launch_at_startup: boolean;
  disable_global_hotkeys: boolean;
}): Promise<void> {
  if (!isTauri()) return;
  await setMinimizeToTray(s.minimize_to_tray);
  await setAutostart(s.launch_at_startup);
  // Inverted setting: global shortcuts are off by default, so register only when the
  // user has NOT disabled them.
  await setGlobalHotkey(!s.disable_global_hotkeys);
}

/**
 * Subscribe to a Tauri event emitted by the Rust shell. Returns an unlisten
 * function; no-ops (returns a no-op) outside Tauri.
 */
async function onEvent(name: string, handler: () => void): Promise<() => void> {
  if (!isTauri()) return () => {};
  try {
    const { listen } = await import("@tauri-apps/api/event");
    return await listen(name, () => handler());
  } catch {
    return () => {};
  }
}

/** Global "bring to front + paste-and-analyze" (Ctrl/⌘+Shift+Y). */
export const onGlobalHotkey = (h: () => void) => onEvent("global-hotkey", h);
/** Global "quick-download the clipboard without showing the window" (Ctrl/⌘+Shift+D). */
export const onGlobalQuickDownload = (h: () => void) =>
  onEvent("global-quick-download", h);
/** Global "bring to front + paste, no analyze" (Ctrl/⌘+Shift+P). */
export const onGlobalPaste = (h: () => void) => onEvent("global-paste", h);
/** Global "cancel the current download" (Ctrl/⌘+Shift+X). */
export const onGlobalCancel = (h: () => void) => onEvent("global-cancel", h);
/** Global "open the downloads folder" (Ctrl/⌘+Shift+F). */
export const onGlobalOpenFolder = (h: () => void) =>
  onEvent("global-open-folder", h);
