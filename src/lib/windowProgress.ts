/**
 * Reflect download progress in the window title and, on the desktop app, the
 * taskbar progress bar. No-ops gracefully in a plain browser.
 *
 * @param percent 0–100 while downloading, or null to clear (idle / finished).
 */
export function setWindowProgress(percent: number | null): void {
  // Window title — works in both the browser and the desktop webview.
  document.title = percent == null ? "Yoink" : `Yoink — ${Math.round(percent)}%`;

  // Taskbar progress bar — desktop only; ignored when not under Tauri.
  void (async () => {
    try {
      const { getCurrentWindow, ProgressBarStatus } = await import(
        "@tauri-apps/api/window"
      );
      await getCurrentWindow().setProgressBar({
        status:
          percent == null ? ProgressBarStatus.None : ProgressBarStatus.Normal,
        progress: percent == null ? 0 : Math.round(percent),
      });
    } catch {
      /* not running under Tauri — title-only is fine */
    }
  })();
}
