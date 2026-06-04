/**
 * WebSocket client for the live download endpoint (`/api/ws/download`).
 *
 * Opens a socket, sends the download request, and forwards every event the
 * backend streams back. The WS URL is derived from the same base as the REST
 * client (`VITE_API_BASE_URL`) by swapping the `http`/`https` scheme.
 */

import i18n from "../i18n";
import type { DownloadEvent, DownloadRequest } from "../types/download";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8756/api";

function wsUrl(path: string): string {
  return `${API_BASE_URL.replace(/^http/, "ws")}${path}`;
}

export interface DownloadHandlers {
  /** Called for each event (progress / completed / error). */
  onEvent: (event: DownloadEvent) => void;
  /** Called once when the socket closes, whatever the reason. */
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

  socket.onopen = () => socket.send(JSON.stringify(request));

  socket.onmessage = (message) => {
    try {
      handlers.onEvent(JSON.parse(message.data) as DownloadEvent);
    } catch {
      // Ignore malformed frames rather than killing the download.
    }
  };

  socket.onerror = () => {
    if (closed) return;
    handlers.onEvent({
      type: "error",
      message: i18n.t("errors.downloadConnectionLost"),
    });
  };

  socket.onclose = () => {
    closed = true;
    // A client-initiated cancel() is intentional; only report server-side
    // closes so the caller can react to an unexpected drop (and not stall).
    if (!cancelled) handlers.onClose?.();
  };

  return {
    cancel: () => {
      cancelled = true;
      closed = true;
      socket.close();
    },
  };
}
