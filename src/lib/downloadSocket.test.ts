import { afterEach, describe, expect, it, vi } from "vitest";
import { startDownload } from "./downloadSocket";
import type { DownloadRequest } from "../types/download";

class MockWebSocket {
  static last: MockWebSocket;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  sent: string[] = [];
  constructor() {
    MockWebSocket.last = this;
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.onclose?.();
  }
}

const REQUEST = { url: "https://example.com/v", kind: "audio" } as DownloadRequest;

afterEach(() => {
  vi.restoreAllMocks();
});

describe("startDownload", () => {
  it("sends the request on open and forwards events", () => {
    vi.stubGlobal("WebSocket", MockWebSocket);
    const events: { type: string }[] = [];

    startDownload(REQUEST, { onEvent: (e) => events.push(e) });
    const ws = MockWebSocket.last;

    ws.onopen?.();
    expect(JSON.parse(ws.sent[0]).kind).toBe("audio");

    ws.onmessage?.({
      data: JSON.stringify({ type: "completed", filename: "x.mp3" }),
    });
    expect(events[0]).toMatchObject({ type: "completed" });
  });

  it("emits an error if the handshake never opens", () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", MockWebSocket);
    const events: { type: string }[] = [];

    startDownload(REQUEST, { onEvent: (e) => events.push(e) });
    // Never call onopen — advance past the open timeout.
    vi.advanceTimersByTime(15_000);

    expect(events[0]).toMatchObject({ type: "error" });
    vi.useRealTimers();
  });

  it("calls onClose on a server close but not on a client cancel", () => {
    vi.stubGlobal("WebSocket", MockWebSocket);

    const serverClose = vi.fn();
    startDownload(REQUEST, { onEvent: () => undefined, onClose: serverClose });
    MockWebSocket.last.close(); // server-side close
    expect(serverClose).toHaveBeenCalledOnce();

    const cancelClose = vi.fn();
    const handle = startDownload(REQUEST, {
      onEvent: () => undefined,
      onClose: cancelClose,
    });
    handle.cancel(); // client cancel → onClose must NOT fire
    expect(cancelClose).not.toHaveBeenCalled();
  });
});
