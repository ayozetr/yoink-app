/**
 * Open a URL in the system browser.
 *
 * In the packaged desktop app the webview doesn't follow `target="_blank"` to
 * the OS browser, so we use Tauri's opener plugin. In a plain browser (dev) the
 * import resolves but the call fails (no Tauri runtime), and we fall back to
 * `window.open`.
 */
export async function openExternal(url: string): Promise<void> {
  try {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(url);
  } catch {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}
