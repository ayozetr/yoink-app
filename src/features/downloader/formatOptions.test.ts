// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

import { describe, it, expect } from "vitest";
import {
  videoQualities,
  estimatedSizeBytes,
  bestAvailableCodec,
  codecFitsContainer,
} from "./formatOptions";
import type { VideoInfo } from "../../types/download";

/** Minimal VideoInfo carrying only the fields videoQualities reads. */
function info(resolutions: string[], extractor = "youtube"): VideoInfo {
  return {
    extractor,
    formats: resolutions.map((resolution) => ({
      resolution,
      has_video: true,
      has_audio: false,
    })),
  } as unknown as VideoInfo;
}

describe("videoQualities", () => {
  it("labels ultrawide YouTube formats by the standard tier, like YouTube", () => {
    // A 2.35:1 video: raw heights are 1634/1090/818/544, tiers are 2160/1440/1080/720.
    expect(
      videoQualities(info(["3840x1634", "2560x1090", "1920x818", "1280x544"])),
    ).toEqual(["2160p", "1440p", "1080p", "720p"]);
  });

  it("labels 16:9, 4:3 and vertical YouTube frames correctly", () => {
    expect(videoQualities(info(["1920x1080"]))).toEqual(["1080p"]); // 16:9
    expect(videoQualities(info(["1440x1080"]))).toEqual(["1080p"]); // 4:3
    expect(videoQualities(info(["1080x1920"]))).toEqual(["1080p"]); // vertical
  });

  it("dedupes YouTube formats that share a tier and sorts high→low", () => {
    // Two 1080p-tier encodes (avc1 + vp9) collapse to one option.
    expect(videoQualities(info(["1920x1080", "1920x1080", "1280x720"]))).toEqual([
      "1080p",
      "720p",
    ]);
  });

  it("keeps the raw pixel height for non-YouTube sites (no tier relabelling)", () => {
    // The tier normalisation is YouTube-only; elsewhere the height is untouched.
    expect(videoQualities(info(["1920x818"], "generic"))).toEqual(["818p"]);
    expect(videoQualities(info(["1920x1080"], "vimeo"))).toEqual(["1080p"]);
  });
});

/** VideoInfo carrying full format objects (sizes + audio flags) for size estimation. */
function withFormats(
  formats: Array<Record<string, unknown>>,
  extractor = "youtube",
): VideoInfo {
  return { extractor, formats } as unknown as VideoInfo;
}

describe("estimatedSizeBytes", () => {
  it("returns null for lossless audio (compressed source ≠ output size)", () => {
    const i = withFormats([
      { has_audio: true, has_video: false, filesize: 5_000_000 },
    ]);
    expect(estimatedSizeBytes(i, "audio", undefined, "flac")).toBeNull();
    expect(estimatedSizeBytes(i, "audio", undefined, "wav")).toBeNull();
  });

  it("returns the largest audio-only size for lossy audio", () => {
    const i = withFormats([
      { has_audio: true, has_video: false, filesize: 3_000_000 },
      { has_audio: true, has_video: false, filesize: 5_000_000 },
      { has_audio: true, has_video: true, filesize: 9_000_000 }, // progressive, ignored
    ]);
    expect(estimatedSizeBytes(i, "audio", undefined, "mp3")).toBe(5_000_000);
  });

  it("returns null for audio when no sizes are known", () => {
    const i = withFormats([{ has_audio: true, has_video: false, filesize: null }]);
    expect(estimatedSizeBytes(i, "audio", undefined, "mp3")).toBeNull();
  });

  it("uses only the video stream when the match is progressive", () => {
    const i = withFormats([
      { resolution: "1280x720", has_video: true, has_audio: true, filesize: 8_000_000 },
      { has_video: false, has_audio: true, filesize: 2_000_000 },
    ]);
    expect(estimatedSizeBytes(i, "video", "720p")).toBe(8_000_000);
  });

  it("adds the best audio-only stream to an adaptive (video-only) match", () => {
    const i = withFormats([
      { resolution: "1920x1080", has_video: true, has_audio: false, filesize: 20_000_000 },
      { has_video: false, has_audio: true, filesize: 4_000_000 },
    ]);
    expect(estimatedSizeBytes(i, "video", "1080p")).toBe(24_000_000);
  });

  it("returns the video-only size when there's no audio stream to add", () => {
    const i = withFormats([
      { resolution: "1920x1080", has_video: true, has_audio: false, filesize: 20_000_000 },
    ]);
    expect(estimatedSizeBytes(i, "video", "1080p")).toBe(20_000_000);
  });

  it("returns null when no video format has a known size", () => {
    const i = withFormats([
      { resolution: "1920x1080", has_video: true, has_audio: false, filesize: null },
    ]);
    expect(estimatedSizeBytes(i, "video", "1080p")).toBeNull();
  });

  it("picks the largest video stream when no quality target is given", () => {
    const i = withFormats([
      { resolution: "1280x720", has_video: true, has_audio: true, filesize: 8_000_000 },
      { resolution: "1920x1080", has_video: true, has_audio: true, filesize: 15_000_000 },
    ]);
    expect(estimatedSizeBytes(i, "video", undefined)).toBe(15_000_000);
  });
});

describe("bestAvailableCodec", () => {
  it("prefers AV1 over VP9 and H.264 at the same resolution (yt-dlp default)", () => {
    const i = withFormats([
      { resolution: "1920x1080", has_video: true, vcodec: "avc1.640028", fps: 30 },
      { resolution: "1920x1080", has_video: true, vcodec: "vp09.00.40.08", fps: 30 },
      { resolution: "1920x1080", has_video: true, vcodec: "av01.0.08M.08", fps: 30 },
    ]);
    expect(bestAvailableCodec(i, "1080p")).toBe("AV1");
  });

  it("picks the codec for the chosen tier, not a higher one", () => {
    // 4K is AV1-only; 1080p only has H.264 — asking for 1080p must say H.264.
    const i = withFormats([
      { resolution: "3840x2160", has_video: true, vcodec: "av01.0.12M.08", fps: 30 },
      { resolution: "1920x1080", has_video: true, vcodec: "avc1.640028", fps: 30 },
    ]);
    expect(bestAvailableCodec(i, "1080p")).toBe("H.264");
    expect(bestAvailableCodec(i, "2160p")).toBe("AV1");
  });

  it("prefers the higher fps before codec order", () => {
    // VP9 at 60fps beats AV1 at 30fps — fps sorts before vcodec.
    const i = withFormats([
      { resolution: "1920x1080", has_video: true, vcodec: "av01.0.08M.08", fps: 30 },
      { resolution: "1920x1080", has_video: true, vcodec: "vp09.00.40.08", fps: 60 },
    ]);
    expect(bestAvailableCodec(i, "1080p")).toBe("VP9");
  });

  it("maps HEVC and returns null when no codec is exposed", () => {
    const hevc = withFormats([
      { resolution: "1920x1080", has_video: true, vcodec: "hev1.1.6.L120", fps: 30 },
    ]);
    expect(bestAvailableCodec(hevc, "1080p")).toBe("H.265");
    const none = withFormats([
      { resolution: "1920x1080", has_video: true, vcodec: null, fps: 30 },
    ]);
    expect(bestAvailableCodec(none, "1080p")).toBeNull();
  });
});

describe("codecFitsContainer", () => {
  it("flags codecs a container can't hold natively", () => {
    expect(codecFitsContainer("webm", "h264")).toBe(false); // WebM is VP9/AV1
    expect(codecFitsContainer("webm", "h265")).toBe(false);
    expect(codecFitsContainer("mov", "vp9")).toBe(false); // QuickTime: no VP9/AV1
    expect(codecFitsContainer("mov", "av1")).toBe(false);
    expect(codecFitsContainer("mp4", "vp9")).toBe(false); // VP9-in-MP4 is fragile
  });

  it("accepts native pairings and never warns for 'any'", () => {
    expect(codecFitsContainer("webm", "vp9")).toBe(true);
    expect(codecFitsContainer("webm", "av1")).toBe(true);
    expect(codecFitsContainer("mp4", "h264")).toBe(true);
    expect(codecFitsContainer("mp4", "av1")).toBe(true);
    expect(codecFitsContainer("mkv", "vp9")).toBe(true); // MKV holds everything
    expect(codecFitsContainer("webm", "any")).toBe(true); // "best available" never clashes
  });
});
