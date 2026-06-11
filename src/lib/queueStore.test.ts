// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import {
  loadQueue,
  newQueueId,
  parseUrls,
  saveQueue,
  type QueueItem,
} from "./queueStore";

afterEach(() => localStorage.clear());

describe("parseUrls", () => {
  it("extracts http(s) URLs and ignores everything else", () => {
    const text = "https://a.com/1\nnot a url\n  http://b.com/2  \nftp://c.com/3";
    expect(parseUrls(text)).toEqual(["https://a.com/1", "http://b.com/2"]);
  });

  it("de-duplicates so re-pasting the same block is idempotent", () => {
    const text = "https://a.com/1\nhttps://a.com/1\nhttps://b.com/2";
    expect(parseUrls(text)).toEqual(["https://a.com/1", "https://b.com/2"]);
  });

  it("returns [] for blank input", () => {
    expect(parseUrls("   \n  ")).toEqual([]);
  });
});

describe("newQueueId", () => {
  it("returns unique non-empty ids", () => {
    const a = newQueueId();
    const b = newQueueId();
    expect(a).toBeTruthy();
    expect(a).not.toBe(b);
  });
});

describe("save/load round-trip", () => {
  it("persists and restores items", () => {
    const items: QueueItem[] = [
      { id: "1", url: "https://a.com", status: "done", title: "a.mp4" },
      { id: "2", url: "https://b.com", status: "pending" },
    ];
    saveQueue(items);
    expect(loadQueue()).toEqual(items);
  });

  it("resets an interrupted 'active' item back to 'pending'", () => {
    saveQueue([{ id: "1", url: "https://a.com", status: "active" }]);
    expect(loadQueue()[0].status).toBe("pending");
  });

  it("drops malformed entries without throwing", () => {
    localStorage.setItem("yoink-queue", JSON.stringify([{ nope: 1 }, "x", null]));
    expect(loadQueue()).toEqual([]);
  });

  it("returns [] when nothing is stored or JSON is broken", () => {
    expect(loadQueue()).toEqual([]);
    localStorage.setItem("yoink-queue", "{not json");
    expect(loadQueue()).toEqual([]);
  });
});
