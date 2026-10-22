// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

/**
 * Derive the user-facing format & quality selectors from the real list of
 * yt-dlp formats, instead of hard-coded placeholders.
 */

import type {
  AudioFormat,
  MediaFormat,
  MediaKind,
  VideoCodec,
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
  { value: "webm", label: "WebM" },
];

/** Default video container (mirrors the backend default). */
export const DEFAULT_CONTAINER: VideoContainer = "mp4";

/** Friendly labels for the video codecs offered in the picker. */
export const VIDEO_CODEC_LABELS: Record<Exclude<VideoCodec, "any">, string> = {
  h264: "H.264",
  h265: "H.265",
  vp9: "VP9",
  av1: "AV1",
};

/**
 * Which video codecs each container can hold without re-encoding. A forced
 * codec outside this set means ffmpeg must re-encode the video (slow) or the
 * mux may fail — we warn the user. MKV is universal; WebM is VP9/AV1 only.
 */
const CONTAINER_CODECS: Record<VideoContainer, Exclude<VideoCodec, "any">[]> = {
  mp4: ["h264", "h265", "av1"],
  mov: ["h264", "h265"],
  mkv: ["h264", "h265", "vp9", "av1"],
  webm: ["vp9", "av1"],
};

/** Whether a (forced) codec muxes natively into the container ("any" always fits). */
export function codecFitsContainer(
  container: VideoContainer,
  codec: VideoCodec,
): boolean {
  if (codec === "any") return true;
  return CONTAINER_CODECS[container]?.includes(codec) ?? true;
}

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
  { value: "opus", label: "Opus", lossless: false },
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

/**
 * yt-dlp's default video-codec preference, best first (mirrors FormatSorter's
 * `vcodec` order). Each entry maps a raw `vcodec` string (e.g. "av01.0.08M.08",
 * "avc1.640028") to a friendly name and its rank.
 */
const VCODEC_RANK: { re: RegExp; name: string }[] = [
  { re: /^av0?1/i, name: "AV1" },
  { re: /^vp0?9\.0?2/i, name: "VP9" },
  { re: /^vp0?9/i, name: "VP9" },
  { re: /^([hx]265|he?vc?)/i, name: "H.265" },
  { re: /^([hx]264|avc)/i, name: "H.264" },
  { re: /^vp0?8/i, name: "VP8" },
  { re: /^(mp4v|h263)/i, name: "H.263" },
  { re: /^theora/i, name: "Theora" },
];

/** Rank a raw vcodec string (lower rank = more preferred by yt-dlp's default). */
function rankVcodec(vcodec: string): { name: string; rank: number } {
  const i = VCODEC_RANK.findIndex((e) => e.re.test(vcodec));
  if (i >= 0) return { name: VCODEC_RANK[i].name, rank: i };
  return { name: vcodec.split(/[.\s]/)[0].toUpperCase(), rank: 99 };
}

/**
 * Predict which video codec yt-dlp would actually pick for the chosen quality
 * when no codec is forced ("best available"). Mirrors yt-dlp's default sort:
 * within the target resolution, prefer the highest fps, then the best codec by
 * {@link VCODEC_RANK}. Returns a friendly name ("AV1", "VP9", …) or null when
 * the formats don't expose a codec.
 */
export function bestAvailableCodec(
  info: VideoInfo,
  quality: string | undefined,
): string | null {
  const normalize = isYoutube(info);
  const target = quality ? Number.parseInt(quality, 10) : NaN;
  let candidates = info.formats.filter((f) => f.has_video && f.vcodec);
  if (candidates.length === 0) return null;

  // Narrow to the chosen resolution tier (or the best one at/below it; without a
  // target, the highest resolution overall) — yt-dlp sorts by `res` first.
  const heightOf = (f: MediaFormat) => formatHeight(f, normalize) ?? 0;
  if (Number.isFinite(target)) {
    const atTier = candidates.filter((f) => heightOf(f) === target);
    if (atTier.length > 0) {
      candidates = atTier;
    } else {
      const below = candidates.filter((f) => heightOf(f) <= target);
      const pool = below.length > 0 ? below : candidates;
      const maxH = Math.max(...pool.map(heightOf));
      candidates = pool.filter((f) => heightOf(f) === maxH);
    }
  } else {
    const maxH = Math.max(...candidates.map(heightOf));
    candidates = candidates.filter((f) => heightOf(f) === maxH);
  }

  // Within the resolution, prefer the highest fps, then the best codec.
  const maxFps = Math.max(...candidates.map((f) => f.fps ?? 0));
  const topFps = candidates.filter((f) => (f.fps ?? 0) === maxFps);
  return topFps.reduce(
    (best: { name: string; rank: number } | null, f) => {
      const r = rankVcodec(f.vcodec as string);
      return best === null || r.rank < best.rank ? r : best;
    },
    null,
  )?.name ?? null;
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
  // 0 reads as "0 min" (used only by the selection summary, e.g. nothing picked).
  if (minutes || totalSeconds === 0) return unit(minutes, "minute");
  return unit(totalSeconds, "second");
}
