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

/** Push the three desktop settings to the Rust shell (called on load + on save). */
export async function syncDesktopSettings(s: {
  minimize_to_tray: boolean;
  launch_at_startup: boolean;
  global_hotkey: boolean;
}): Promise<void> {
  if (!isTauri()) return;
  await setMinimizeToTray(s.minimize_to_tray);
  await setAutostart(s.launch_at_startup);
  await setGlobalHotkey(s.global_hotkey);
}

/**
 * Subscribe to the global-shortcut trigger emitted by Rust. Returns an unlisten
 * function; no-ops (returns a no-op) outside Tauri.
 */
export async function onGlobalHotkey(handler: () => void): Promise<() => void> {
  if (!isTauri()) return () => {};
  try {
    const { listen } = await import("@tauri-apps/api/event");
    return await listen("global-hotkey", () => handler());
  } catch {
    return () => {};
  }
}
