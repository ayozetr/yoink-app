import { afterEach, describe, expect, it } from "vitest";
import {
  acquireDownloadLock,
  downloadLockOwner,
  isLockedByOther,
  releaseDownloadLock,
} from "./downloadLock";

// The lock is a module-level singleton; reset it after every case.
afterEach(() => {
  releaseDownloadLock("downloader");
  releaseDownloadLock("queue");
  releaseDownloadLock("music");
});

describe("downloadLock", () => {
  it("starts free", () => {
    expect(downloadLockOwner()).toBeNull();
  });

  it("acquires when free", () => {
    expect(acquireDownloadLock("downloader")).toBe(true);
    expect(downloadLockOwner()).toBe("downloader");
  });

  it("is re-entrant for the same owner", () => {
    expect(acquireDownloadLock("queue")).toBe(true);
    expect(acquireDownloadLock("queue")).toBe(true);
    expect(downloadLockOwner()).toBe("queue");
  });

  it("rejects a different owner while held", () => {
    expect(acquireDownloadLock("downloader")).toBe(true);
    expect(acquireDownloadLock("queue")).toBe(false);
    expect(downloadLockOwner()).toBe("downloader");
  });

  it("treats release by a non-owner as a no-op", () => {
    acquireDownloadLock("downloader");
    releaseDownloadLock("queue"); // not the holder
    expect(downloadLockOwner()).toBe("downloader");
  });

  it("releases for the owner and lets another engine acquire", () => {
    acquireDownloadLock("downloader");
    releaseDownloadLock("downloader");
    expect(downloadLockOwner()).toBeNull();
    expect(acquireDownloadLock("music")).toBe(true);
    expect(downloadLockOwner()).toBe("music");
  });

  it("reports isLockedByOther relative to a given engine", () => {
    expect(isLockedByOther("downloader")).toBe(false);
    acquireDownloadLock("queue");
    expect(isLockedByOther("downloader")).toBe(true);
    expect(isLockedByOther("queue")).toBe(false);
    expect(isLockedByOther()).toBe(true); // held by anyone
  });
});
