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

/** Stereo/projection layout for immersive (VR) video (mirrors backend `VRLayout`). */
export type VRLayout =
  | "180_sbs"
  | "180_tb"
  | "180_mono"
  | "360_sbs"
  | "360_tb"
  | "360_mono"
  | "fisheye190"
  | "fisheye200"
  | "mkx200"
  | "mkx220"
  | "rf52";

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
  /** Resolution (video, e.g. "1080p") or bitrate/format (audio, e.g. "320 kbps"). */
  quality: string | null;
  /** Failure reason when status is "error". */
  error_message: string | null;
  created_at: string;
  /** Output file's last-modified time (epoch seconds), for per-row cover cache-busting. */
  mtime: number | null;
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
  /** Clock-formatted duration, e.g. "1:24:18" or "0:05". */
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
  /** False when the source exposes no audio at all (video-only — silent). */
  has_audio: boolean;
  /** Published (manual) subtitle language codes. */
  subtitle_langs: string[];
  /** Auto-generated caption codes (not already in subtitle_langs). */
  auto_caption_langs: string[];
  /** Whether the source exposes chapter markers. */
  has_chapters: boolean;
  /** Languages of the available audio tracks (>1 means multi-audio). */
  audio_langs: string[];
  /** Heuristically detected as immersive (VR) video. */
  is_vr: boolean;
  /** Suggested stereo/projection layout (seeds the VR toggle). */
  vr_layout: VRLayout;
}

/** One flat item inside a playlist (mirrors backend `PlaylistEntry`). */
export interface PlaylistEntry {
  id: string;
  title: string;
  url: string;
  duration_string: string | null;
  thumbnail_url: string | null;
  uploader: string | null;
  view_count: number | null;
  /** URL already a completed download — pre-selected off (playlist sync). */
  already_downloaded: boolean;
}

/** Flat YouTube search results for the URL-field typeahead (mirrors backend). */
export interface SearchResponse {
  results: PlaylistEntry[];
}

/** Flat playlist metadata (mirrors backend `PlaylistInfo`). */
export interface PlaylistInfo {
  id: string;
  title: string;
  uploader: string | null;
  /** Playlist cover (or the first entry's thumbnail). */
  thumbnail_url: string | null;
  entry_count: number;
  entries: PlaylistEntry[];
  truncated: boolean;
  /** Probed from the first entry (assumes a homogeneous playlist). */
  source_lossless: boolean;
  best_audio_abr: number | null;
  /** Heuristically detected as a VR playlist (title/channel). */
  is_vr: boolean;
  /** Suggested layout to tag the whole batch with. */
  vr_layout: VRLayout;
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
  /** Video or audio. Defaults to "video" on the backend when omitted. */
  kind?: MediaKind;
  /** Target video quality, e.g. "1080p". Omitted for audio. */
  quality?: string;
  /** Output container when kind=video (merge target). Defaults to "mp4". */
  container?: VideoContainer;
  /** Output format when kind=audio. Defaults to "mp3". */
  audio_format?: AudioFormat;
  /** Embed subtitles into the video output when available. */
  embed_subs?: boolean;
  /** Subtitle language to embed: a code like "en"/"es", "all", or omitted. */
  subtitle_lang?: string;
  /** Embed chapter markers + metadata when the source has them. */
  embed_chapters?: boolean;
  /** Include all audio tracks (multi-language) in the video output. */
  audio_multistreams?: boolean;
  /** Clip start/end in seconds — download only that range. */
  trim_start?: number;
  trim_end?: number;
  /** Tag the output as immersive VR (name suffix + spherical metadata). */
  is_vr?: boolean;
  /** Stereo/projection layout to tag with when is_vr is set. */
  vr_layout?: VRLayout;
  /** Auto-detect + tag VR during the download (used by the queue, no preview). */
  auto_vr?: boolean;
  /** Client-estimated final size (bytes), for the pre-flight disk check. */
  estimated_size?: number;
  /** Override %(title)s in the output filename (single wrapped story/post item). */
  output_title?: string | null;
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

/** Catalogue used by the audio auto-tagger. */
export type AutotagSource = "auto" | "apple" | "deezer" | "musicbrainz";
export type SponsorblockAction = "remove" | "mark";
export type VideoCodec = "any" | "h264" | "vp9" | "av1";
export type AudioBitrate = "best" | "320" | "256" | "192" | "128";

/** User-editable settings (mirrors backend `AppSettings`). */
export interface AppSettings {
  download_dir: string;
  default_kind: MediaKind;
  default_quality: string;
  default_container: VideoContainer;
  default_audio_format: AudioFormat;
  /** Seed the subtitle picker to embed subs by default (when the container allows). */
  default_embed_subs: boolean;
  /** Seed new video downloads to embed chapter markers by default. */
  default_embed_chapters: boolean;
  /** Write a Kodi/Jellyfin-style .nfo metadata file next to each download. */
  nfo_sidecars: boolean;
  /** Fetch + embed song lyrics (LRCLIB) during audio auto-tagging. */
  fetch_lyrics: boolean;
  /** Also write a synced .lrc sidecar next to the audio. */
  lyrics_lrc: boolean;
  cookies_from_browser: string | null;
  cookies_file: string | null;
  /** Proxy URL (http/https/socks) for metadata + downloads; null = none. */
  proxy: string | null;
  autotag_source: AutotagSource;
  sponsorblock_enabled: boolean;
  sponsorblock_action: SponsorblockAction;
  /** yt-dlp output name template (extension appended by the backend). */
  filename_template: string;
  /** Download speed cap like "1M"/"500K"; null means no cap. */
  rate_limit: string | null;
  /** Preferred video codec ("any" = no preference). */
  video_codec: VideoCodec;
  /** Lossy audio bitrate in kbps, or "best". */
  audio_bitrate: AudioBitrate;
  /** Loudness-normalize audio to -14 LUFS so every track plays at one volume. */
  normalize_audio: boolean;
  /** Check GitHub for a newer app release on launch (opt-in; the app only). */
  check_updates: boolean;
  /** Send a desktop notification when a download finishes. */
  notify_on_complete: boolean;
  /** Desktop app: closing the window hides it to the system tray. */
  minimize_to_tray: boolean;
  /** Desktop app: launch Yoink when the system starts. */
  launch_at_startup: boolean;
  /** Desktop app: disable the global shortcut (on by default — opt in by turning off). */
  disable_global_hotkeys: boolean;
}

/** A release's "what's new" notes for the after-update popup (mirrors backend). */
export interface ReleaseNotes {
  version: string;
  /** Markdown notes, trimmed to the what's-new part; null if unavailable. */
  notes: string | null;
}

/** Aggregate stats shown at the bottom of the sidebar (mirrors backend). */
export interface DownloadStats {
  total_downloads: number;
  total_bytes: number;
  /** Human-readable total, e.g. "182 GB". */
  transferred: string;
}
