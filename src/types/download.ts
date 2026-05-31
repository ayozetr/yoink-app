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

/** Real-time progress reported by yt-dlp progress_hooks over WS/SSE. */
export interface DownloadProgress {
  percent: number;
  /** Human-readable speed, e.g. "3 MB/s". */
  speed: string;
}

/** Aggregate stats shown at the bottom of the sidebar. */
export interface DownloadStats {
  totalDownloads: number;
  transferred: string;
}
