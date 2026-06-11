/**
 * A persistent, sequential download queue.
 *
 * Yoink is a local app, so the queue lives in localStorage — it survives app
 * restarts. Items interrupted by a close come back as "pending" so they resume
 * on the next run (yt-dlp itself resumes the partial `.part` bytes on disk).
 */

export type QueueStatus = "pending" | "active" | "done" | "error";

export interface QueueItem {
  id: string;
  url: string;
  status: QueueStatus;
  /** Final file name once done, else the URL is shown. */
  title?: string;
  error?: string;
}

const KEY = "yoink-queue";

/** Load the saved queue; any "active" item (a crash mid-download) → "pending". */
export function loadQueue(): QueueItem[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return (parsed as unknown[])
      .map((i) => i as Record<string, unknown>)
      .filter(
        (i) => i && typeof i.id === "string" && typeof i.url === "string",
      )
      .map((i) => ({
        id: i.id as string,
        url: i.url as string,
        // "active" (interrupted) and any unknown value reset to "pending".
        status:
          i.status === "done" || i.status === "error" ? i.status : "pending",
        title: typeof i.title === "string" ? i.title : undefined,
        error: typeof i.error === "string" ? i.error : undefined,
      }));
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
