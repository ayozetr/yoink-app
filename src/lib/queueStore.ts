/**
 * A persistent, sequential download queue.
 *
 * Yoink is a local app, so the queue lives in localStorage — it survives app
 * restarts. Items interrupted by a close come back as "pending" so they resume
 * on the next run (yt-dlp itself resumes the partial `.part` bytes on disk).
 */

import type { MusicTrack } from "../types/music";

export type QueueStatus =
  | "pending"
  | "active"
  | "done"
  | "error"
  | "skipped"
  | "resolving";

/** One selectable entry inside a group (playlist/album) queue item. */
export interface QueueChild {
  id: string;
  title: string;
  status: QueueStatus;
  /** Whether it downloads when the group runs. */
  selected: boolean;
  error?: string;
  /** Direct URL for a video child (a regular-playlist entry). */
  url?: string;
  /** Track data for a music child — its YouTube URL is resolved via match at
   * download time, then the file is tagged with this metadata. */
  track?: MusicTrack;
}

export interface QueueItem {
  id: string;
  url: string;
  status: QueueStatus;
  /** Final file name once done, else the URL/title is shown. */
  title?: string;
  error?: string;
  /** Present when this item is a playlist/album group of selectable children. */
  children?: QueueChild[];
  /** UI: whether the group is expanded to show its children. */
  expanded?: boolean;
  /** Source name shown under the title, e.g. "Spotify", "YouTube Music". */
  sourceLabel?: string;
  /** A single music track (no children): downloaded as audio via match + tag. */
  track?: MusicTrack;
}

const KEY = "yoink-queue";

/** "active"/"resolving" (interrupted) and unknown values reset to "pending";
 * terminal states are kept. */
function resetStatus(s: unknown): QueueStatus {
  return s === "done" || s === "error" || s === "skipped" ? s : "pending";
}

function parseChild(raw: unknown): QueueChild | null {
  if (!raw || typeof raw !== "object") return null;
  const c = raw as Record<string, unknown>;
  if (typeof c.id !== "string" || typeof c.title !== "string") return null;
  return {
    id: c.id,
    title: c.title,
    status: resetStatus(c.status),
    selected: c.selected !== false,
    error: typeof c.error === "string" ? c.error : undefined,
    url: typeof c.url === "string" ? c.url : undefined,
    track: (c.track as MusicTrack | undefined) ?? undefined,
  };
}

/** Load the saved queue; interrupted items (a crash mid-download/resolve) reset
 * to "pending", and never-resolved placeholders are dropped. */
export function loadQueue(): QueueItem[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return (parsed as unknown[])
      .map((i) => i as Record<string, unknown>)
      .filter((i) => i && typeof i.id === "string" && typeof i.url === "string")
      // A placeholder still "resolving" when the app closed never got its
      // children, so it's dead weight — drop it.
      .filter((i) => i.status !== "resolving")
      .map((i) => {
        // Only carry the fields that are actually present, so a plain item
        // round-trips unchanged (no spurious children/expanded keys).
        const item: QueueItem = {
          id: i.id as string,
          url: i.url as string,
          status: resetStatus(i.status),
        };
        if (typeof i.title === "string") item.title = i.title;
        if (typeof i.error === "string") item.error = i.error;
        if (typeof i.sourceLabel === "string") item.sourceLabel = i.sourceLabel;
        if (i.track && typeof i.track === "object")
          item.track = i.track as MusicTrack;
        if (Array.isArray(i.children)) {
          item.children = i.children
            .map(parseChild)
            .filter(Boolean) as QueueChild[];
          item.expanded = i.expanded === true;
        }
        return item;
      });
  } catch {
    return [];
  }
}

/** Persist the queue (best-effort; ignores quota/private-mode failures). */
export function saveQueue(items: QueueItem[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    /* localStorage unavailable — ignore. */
  }
}

/** Extract the unique http(s) URLs from a free-text blob (whitespace-separated). */
export function parseUrls(text: string): string[] {
  const urls = text
    .split(/\s+/)
    .map((s) => s.trim())
    .filter((s) => /^https?:\/\//i.test(s));
  return [...new Set(urls)];
}

/** A unique id for a queue item, with a fallback for non-secure contexts.
 *
 * `crypto.randomUUID` only exists in secure contexts (https or localhost), so a
 * plain-http LAN deployment would otherwise throw and break the Add button.
 */
export function newQueueId(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  return uuid ?? `q-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
