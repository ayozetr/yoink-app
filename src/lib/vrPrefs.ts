/**
 * Remembers the VR layout the user picked per uploader/studio.
 *
 * yt-dlp can't tell us the exact layout, so the user's own correction is the
 * best source of truth. Since Yoink is a local app, we persist the choice in
 * localStorage keyed by uploader and reuse it to seed future downloads from the
 * same studio (which publish consistently in one layout).
 */

import type { VRLayout } from "../types/download";

const VALID: readonly VRLayout[] = [
  "180_sbs",
  "180_tb",
  "180_mono",
  "360_sbs",
  "360_tb",
  "360_mono",
  "fisheye190",
  "fisheye200",
  "mkx200",
  "mkx220",
  "rf52",
];

const keyFor = (uploader: string) => `yoink-vr-layout:${uploader}`;

/** The layout last chosen for this uploader, or null if none/invalid. */
export function rememberedLayout(
  uploader: string | null | undefined,
): VRLayout | null {
  if (!uploader) return null;
  try {
    const value = localStorage.getItem(keyFor(uploader));
    return value && (VALID as readonly string[]).includes(value)
      ? (value as VRLayout)
      : null;
  } catch {
    return null;
  }
}

/** Persist the layout chosen for this uploader (no-op without an uploader). */
export function rememberLayout(
  uploader: string | null | undefined,
  layout: VRLayout,
): void {
  if (!uploader) return;
  try {
    localStorage.setItem(keyFor(uploader), layout);
  } catch {
    /* localStorage unavailable (private mode / quota) — ignore. */
  }
}
