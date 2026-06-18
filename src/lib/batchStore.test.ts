// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { clearBatch, loadPendingBatch, saveBatch, type BatchJob } from "./batchStore";

const job = (url: string): BatchJob => ({
  request: { url, kind: "video" },
  title: url,
});

afterEach(() => clearBatch());

describe("batchStore", () => {
  it("returns nothing when there's no saved batch", () => {
    expect(loadPendingBatch()).toEqual([]);
  });

  it("returns every job when none are done yet", () => {
    saveBatch([job("a"), job("b"), job("c")], 0);
    expect(loadPendingBatch().map((j) => j.request.url)).toEqual(["a", "b", "c"]);
  });

  it("skips the finished prefix", () => {
    saveBatch([job("a"), job("b"), job("c")], 2);
    expect(loadPendingBatch().map((j) => j.request.url)).toEqual(["c"]);
  });

  it("returns nothing when the whole batch finished", () => {
    saveBatch([job("a"), job("b")], 2);
    expect(loadPendingBatch()).toEqual([]);
  });

  it("clears the persisted batch", () => {
    saveBatch([job("a")], 0);
    clearBatch();
    expect(loadPendingBatch()).toEqual([]);
  });

  it("tolerates malformed storage", () => {
    localStorage.setItem("yoink-batch", "{ not json");
    expect(loadPendingBatch()).toEqual([]);
    localStorage.setItem("yoink-batch", JSON.stringify({ jobs: "x", done: 0 }));
    expect(loadPendingBatch()).toEqual([]);
  });
});
