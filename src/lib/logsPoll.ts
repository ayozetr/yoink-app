// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

import { fetchLogs } from "./api";
import type { LogsResponse } from "../types/download";

/**
 * Poll the app log tail and hand each result to `onData`, re-fetching every
 * `intervalMs`. Returns an unsubscribe that stops the poll and aborts any
 * in-flight request. Delivering results through this callback (rather than
 * setting state inside an effect) keeps the Logs view's effect side-effect-free.
 */
export function subscribeLogs(
  onData: (res: LogsResponse) => void,
  intervalMs = 5000,
): () => void {
  const ctrl = new AbortController();
  let stopped = false;
  let inFlight = false;
  const tick = async () => {
    if (inFlight) return; // a slow fetch (> interval) must not stack a second one
    inFlight = true;
    try {
      const res = await fetchLogs(2000, ctrl.signal);
      if (!stopped) onData(res);
    } catch {
      // Keep the last delivered content on a transient failure.
    } finally {
      inFlight = false;
    }
  };
  void tick();
  const id = window.setInterval(() => void tick(), intervalMs);
  return () => {
    stopped = true;
    ctrl.abort();
    window.clearInterval(id);
  };
}
