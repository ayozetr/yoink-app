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

/** Metadata extracted from a URL via yt-dlp (download=False). */
export interface VideoInfo {
  title: string;
  /** Human-readable duration, e.g. "1h 24m 18s". */
  duration: string;
  thumbnailUrl?: string;
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
