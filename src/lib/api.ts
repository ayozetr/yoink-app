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
  WhatsNew,
} from "../types/download";
import type {
  ApplyRequest,
  ApplyResponse,
  CandidateList,
  LyricsResult,
} from "../types/autotag";
import type { MusicImportInfo, MusicTrack } from "../types/music";
import { getApiBase } from "./apiBase";

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
  return `${getApiBase()}/thumbnail?${params.toString()}`;
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
 * Shared `fetch` wrapper for every endpoint below.
 *
 * Maps a dropped/refused connection (which `fetch` rejects with a raw
 * `TypeError`) to a typed `ApiError(backendUnreachable)` so callers get a
 * consistent, translatable error instead of an opaque exception. An aborted
 * request is re-thrown untouched so callers can tell a cancellation apart. A
 * non-2xx response becomes an `ApiError` carrying the backend's `detail`.
 *
 * @throws {ApiError} on a network failure or a non-2xx response.
 */
async function request(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${getApiBase()}${path}`, init);
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw cause;
    }
    throw new ApiError(i18n.t("errors.backendUnreachable"), 0);
  }
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return response;
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
  const response = await request("/info", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
    signal,
  });
  return (await response.json()) as InfoResponse;
}

/** A supported music-service URL (Spotify/Deezer/Apple/Tidal/Amazon). */
export function isMusicUrl(value: string): boolean {
  return (
    /(?:open\.spotify\.com\/(?:intl-[a-z-]+\/)?|spotify:)(track|album|playlist)[/:]/i.test(value) ||
    /(?:deezer\.com|deezer\.page\.link)\/(?:[a-z]{2}\/)?(track|album|playlist)\//i.test(value) ||
    /(?:link\.deezer\.com|dzr\.page\.link)\//i.test(value) ||
    /music\.apple\.com\/(?:[a-z]{2}\/)?(album|song|playlist)\//i.test(value) ||
    /(?:tidal\.com|embed\.tidal\.com|listen\.tidal\.com)\/(?:browse\/)?(track|album|playlist)s?\//i.test(value) ||
    /music\.amazon\.[a-z.]+\/(albums|tracks|playlists|user-playlists)\//i.test(value)
  );
}

/** Resolve a music-service URL into its tracklist (keyless). */
export async function resolveMusic(
  url: string,
  signal?: AbortSignal,
): Promise<MusicImportInfo> {
  const response = await request("/music/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
    signal,
  });
  return (await response.json()) as MusicImportInfo;
}

/** One track's cover art + duration via a keyless (server-paced) Deezer lookup —
 * for filling a non-enriched playlist's covers lazily, row by row. */
export async function getTrackMeta(
  track: MusicTrack,
  signal?: AbortSignal,
): Promise<{ cover_url: string | null; duration_ms: number | null }> {
  const response = await request("/music/cover", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(track),
    signal,
  });
  return (await response.json()) as {
    cover_url: string | null;
    duration_ms: number | null;
  };
}

/** Find the best-ranked YouTube video URL for a track (null if none). */
export async function matchMusic(
  track: MusicTrack,
  signal?: AbortSignal,
): Promise<string | null> {
  const response = await request("/music/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(track),
    signal,
  });
  const data = (await response.json()) as { youtube_url: string | null };
  return data.youtube_url;
}

/** Platform the URL-field typeahead searches. */
export type SearchSource = "youtube" | "soundcloud";

/** Flat search (YouTube or SoundCloud) for the URL-field typeahead via
 * `GET /api/search`. */
export async function searchYoutube(
  query: string,
  source: SearchSource = "youtube",
  signal?: AbortSignal,
): Promise<PlaylistEntry[]> {
  const response = await request(
    `/search?q=${encodeURIComponent(query)}&source=${source}`,
    { signal },
  );
  return ((await response.json()) as SearchResponse).results;
}

/** The running backend's app version (+ update check), via `GET /api/version`.
 * Compared against the frontend's `__APP_VERSION__` to catch a stale backend
 * left running after a self-update. */
export async function fetchAppVersion(
  signal?: AbortSignal,
): Promise<VersionInfo> {
  const response = await request("/version", { signal });
  return (await response.json()) as VersionInfo;
}

/** The bundled yt-dlp version + whether a newer one is published, via
 * `GET /api/ytdlp-version`. */
export async function fetchYtdlpVersion(
  signal?: AbortSignal,
): Promise<VersionInfo> {
  const response = await request("/ytdlp-version", { signal });
  return (await response.json()) as VersionInfo;
}

/**
 * "What's new" notes for the after-update popup, via `GET /api/release-notes`.
 * Passing `since` (the version last run) makes it cumulative — every release
 * newer than it, up to the current version, newest first.
 */
export async function fetchWhatsNew(
  since: string | null,
  signal?: AbortSignal,
): Promise<WhatsNew> {
  const query = since ? `?since=${encodeURIComponent(since)}` : "";
  const response = await request(`/release-notes${query}`, { signal });
  return (await response.json()) as WhatsNew;
}

/** Fetch recent download records via `GET /api/history`. */
export async function fetchHistory(
  signal?: AbortSignal,
): Promise<HistoryEntry[]> {
  const response = await request("/history", { signal });
  return (await response.json()) as HistoryEntry[];
}

/** Fetch aggregate download statistics via `GET /api/history/stats`. */
export async function fetchStats(signal?: AbortSignal): Promise<DownloadStats> {
  const response = await request("/history/stats", { signal });
  return (await response.json()) as DownloadStats;
}

/** Delete all download history via `DELETE /api/history`. */
export async function clearHistory(): Promise<void> {
  await request("/history", { method: "DELETE" });
}

/** Reveal a file/folder in the OS file manager via `POST /api/open`. With
 * `openFile`, the file itself is opened with its default app. */
export async function openInFileManager(
  path?: string | null,
  openFile = false,
): Promise<void> {
  await request("/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: path ?? null, open_file: openFile }),
  });
}

/** URL of a downloaded file's embedded cover art (the endpoint 404s if none).
 * `version` is an optional cache-buster so a freshly-tagged file re-fetches. */
export function coverUrl(path: string, version?: number): string {
  const bust = version != null ? `&v=${version}` : "";
  return `${getApiBase()}/cover?path=${encodeURIComponent(path)}${bust}`;
}

/** Fetch the current settings via `GET /api/settings`. */
export async function fetchSettings(signal?: AbortSignal): Promise<AppSettings> {
  const response = await request("/settings", { signal });
  return (await response.json()) as AppSettings;
}

/** Persist new settings via `PUT /api/settings`; returns the effective values. */
export async function updateSettings(
  payload: AppSettings,
): Promise<AppSettings> {
  const response = await request("/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await response.json()) as AppSettings;
}

/** Match a downloaded audio file via `POST /api/autotag/identify`. */
export async function identifyAudio(
  path: string,
  signal?: AbortSignal,
): Promise<CandidateList> {
  const response = await request("/autotag/identify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
    signal,
  });
  return (await response.json()) as CandidateList;
}

/** Manual Apple Music search via `POST /api/autotag/search`. */
export async function searchAudio(
  artist: string,
  title: string,
  signal?: AbortSignal,
): Promise<CandidateList> {
  const response = await request("/autotag/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ artist, title }),
    signal,
  });
  return (await response.json()) as CandidateList;
}

/** Write the chosen tags + cover into the file via `POST /api/autotag/apply`. */
export async function applyAudioTags(
  payload: ApplyRequest,
): Promise<ApplyResponse> {
  const response = await request("/autotag/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await response.json()) as ApplyResponse;
}

/** Preview lyrics availability for a track via `POST /api/autotag/lyrics`. */
export async function previewLyrics(payload: {
  title: string;
  artist?: string;
  album?: string | null;
  path?: string;
}): Promise<LyricsResult> {
  const response = await request("/autotag/lyrics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await response.json()) as LyricsResult;
}
