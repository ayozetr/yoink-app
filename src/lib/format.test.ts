import { describe, it, expect } from "vitest";
import { formatBytes } from "./format";

describe("formatBytes", () => {
  it("returns null for nullish / non-finite input", () => {
    expect(formatBytes(null)).toBeNull();
    expect(formatBytes(undefined)).toBeNull();
    expect(formatBytes(NaN)).toBeNull();
    expect(formatBytes(Infinity)).toBeNull();
  });

  it("formats sub-KB values as whole bytes (no decimals)", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1023)).toBe("1023 B");
  });

  it("rolls over to larger units with one decimal", () => {
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(1024 * 1024)).toBe("1.0 MB");
    expect(formatBytes(5 * 1024 ** 3)).toBe("5.0 GB");
    expect(formatBytes(3 * 1024 ** 4)).toBe("3.0 TB");
  });

  it("caps at the largest unit (TB) instead of inventing PB", () => {
    expect(formatBytes(2048 * 1024 ** 4)).toBe("2048.0 TB");
  });
});
