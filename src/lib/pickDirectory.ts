/**
 * Open the native folder picker (Tauri dialog plugin) and return the chosen
 * directory, or null if cancelled / not in the desktop app.
 *
 * In a plain browser (dev) there's no native directory picker, so this resolves
 * to null and the caller keeps the typed path.
 */
export async function pickDirectory(current?: string): Promise<string | null> {
  try {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({
      directory: true,
      multiple: false,
      defaultPath: current || undefined,
    });
    return typeof selected === "string" ? selected : null;
  } catch {
    return null; // not running inside Tauri
  }
}
