/**
 * Shared domain types for the Yoink downloader.
 *
 * These mirror the JSON contract that the FastAPI backend (yt-dlp wrapper)
 * will eventually return, so the UI is already shaped around the real data.
 */

export type DownloadStatus = "completed" | "error" | "downloading" | "queued";

export type MediaKind = "video" | "audio";

/** A single entry in the download history sidebar. */
export interface HistoryItem {
  id: number;
  title: string;
  status: DownloadStatus;
  kind: MediaKind;
}

/**
 * A single downloadable format reported by yt-dlp.
 *
 * Mirrors `MediaFormat` in `backend/app/models/media.py`. The JSON travels
 * over the wire in snake_case, so these field names match it 1:1.
 */
export interface MediaFormat {
  format_id: string;
  ext: string;
  resolution: string | null;
  fps: number | null;
  vcodec: string | null;
  acodec: string | null;
  filesize: number | null;
  has_video: boolean;
  has_audio: boolean;
}

/**
 * Metadata extracted from a URL via yt-dlp (download=False).
 *
 * Mirrors `VideoInfo` in `backend/app/models/media.py`.
 */
export interface VideoInfo {
  id: string;
  title: string;
  /** Duration in seconds, when known. */
  duration: number | null;
  /** Human-readable duration, e.g. "1h 24m 18s". */
  duration_string: string | null;
  uploader: string | null;
  thumbnail_url: string | null;
  webpage_url: string | null;
  extractor: string | null;
  formats: MediaFormat[];
}

/** What the frontend asks to download (mirrors backend `DownloadRequest`). */
export interface DownloadRequest {
  url: string;
  kind: MediaKind;
  /** Target video quality, e.g. "1080p". Omitted for audio. */
  quality?: string;
}

/** Live progress while yt-dlp downloads (mirrors backend `ProgressEvent`). */
export interface DownloadProgressEvent {
  type: "progress";
  status: "downloading" | "processing";
  percent: number;
  downloaded_bytes: number | null;
  total_bytes: number | null;
  speed: string | null;
  eta: string | null;
  filename: string | null;
}

/** Terminal success event (mirrors backend `CompletedEvent`). */
export interface DownloadCompletedEvent {
  type: "completed";
  filename: string;
  filepath: string;
  total_bytes: number | null;
}

/** Terminal failure event (mirrors backend `ErrorEvent`). */
export interface DownloadErrorEvent {
  type: "error";
  message: string;
}

/** Any event streamed over the download WebSocket. */
export type DownloadEvent =
  | DownloadProgressEvent
  | DownloadCompletedEvent
  | DownloadErrorEvent;

/** Aggregate stats shown at the bottom of the sidebar. */
export interface DownloadStats {
  totalDownloads: number;
  transferred: string;
}
