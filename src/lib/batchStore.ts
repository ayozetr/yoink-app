/**
 * Persists the main panel's in-flight download batch so a multi-item playlist
 * survives a close / refresh / crash and can be resumed.
 *
 * The panel's batch runner (`DownloaderPanel` `startQueue`/`runJob`) is otherwise
 * in-memory (a `useRef`), so a 100-track playlist interrupted at track 40 loses
 * the remaining 60. The queue (`queueStore`) already persists; this gives the
 * panel flow the same resilience without moving playlists out of it (which would
 * lose the rich preview + batch auto-tagging).
 *
 * The runner is strictly sequential, so progress is a single `done` count: the
 * first `done` jobs finished, the rest are pending (the one interrupted mid-flight
 * is among the pending and yt-dlp resumes its `.part`).
 */

import type { DownloadRequest } from "../types/download";

/** One queued download: the request to send and a human title for the UI. */
export interface BatchJob {
  request: DownloadRequest;
  title: string;
}

interface StoredBatch {
  jobs: BatchJob[];
  done: number;
}

const KEY = "yoink-batch";

/** Persist the batch and how many of its jobs have finished (best-effort). */
export function saveBatch(jobs: BatchJob[], done: number): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ jobs, done } satisfies StoredBatch));
  } catch {
    /* localStorage unavailable / quota — ignore. */
  }
}

/** The not-yet-finished jobs of a persisted batch (empty if none/invalid). */
export function loadPendingBatch(): BatchJob[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Partial<StoredBatch>;
    if (!parsed || !Array.isArray(parsed.jobs)) return [];
    const done = typeof parsed.done === "number" ? parsed.done : 0;
    return parsed.jobs
      .filter(
        (j): j is BatchJob =>
          !!j &&
          typeof j.title === "string" &&
          !!j.request &&
          typeof j.request.url === "string",
      )
      .slice(done);
  } catch {
    return [];
  }
}

/** Forget the persisted batch (on completion, cancel, or a fresh analysis). */
export function clearBatch(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
