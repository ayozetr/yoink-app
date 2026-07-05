import { describe, expect, it } from "vitest";
import { youtubeFallback } from "./youtubeFallback";

describe("youtubeFallback", () => {
  it("downgrades a maxresdefault .jpg to the always-present hqdefault", () => {
    expect(
      youtubeFallback("https://i.ytimg.com/vi/OuFgZ8bKrcE/maxresdefault.jpg"),
    ).toBe("https://i.ytimg.com/vi/OuFgZ8bKrcE/hqdefault.jpg");
  });

  it("downgrades a vi_webp variant to the vi/hqdefault.jpg", () => {
    expect(
      youtubeFallback("https://i.ytimg.com/vi_webp/abc123/maxresdefault.webp"),
    ).toBe("https://i.ytimg.com/vi/abc123/hqdefault.jpg");
  });

  it("returns null when the URL is already hqdefault (no infinite loop)", () => {
    expect(
      youtubeFallback("https://i.ytimg.com/vi/abc123/hqdefault.jpg"),
    ).toBeNull();
  });

  it("returns null for non-YouTube CDNs", () => {
    expect(youtubeFallback("https://i.scdn.co/image/ab67616d0000.jpg")).toBeNull();
    expect(youtubeFallback("https://example.com/cover.png")).toBeNull();
  });
});
