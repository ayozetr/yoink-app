/**
 * Typed client for the local Yoink FastAPI backend.
 *
 * The base URL can be overridden with `VITE_API_BASE_URL` (e.g. when the
 * backend runs on a non-default port); it defaults to the local uvicorn server.
 */

import type {
  DownloadStats,
  HistoryEntry,
  VideoInfo,
} from "../types/download";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

/** Error carrying the HTTP status alongside a human-readable message. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Extract a `detail` message from a FastAPI error response, if present. */
async function readErrorDetail(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (
      data &&
      typeof data === "object" &&
      "detail" in data &&
      typeof (data as { detail: unknown }).detail === "string"
    ) {
      return (data as { detail: string }).detail;
    }
  } catch {
    // Body was not JSON — fall through to the generic message.
  }
  return `La petición falló (${response.status}).`;
}

/**
 * Fetch clean metadata for a media URL via `POST /api/info`.
 *
 * @throws {ApiError} when the backend rejects the URL or is unreachable.
 */
export async function fetchVideoInfo(
  url: string,
  signal?: AbortSignal,
): Promise<VideoInfo> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/info`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw cause;
    }
    throw new ApiError(
      "No se pudo conectar con el backend. ¿Está corriendo en el puerto 8000?",
      0,
    );
  }

  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }

  return (await response.json()) as VideoInfo;
}

/** Fetch recent download records via `GET /api/history`. */
export async function fetchHistory(
  signal?: AbortSignal,
): Promise<HistoryEntry[]> {
  const response = await fetch(`${API_BASE_URL}/history`, { signal });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as HistoryEntry[];
}

/** Fetch aggregate download statistics via `GET /api/history/stats`. */
export async function fetchStats(signal?: AbortSignal): Promise<DownloadStats> {
  const response = await fetch(`${API_BASE_URL}/history/stats`, { signal });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as DownloadStats;
}

/** Reveal a file/folder in the OS file manager via `POST /api/open`. */
export async function openInFileManager(path?: string | null): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: path ?? null }),
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
}
