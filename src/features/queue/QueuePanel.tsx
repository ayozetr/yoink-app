import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ListPlus,
  Loader2,
  Play,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { Button } from "../../components/ui/Button";
import { startDownload, type DownloadHandle } from "../../lib/downloadSocket";
import { notify } from "../../lib/notify";
import {
  loadQueue,
  newQueueId,
  parseUrls,
  saveQueue,
  type QueueItem,
} from "../../lib/queueStore";
import type { AudioFormat, MediaKind, VideoContainer } from "../../types/download";

interface QueuePanelProps {
  /** Whether the panel is visible (the queue keeps running while hidden). */
  open: boolean;
  /** Close the panel. */
  onClose: () => void;
  /** Default format settings, used for every queued item (no per-item picker). */
  defaultKind?: MediaKind;
  defaultQuality?: string;
  defaultContainer?: VideoContainer;
  defaultAudioFormat?: AudioFormat;
  /** Refresh history/stats after each item finishes. */
  onDownloadFinished?: () => void;
  /** Report the number of unfinished items so the header can badge it. */
  onPendingChange?: (count: number) => void;
}

/** A persistent, sequential download queue: paste many URLs, run them in order. */
export function QueuePanel({
  open,
  onClose,
  defaultKind,
  defaultQuality,
  defaultContainer,
  defaultAudioFormat,
  onDownloadFinished,
  onPendingChange,
}: QueuePanelProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<QueueItem[]>(() => loadQueue());
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [percent, setPercent] = useState(0);

  const itemsRef = useRef(items);
  const handleRef = useRef<DownloadHandle | null>(null);
  const runningRef = useRef(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Live snapshot of the format settings, so a queue already running picks up
  // changes made in Settings (processNext recurses from a closure and would
  // otherwise keep using the values from the render that started it).
  const optsRef = useRef({
    defaultKind,
    defaultQuality,
    defaultContainer,
    defaultAudioFormat,
  });
  useEffect(() => {
    optsRef.current = {
      defaultKind,
      defaultQuality,
      defaultContainer,
      defaultAudioFormat,
    };
  });

  // Auto-grow the input to fit its content (up to a cap) instead of using the
  // browser's native resize handle, which clashes with the dark theme.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [input, open]);

  // Mirror state into refs + persist on every change.
  useEffect(() => {
    itemsRef.current = items;
    saveQueue(items);
  }, [items]);

  // Report unfinished items so the header can badge the queue button.
  useEffect(() => {
    onPendingChange?.(
      items.filter((i) => i.status === "pending" || i.status === "active").length,
    );
  }, [items, onPendingChange]);

  // Tear down a live socket if the panel unmounts.
  useEffect(() => () => handleRef.current?.cancel(), []);

  const update = (id: string, patch: Partial<QueueItem>) =>
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, ...patch } : i)));

  const processNext = () => {
    const next = itemsRef.current.find((i) => i.status === "pending");
    if (!next) {
      const wasRunning = runningRef.current;
      runningRef.current = false;
      setRunning(false);
      setPercent(0);
      onDownloadFinished?.();
      // A "launch it and walk away" queue shouldn't finish in silence: notify
      // once the run drains (not when Start is pressed on an empty queue).
      if (wasRunning) {
        const done = itemsRef.current.filter((i) => i.status === "done").length;
        const failed = itemsRef.current.filter((i) => i.status === "error").length;
        void notify(
          t("notify.queueDone"),
          t("notify.queueSummary", { completed: done, failed }),
        );
      }
      return;
    }
    runningRef.current = true;
    setRunning(true);
    setPercent(0);
    update(next.id, { status: "active", error: undefined });

    let settled = false;
    const opts = optsRef.current;
    handleRef.current = startDownload(
      {
        url: next.url,
        kind: opts.defaultKind ?? "video",
        quality: opts.defaultQuality,
        container: opts.defaultContainer ?? "mp4",
        audio_format: opts.defaultAudioFormat ?? "mp3",
        // The queue has no preview, so auto-detect + tag VR during the download.
        auto_vr: true,
      },
      {
        onEvent: (event) => {
          if (settled) return;
          if (event.type === "progress") {
            setPercent(event.percent);
            return;
          }
          settled = true;
          handleRef.current = null;
          if (event.type === "completed") {
            update(next.id, { status: "done", title: event.filename });
          } else {
            update(next.id, { status: "error", error: event.message });
          }
          onDownloadFinished?.();
          if (runningRef.current) processNext();
        },
        onClose: () => {
          if (settled) return;
          settled = true;
          handleRef.current = null;
          update(next.id, {
            status: "error",
            error: t("errors.downloadConnectionLost"),
          });
          if (runningRef.current) processNext();
        },
      },
    );
  };

  const addUrls = () => {
    const urls = parseUrls(input);
    if (urls.length === 0) return;
    setItems((prev) => {
      // Skip URLs already queued (pending/active/done) so re-pasting the same
      // block — a very common "did it add?" action — is idempotent, not a
      // silent double download. Failed items can be re-added to retry.
      const existing = new Set(
        prev.filter((i) => i.status !== "error").map((i) => i.url),
      );
      const fresh = urls.filter((url) => !existing.has(url));
      if (fresh.length === 0) return prev;
      return [
        ...prev,
        ...fresh.map((url) => ({
          id: newQueueId(),
          url,
          status: "pending" as const,
        })),
      ];
    });
    setInput("");
  };

  const start = () => {
    if (!runningRef.current) processNext();
  };

  const stop = () => {
    runningRef.current = false;
    handleRef.current?.cancel();
    handleRef.current = null;
    setRunning(false);
    setPercent(0);
    // Put the interrupted item back in line so it can resume.
    setItems((prev) =>
      prev.map((i) => (i.status === "active" ? { ...i, status: "pending" } : i)),
    );
    onDownloadFinished?.();
  };

  const removeItem = (id: string) =>
    setItems((prev) => prev.filter((i) => i.id !== id));
  const clearDone = () =>
    setItems((prev) => prev.filter((i) => i.status !== "done"));

  const pending = items.filter((i) => i.status === "pending").length;
  const hasDone = items.some((i) => i.status === "done");

  // Hidden but still mounted: the queue keeps downloading in the background
  // (returning null doesn't unmount, so its effects/socket live on).
  if (!open) return null;

  return (
    <GlassPanel className="p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-xs uppercase tracking-wider text-violet-400">
          <ListPlus size={14} />
          {t("queue.title")}
        </span>
        <div className="flex items-center gap-3">
          {hasDone && (
            <button
              type="button"
              onClick={clearDone}
              className="flex items-center gap-1.5 text-xs text-zinc-400 transition hover:text-white"
            >
              <Trash2 size={13} />
              {t("queue.clearDone")}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label={t("queue.close")}
            className="text-zinc-400 transition hover:text-white"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("queue.placeholder")}
          rows={2}
          className="flex-1 resize-none overflow-y-auto rounded-xl border border-white/10 bg-surface px-4 py-2.5 text-sm outline-none focus:border-violet-500"
        />
        <div className="flex gap-2 sm:flex-col">
          <Button
            onClick={addUrls}
            disabled={parseUrls(input).length === 0}
            className="h-10 px-4 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ListPlus size={16} />
            {t("queue.add")}
          </Button>
          {running ? (
            <button
              type="button"
              onClick={stop}
              className="flex h-10 items-center justify-center gap-2 rounded-xl border border-white/10 bg-surface px-4 text-sm text-zinc-200 transition hover:border-white/20"
            >
              <Square size={15} />
              {t("queue.stop")}
            </button>
          ) : (
            <button
              type="button"
              onClick={start}
              disabled={pending === 0}
              className="flex h-10 items-center justify-center gap-2 rounded-xl border border-violet-500/40 bg-violet-600/10 px-4 text-sm text-white transition hover:bg-violet-600/20 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Play size={15} />
              {t("queue.start")}
            </button>
          )}
        </div>
      </div>

      {items.length === 0 && (
        <div className="mt-3 flex flex-col items-center gap-2 py-6 text-center text-zinc-500">
          <ListPlus size={28} className="opacity-60" />
          <p className="text-xs">{t("queue.empty")}</p>
        </div>
      )}

      {items.length > 0 && (
        <ul className="mt-3 flex max-h-72 flex-col gap-1.5 overflow-auto pr-1">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-center gap-3 rounded-xl border border-white/10 bg-surface/60 p-2.5"
            >
              <span className="shrink-0">
                {item.status === "active" ? (
                  <Loader2 size={16} className="animate-spin text-violet-400" />
                ) : item.status === "done" ? (
                  <CheckCircle2 size={16} className="text-emerald-400" />
                ) : item.status === "error" ? (
                  <AlertCircle size={16} className="text-red-400" />
                ) : (
                  <span className="block size-2 rounded-full bg-zinc-500" />
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">
                  {item.title ?? item.url}
                </span>
                {item.status === "active" && (
                  <span className="mt-1 block h-1 overflow-hidden rounded-full bg-white/10">
                    <span
                      className="block h-full bg-violet-500 transition-[width]"
                      style={{ width: `${percent}%` }}
                    />
                  </span>
                )}
                {item.status === "error" && item.error && (
                  <span className="block truncate text-xs text-red-300">
                    {item.error}
                  </span>
                )}
              </span>
              {item.status !== "active" && (
                <button
                  type="button"
                  onClick={() => removeItem(item.id)}
                  aria-label={t("queue.remove")}
                  className="shrink-0 text-zinc-500 transition hover:text-white"
                >
                  <X size={15} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </GlassPanel>
  );
}
