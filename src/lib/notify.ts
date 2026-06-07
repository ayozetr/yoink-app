/**
 * Send a desktop notification (e.g. when a download finishes), requesting
 * permission on first use. No-ops in a plain browser or when permission is
 * denied / unavailable.
 */
export async function notify(title: string, body: string): Promise<void> {
  try {
    const { isPermissionGranted, requestPermission, sendNotification } =
      await import("@tauri-apps/plugin-notification");
    let granted = await isPermissionGranted();
    if (!granted) {
      granted = (await requestPermission()) === "granted";
    }
    if (granted) sendNotification({ title, body });
  } catch {
    /* not running under Tauri */
  }
}
