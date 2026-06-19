/**
 * Saved download presets — named bundles of format options the user can apply
 * to the preview in one click.
 *
 * Local convenience state (like `vrPrefs` / `searchSource`), so it lives in
 * localStorage and survives restarts. A preset captures the format selection,
 * not the URL; quality/container are applied best-effort (skipped when the
 * current media can't offer them).
 */

import type { AudioFormat, MediaKind, VideoContainer } from "../types/download";

export interface DownloadPreset {
  id: string;
  name: string;
  kind: MediaKind;
  quality?: string;
  container?: VideoContainer;
  audioFormat?: AudioFormat;
  embedSubs?: boolean;
  embedChapters?: boolean;
}

const KEY = "yoink-presets";

/** A unique id, with a fallback for non-secure contexts (no crypto.randomUUID). */
export function newPresetId(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  return uuid ?? `p-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/** Load saved presets (empty/[] on any problem). */
export function loadPresets(): DownloadPreset[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return (parsed as unknown[])
      .map((p) => p as Record<string, unknown>)
      .filter(
        (p) =>
          !!p &&
          typeof p.id === "string" &&
          typeof p.name === "string" &&
          (p.kind === "video" || p.kind === "audio"),
      )
      .map((p) => ({
        id: p.id as string,
        name: p.name as string,
        kind: p.kind as MediaKind,
        quality: typeof p.quality === "string" ? p.quality : undefined,
        container:
          typeof p.container === "string"
            ? (p.container as VideoContainer)
            : undefined,
        audioFormat:
          typeof p.audioFormat === "string"
            ? (p.audioFormat as AudioFormat)
            : undefined,
        embedSubs: typeof p.embedSubs === "boolean" ? p.embedSubs : undefined,
        embedChapters:
          typeof p.embedChapters === "boolean" ? p.embedChapters : undefined,
      }));
  } catch {
    return [];
  }
}

/** Persist the preset list (best-effort). */
export function savePresets(presets: DownloadPreset[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(presets));
  } catch {
    /* localStorage unavailable — ignore. */
  }
}
