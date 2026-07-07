import { describe, it, expect } from "vitest";
import { videoQualities, estimatedSizeBytes } from "./formatOptions";
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
