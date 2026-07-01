import { describe, it, expect } from "vitest";
import { videoQualities } from "./formatOptions";
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
