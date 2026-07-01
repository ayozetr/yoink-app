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
  VRLayout,
} from "../../types/download";

/** Stereo/projection layouts offered for VR tagging (technical, untranslated). */
export const VR_LAYOUTS: { value: VRLayout; label: string }[] = [
  { value: "180_sbs", label: "180° · SBS" },
  { value: "180_tb", label: "180° · TB" },
  { value: "180_mono", label: "180° · Mono" },
  { value: "360_sbs", label: "360° · SBS" },
  { value: "360_tb", label: "360° · TB" },
  { value: "360_mono", label: "360° · Mono" },
  { value: "fisheye190", label: "Fisheye 190°" },
  { value: "fisheye200", label: "Fisheye 200°" },
  { value: "mkx200", label: "MKX200" },
  { value: "mkx220", label: "MKX220" },
  { value: "rf52", label: "Canon RF5.2" },
];

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

/** Standard quality tiers (vertical resolution), used to label + match formats. */
const QUALITY_TIERS = [144, 240, 360, 480, 720, 1080, 1440, 2160, 4320];

/** Snap a raw pixel value to the nearest standard tier (rounds off encoder noise). */
function snapToTier(value: number): number {
  return QUALITY_TIERS.reduce((best, tier) =>
    Math.abs(tier - value) < Math.abs(best - value) ? tier : best,
  );
}

/** Whether these formats come from YouTube, whose quality labels are the tier
 *  (so an ultrawide 1920×818 is "1080p"). Only there do we normalise to tiers —
 *  other sites keep their raw pixel height so we don't relabel them wrongly. */
function isYoutube(info: VideoInfo): boolean {
  return /youtube/i.test(info.extractor ?? "");
}

/**
 * The quality height for a format. For YouTube (`normalize`) it's the standard
 * tier the frame fits into — for a wide frame `width × 9/16` (so an ultrawide
 * 1920×818 is "1080p", not "818p"), for a tall / 4:3 one the shorter side;
 * `max()` of the two covers every aspect ratio. For other sites it's the raw
 * pixel height, unchanged.
 */
function formatHeight(format: MediaFormat, normalize: boolean): number | null {
  const source = format.resolution ?? "";
  const wxh = source.match(/(\d+)\s*[x×]\s*(\d+)/i);
  if (wxh) {
    const w = Number(wxh[1]);
    const h = Number(wxh[2]);
    if (!normalize) return h;
    return snapToTier(Math.max(Math.min(w, h), Math.round((Math.max(w, h) * 9) / 16)));
  }
  const p = source.match(/(\d+)\s*p/i);
  if (p) return normalize ? snapToTier(Number(p[1])) : Number(p[1]);
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
  const normalize = isYoutube(info);
  const heights = new Set<number>();
  for (const format of info.formats) {
    if (!format.has_video) continue;
    const height = formatHeight(format, normalize);
    if (height) heights.add(height);
  }
  return [...heights].sort((a, b) => b - a).map((height) => `${height}p`);
}

/** Largest known size among audio-only formats, in bytes (or null). */
function bestAudioOnlyBytes(info: VideoInfo): number | null {
  let best: number | null = null;
  for (const format of info.formats) {
    if (format.has_audio && !format.has_video && format.filesize != null) {
      if (best == null || format.filesize > best) best = format.filesize;
    }
  }
  return best;
}

/**
 * Rough estimated download size in bytes for the chosen kind/quality, or null
 * when sizes aren't known. For video it pairs the best matching video stream
 * with the best audio-only stream (unless the match is already progressive).
 * Approximate by nature — yt-dlp's final selection can differ.
 *
 * For audio it returns the source stream size, which only resembles the output
 * for lossy formats (mp3/m4a). Lossless output (flac/wav) is far larger than
 * the compressed source, so we return null there rather than show a wrong size.
 */
export function estimatedSizeBytes(
  info: VideoInfo,
  kind: MediaKind,
  quality: string | undefined,
  audioFormat?: AudioFormat,
): number | null {
  if (kind === "audio") {
    if (audioFormat === "flac" || audioFormat === "wav") return null;
    return bestAudioOnlyBytes(info);
  }

  const target = quality ? Number.parseInt(quality, 10) : NaN;
  const normalize = isYoutube(info);
  let videoBytes: number | null = null;
  let progressive = false;
  for (const format of info.formats) {
    if (!format.has_video || format.filesize == null) continue;
    const height = formatHeight(format, normalize);
    if (Number.isFinite(target) && height !== target) continue;
    if (videoBytes == null || format.filesize > videoBytes) {
      videoBytes = format.filesize;
      progressive = format.has_audio;
    }
  }
  if (videoBytes == null) return null;
  if (progressive) return videoBytes;
  const audio = bestAudioOnlyBytes(info);
  return audio != null ? videoBytes + audio : videoBytes;
}

/** A compact, locale-formatted duration: "1h 18m" / "18m" / "45s" (units via
 * Intl, so they read correctly in every language instead of hardcoded h/m/s). */
export function formatDuration(totalSeconds: number, lang: string): string {
  const unit = (value: number, u: "hour" | "minute" | "second") =>
    new Intl.NumberFormat(lang, {
      style: "unit",
      unit: u,
      unitDisplay: "narrow",
    }).format(value);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (hours) return `${unit(hours, "hour")} ${unit(minutes, "minute")}`;
  if (minutes) return unit(minutes, "minute");
  return unit(totalSeconds, "second");
}
