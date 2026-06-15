/**
 * A process-wide single-download lock shared by every download engine.
 *
 * Yoink deliberately downloads one file at a time — concurrent downloads are an
 * explicit non-goal. The main panel (single + playlist), the queue, and the
 * music-import card each own an independent download engine; without a shared
 * lock two of them can run at once and, because every file lands in the same
 * download folder under the same name template, resolve to the same `.part`
 * file and corrupt each other (yt-dlp resumes partial bytes). This module is the
 * one place that enforces mutual exclusion across those engines.
 *
 * It is purely in-memory and is never persisted: a lock that survived a reload
 * would wedge every future download if a tab were closed while holding it.
 */

import { useSyncExternalStore } from "react";

/** Which engine currently holds the download lock. */
export type DownloadOwner = "downloader" | "queue" | "music";

let owner: DownloadOwner | null = null;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

/**
 * Try to take the lock for `who`.
 *
 * Returns `true` if it was acquired (or is already held by the same owner —
 * acquisition is re-entrant), `false` if another engine holds it.
 */
export function acquireDownloadLock(who: DownloadOwner): boolean {
  if (owner !== null && owner !== who) return false;
  if (owner !== who) {
    owner = who;
    emit();
  }
  return true;
}

/** Release the lock, but only if `who` is the current holder (else a no-op). */
export function releaseDownloadLock(who: DownloadOwner): void {
  if (owner === who) {
    owner = null;
    emit();
  }
}

/** The engine currently holding the lock, or `null` when it's free. */
export function downloadLockOwner(): DownloadOwner | null {
  return owner;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** React hook: the current lock owner, re-rendering when it changes. */
export function useDownloadLock(): DownloadOwner | null {
  return useSyncExternalStore(subscribe, downloadLockOwner, downloadLockOwner);
}

/** True when the lock is held by someone other than `self` (or, with no `self`,
 *  held by anyone) — the condition for disabling a "start download" control. */
export function isLockedByOther(self?: DownloadOwner): boolean {
  return owner !== null && owner !== self;
}
