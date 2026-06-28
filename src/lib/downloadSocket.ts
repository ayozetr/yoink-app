/**
 * WebSocket client for the live download endpoint (`/api/ws/download`).
 *
 * Opens a socket, sends the download request, and forwards every event the
 * backend streams back. The WS URL is derived from the same base as the REST
 * client (`VITE_API_BASE_URL`) by swapping the `http`/`https` scheme.
 */

import i18n from "../i18n";
import type { DownloadEvent, DownloadRequest } from "../types/download";
import { getApiBase } from "./apiBase";

function wsUrl(path: string): string {
  return `${getApiBase().replace(/^http/, "ws")}${path}`;
}

/** How long to wait for the WS handshake before giving up (ms). */
const OPEN_TIMEOUT_MS = 15_000;

export interface DownloadHandlers {
  /** Called for each event (progress / completed / error). At most one
   * terminal event (`completed`/`error`) is ever delivered. */
  onEvent: (event: DownloadEvent) => void;
  /** Called when the socket closes *without* having delivered a terminal event
   * — i.e. an unexpected drop the caller should react to. Suppressed once a
   * terminal event has settled the download (or after `cancel()`). */
  onClose?: () => void;
}

export interface DownloadHandle {
  /** Close the socket; the in-flight job is left to finish on disk. */
  cancel: () => void;
}

/** Start a download and stream its progress events. */
export function startDownload(
  request: DownloadRequest,
  handlers: DownloadHandlers,
): DownloadHandle {
  const socket = new WebSocket(wsUrl("/ws/download"));
  let closed = false;
  let cancelled = false;
  let opened = false;
  let settled = false;

  // Deliver an event, enforcing at-most-one terminal callback: once a
  // `completed`/`error` has gone out the download is settled, so any later
  // frame (a buffered terminal event, a trailing progress tick, or the
  // close-driven error below) is dropped. This spares every caller from
  // hand-rolling its own `settled` guard against the terminal-then-close pair.
  const emit = (event: DownloadEvent) => {
    if (settled) return;
    if (event.type === "completed" || event.type === "error") settled = true;
    handlers.onEvent(event);
  };

  // Fail fast if the handshake never completes (backend still starting or
  // unreachable) instead of hanging on "downloading 0%" with no feedback.
  const openTimer = setTimeout(() => {
    if (opened || closed || cancelled) return;
    emit({
      type: "error",
      message: i18n.t("errors.downloadConnectionLost"),
    });
    closed = true;
    socket.close();
  }, OPEN_TIMEOUT_MS);

  socket.onopen = () => {
    opened = true;
    clearTimeout(openTimer);
    socket.send(JSON.stringify(request));
  };

  socket.onmessage = (message) => {
    // After a client-initiated cancel() the socket is closing but the browser
    // may still dispatch already-buffered frames. Dropping them here stops a
    // stale progress/terminal event from resurrecting a cancelled (or replaced)
    // download job in the caller's queue.
    if (cancelled) return;
    try {
      emit(JSON.parse(message.data as string) as DownloadEvent);
    } catch {
      // Ignore malformed frames rather than killing the download.
    }
  };

  socket.onerror = () => {
    if (closed) return;
    emit({
      type: "error",
      message: i18n.t("errors.downloadConnectionLost"),
    });
  };

  socket.onclose = () => {
    closed = true;
    clearTimeout(openTimer);
    // A client-initiated cancel() is intentional, and a terminal event already
    // settled the download; only report an otherwise-unexplained close so the
    // caller can react to an unexpected drop (and not stall).
    if (!cancelled && !settled) handlers.onClose?.();
  };

  return {
    cancel: () => {
      cancelled = true;
      closed = true;
      clearTimeout(openTimer);
      socket.close();
    },
  };
}
