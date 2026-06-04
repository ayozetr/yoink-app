import { describe, expect, it } from "vitest";
import { guessFromFilename } from "./filename";

describe("guessFromFilename", () => {
  it("splits on the first ' - '", () => {
    expect(guessFromFilename("Artist - Song.mp3")).toEqual({
      artist: "Artist",
      title: "Song",
    });
  });

  it("strips a trailing (Official Video) tag", () => {
    expect(guessFromFilename("A - B (Official Video).mp3")).toEqual({
      artist: "A",
      title: "B",
    });
  });

  it("strips a (prod. …) tag", () => {
    expect(guessFromFilename("X - Y (prod. Z).flac")).toEqual({
      artist: "X",
      title: "Y",
    });
  });

  it("returns an empty artist when there's no dash", () => {
    expect(guessFromFilename("JustATitle.flac")).toEqual({
      artist: "",
      title: "JustATitle",
    });
  });

  it("handles an empty name", () => {
    expect(guessFromFilename()).toEqual({ artist: "", title: "" });
  });
});
