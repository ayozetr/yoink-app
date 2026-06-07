/**
 * Typed client for the local Yoink FastAPI backend.
 *
 * The base URL can be overridden with `VITE_API_BASE_URL` (e.g. when the
 * backend runs on a non-default port); it defaults to the local uvicorn server.
 */

import i18n from "../i18n";
import type {
  AppSettings,
  DownloadStats,
  HistoryEntry,
  InfoResponse,
  PlaylistEntry,
  SearchResponse,
  VersionInfo,
} from "../types/download";
import type {
  ApplyRequest,
  ApplyResponse,
  CandidateList,
} from "../types/autotag";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8756/api";

/**
 * Build a URL that proxies a remote thumbnail through the local backend.
 *
 * Some source CDNs (e.g. Instagram's cdninstagram/fbcdn) block hotlinking of
 * their images from another origin, so a direct `<img src>` fails. Routing the
 * request through `GET /api/thumbnail` re-serves the bytes from localhost.
 *
 * `referer` is forwarded as the upstream `Referer` header — some CDNs
 * hotlink-protect by Referer and 403 without it; pass the page URL.
 */
export function thumbnailProxyUrl(
  remoteUrl: string,
  referer?: string | null,
): string {
  const params = new URLSearchParams({ url: remoteUrl });
  if (referer) params.set("referer", referer);
  return `${API_BASE_URL}/thumbnail?${params.toString()}`;
}

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
      typeof data.detail === "string"
    ) {
      return (data as { detail: string }).detail;
    }
  } catch {
    // Body was not JSON — fall through to the generic message.
  }
  return i18n.t("errors.requestFailed", { status: response.status });
}

/**
 * Fetch clean metadata for a media URL via `POST /api/info`.
 *
 * Returns either a single video or a playlist listing.
 *
 * @throws {ApiError} when the backend rejects the URL or is unreachable.
 */
export async function fetchInfo(
  url: string,
  signal?: AbortSignal,
): Promise<InfoResponse> {
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
    throw new ApiError(i18n.t("errors.backendUnreachable"), 0);
  }

  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }

  return (await response.json()) as InfoResponse;
}

/** Flat YouTube search for the URL-field typeahead via `GET /api/search`. */
export async function searchYoutube(
  query: string,
  signal?: AbortSignal,
): Promise<PlaylistEntry[]> {
  const response = await fetch(
    `${API_BASE_URL}/search?q=${encodeURIComponent(query)}`,
    { signal },
  );
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return ((await response.json()) as SearchResponse).results;
}

/** The bundled yt-dlp version + whether a newer one is published, via
 * `GET /api/ytdlp-version`. */
export async function fetchYtdlpVersion(
  signal?: AbortSignal,
): Promise<VersionInfo> {
  const response = await fetch(`${API_BASE_URL}/ytdlp-version`, { signal });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as VersionInfo;
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

/** Delete all download history via `DELETE /api/history`. */
export async function clearHistory(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/history`, { method: "DELETE" });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
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

/** Fetch the current settings via `GET /api/settings`. */
export async function fetchSettings(signal?: AbortSignal): Promise<AppSettings> {
  const response = await fetch(`${API_BASE_URL}/settings`, { signal });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as AppSettings;
}

/** Persist new settings via `PUT /api/settings`; returns the effective values. */
export async function updateSettings(
  payload: AppSettings,
): Promise<AppSettings> {
  const response = await fetch(`${API_BASE_URL}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as AppSettings;
}

/** Match a downloaded audio file via `POST /api/autotag/identify`. */
export async function identifyAudio(
  path: string,
  signal?: AbortSignal,
): Promise<CandidateList> {
  const response = await fetch(`${API_BASE_URL}/autotag/identify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
    signal,
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as CandidateList;
}

/** Manual Apple Music search via `POST /api/autotag/search`. */
export async function searchAudio(
  artist: string,
  title: string,
  signal?: AbortSignal,
): Promise<CandidateList> {
  const response = await fetch(`${API_BASE_URL}/autotag/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ artist, title }),
    signal,
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as CandidateList;
}

/** Write the chosen tags + cover into the file via `POST /api/autotag/apply`. */
export async function applyAudioTags(
  request: ApplyRequest,
): Promise<ApplyResponse> {
  const response = await fetch(`${API_BASE_URL}/autotag/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as ApplyResponse;
}
