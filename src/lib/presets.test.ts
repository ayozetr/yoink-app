// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import {
  loadPresets,
  newPresetId,
  savePresets,
  type DownloadPreset,
} from "./presets";

afterEach(() => localStorage.clear());

describe("presets", () => {
  it("returns nothing when empty", () => {
    expect(loadPresets()).toEqual([]);
  });

  it("round-trips a saved preset", () => {
    const p: DownloadPreset = {
      id: "1",
      name: "HD MP4",
      kind: "video",
      quality: "1080p",
      container: "mp4",
      embedChapters: true,
    };
    savePresets([p]);
    expect(loadPresets()).toEqual([p]);
  });

  it("drops malformed / unknown-kind entries", () => {
    localStorage.setItem(
      "yoink-presets",
      JSON.stringify([
        { name: "no id" },
        { id: "1", name: "ok", kind: "audio" },
        { id: "2", name: "bad kind", kind: "movie" },
      ]),
    );
    expect(loadPresets().map((p) => p.id)).toEqual(["1"]);
  });

  it("tolerates malformed storage", () => {
    localStorage.setItem("yoink-presets", "{ not json");
    expect(loadPresets()).toEqual([]);
  });

  it("generates distinct ids", () => {
    expect(newPresetId()).not.toBe(newPresetId());
  });
});
