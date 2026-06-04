import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, identifyAudio } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("identifyAudio", () => {
  it("POSTs the path and returns the candidate list", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ results: [{ title: "T", artist: "A" }] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await identifyAudio("/dl/song.mp3");

    expect(result.results[0].title).toBe("T");
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toContain("/autotag/identify");
    expect(JSON.parse(opts.body)).toEqual({ path: "/dl/song.mp3" });
  });

  it("throws ApiError on a non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: "not found" }),
      }),
    );

    await expect(identifyAudio("/dl/x.mp3")).rejects.toBeInstanceOf(ApiError);
  });
});
