/**
 * Derive the user-facing format & quality selectors from the real list of
 * yt-dlp formats, instead of hard-coded placeholders.
 */

import type {
  AudioFormat,
  MediaFormat,
  MediaKind,
  VideoContainer,
  VideoInfo,
} from "../../types/download";

export interface KindOption {
  kind: MediaKind;
}

/** Output video containers offered as merge targets, in display order. */
export const VIDEO_CONTAINERS: { value: VideoContainer; label: string }[] = [
  { value: "mp4", label: "MP4" },
  { value: "mov", label: "MOV" },
  { value: "mkv", label: "MKV" },
];

/** Default video container (mirrors the backend default). */
export const DEFAULT_CONTAINER: VideoContainer = "mp4";

export interface AudioFormatOption {
  value: AudioFormat;
  label: string;
  /** True for formats that only make sense from a lossless source (flac/wav). */
  lossless: boolean;
}

/** Output audio formats offered for audio-only downloads, in display order. */
export const AUDIO_FORMATS: AudioFormatOption[] = [
  { value: "mp3", label: "MP3", lossless: false },
  { value: "m4a", label: "M4A", lossless: false },
  { value: "flac", label: "FLAC", lossless: true },
  { value: "wav", label: "WAV", lossless: true },
];

/** Default audio format (mirrors the backend default). */
export const DEFAULT_AUDIO_FORMAT: AudioFormat = "mp3";

/** Pull a pixel height out of a yt-dlp resolution/note string. */
function formatHeight(format: MediaFormat): number | null {
  const source = format.resolution ?? "";
  const wxh = source.match(/\d+\s*[x×]\s*(\d+)/i);
  if (wxh) return Number(wxh[1]);
  const p = source.match(/(\d+)\s*p/i);
  if (p) return Number(p[1]);
  return null;
}

/**
 * Which media kinds can be produced from these formats. Audio is always
 * offered when an audio track exists (yt-dlp can extract it to MP3).
 */
export function availableKinds(info: VideoInfo): KindOption[] {
  const hasVideo = info.formats.some((format) => format.has_video);
  const hasAudio = info.formats.some((format) => format.has_audio);

  const options: KindOption[] = [];
  if (hasVideo) options.push({ kind: "video" });
  if (hasAudio) options.push({ kind: "audio" });

  // Fall back to a video option so the selector is never empty.
  return options.length > 0 ? options : [{ kind: "video" }];
}

/**
 * Distinct video qualities (e.g. "1080p", "720p"), highest first. Returns an
 * empty list when the URL only exposes audio.
 */
export function videoQualities(info: VideoInfo): string[] {
  const heights = new Set<number>();
  for (const format of info.formats) {
    if (!format.has_video) continue;
    const height = formatHeight(format);
    if (height) heights.add(height);
  }
  return [...heights].sort((a, b) => b - a).map((height) => `${height}p`);
}
