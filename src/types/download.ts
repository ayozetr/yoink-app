/**
 * Shared domain types for the Yoink downloader.
 *
 * These mirror the JSON contract that the FastAPI backend (yt-dlp wrapper)
 * will eventually return, so the UI is already shaped around the real data.
 */

export type DownloadStatus = "completed" | "error" | "downloading" | "queued";

export type MediaKind = "video" | "audio";

/** Output container for a video download (mirrors backend `VideoContainer`). */
export type VideoContainer = "mp4" | "mov" | "mkv";

/**
 * Output format for an audio-only download (mirrors backend `AudioFormat`).
 * mp3/m4a are lossy; flac/wav are lossless and only meaningful when the source
 * itself is lossless.
 */
export type AudioFormat = "mp3" | "m4a" | "flac" | "wav";

/** Final outcome persisted in the history (mirrors backend `HistoryStatus`). */
export type HistoryStatus = "completed" | "error";

/** A persisted download record (mirrors backend `HistoryEntry`). */
export interface HistoryEntry {
  id: number;
  title: string;
  url: string;
  kind: MediaKind;
  status: HistoryStatus;
  filename: string | null;
  filepath: string | null;
  filesize: number | null;
  created_at: string;
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
  /** True if the best audio source is lossless (flac/alac/wav/pcm/…). */
  source_lossless: boolean;
  /** Highest audio bitrate available, in kbps. */
  best_audio_abr: number | null;
}

/** One flat item inside a playlist (mirrors backend `PlaylistEntry`). */
export interface PlaylistEntry {
  id: string;
  title: string;
  url: string;
  duration_string: string | null;
  thumbnail_url: string | null;
  uploader: string | null;
}

/** Flat playlist metadata (mirrors backend `PlaylistInfo`). */
export interface PlaylistInfo {
  id: string;
  title: string;
  uploader: string | null;
  entry_count: number;
  entries: PlaylistEntry[];
  truncated: boolean;
}

/** Unified `/api/info` result: a single video or a playlist. */
export interface InfoResponse {
  type: "video" | "playlist";
  video: VideoInfo | null;
  playlist: PlaylistInfo | null;
}

/** What the frontend asks to download (mirrors backend `DownloadRequest`). */
export interface DownloadRequest {
  url: string;
  kind: MediaKind;
  /** Target video quality, e.g. "1080p". Omitted for audio. */
  quality?: string;
  /** Output container when kind=video (merge target). Defaults to "mp4". */
  container?: VideoContainer;
  /** Output format when kind=audio. Defaults to "mp3". */
  audio_format?: AudioFormat;
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

/** Version + update-check result (mirrors backend `VersionInfo`). */
export interface VersionInfo {
  current: string;
  latest: string | null;
  update_available: boolean;
  release_url: string | null;
  error: string | null;
}

/** User-editable settings (mirrors backend `AppSettings`). */
export interface AppSettings {
  download_dir: string;
  default_kind: MediaKind;
  default_quality: string;
  cookies_from_browser: string | null;
  cookies_file: string | null;
}

/** Aggregate stats shown at the bottom of the sidebar (mirrors backend). */
export interface DownloadStats {
  total_downloads: number;
  total_bytes: number;
  /** Human-readable total, e.g. "182 GB". */
  transferred: string;
}
