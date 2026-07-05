import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  GripVertical,
  ListPlus,
  Loader2,
  Play,
  SkipForward,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { Button } from "../../components/ui/Button";
import { ProgressBar } from "../../components/ui/ProgressBar";
import { Select } from "../../components/ui/Select";
import { AUDIO_FORMATS, VIDEO_CONTAINERS } from "../downloader/formatOptions";
import { startDownload, type DownloadHandle } from "../../lib/downloadSocket";
import {
  acquireDownloadLock,
  releaseDownloadLock,
  useDownloadLock,
} from "../../lib/downloadLock";
import { notify } from "../../lib/notify";
import {
  applyAudioTags,
  fetchInfo,
  isMusicUrl,
  matchMusic,
  resolveMusic,
} from "../../lib/api";
import {
  loadQueue,
  newQueueId,
  parseUrls,
  saveQueue,
  type QueueChild,
  type QueueItem,
  type QueueStatus,
} from "../../lib/queueStore";
import { MUSIC_SOURCE_NAMES, type MusicTrack } from "../../types/music";
import type {
  AudioFormat,
  DownloadRequest,
  DownloadProgressEvent,
  MediaKind,
  VideoContainer,
} from "../../types/download";

// The queue has no preview, so it offers a generic best-effort quality target
// (yt-dlp caps to it or takes the closest lower tier).
const QUALITY_OPTIONS = ["best", "1080p", "720p", "480p", "360p"];

// Control-flow signals for the drain loop: SkipSignal drops the current download
// and moves on; StopSignal (Cancel-all) unwinds the whole run.
class SkipSignal extends Error {}
class StopSignal extends Error {}

/** The next thing to download: a plain item, or a group's next selected child. */
interface Work {
  item: QueueItem;
  child: QueueChild | null;
}

/** Human name of the platform a non-music playlist/video came from, from its URL
 * (so a group reads "YouTube Music · 20/20" like the music ones do). */
function playlistSource(url: string): string | null {
  let host: string;
  try {
    host = new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
  if (host === "music.youtube.com") return "YouTube Music";
  if (host.endsWith("youtube.com") || host === "youtu.be") return "YouTube";
  if (host.endsWith("soundcloud.com")) return "SoundCloud";
  if (host.endsWith("vimeo.com")) return "Vimeo";
  if (host.endsWith("bandcamp.com")) return "Bandcamp";
  if (host.endsWith("dailymotion.com")) return "Dailymotion";
  if (host.endsWith("twitch.tv")) return "Twitch";
  // Fallback: the registrable domain's main label, capitalized (e.g. "Nebula").
  const label = host.split(".").slice(-2, -1)[0];
  return label ? label.charAt(0).toUpperCase() + label.slice(1) : null;
}

/** Reset an interrupted item/child (status "active") back to "pending". */
function resetActive(item: QueueItem): QueueItem {
  const status: QueueStatus = item.status === "active" ? "pending" : item.status;
  if (!item.children) return { ...item, status };
  return {
    ...item,
    status,
    children: item.children.map((c) =>
      c.status === "active" ? { ...c, status: "pending" } : c,
    ),
  };
}

/** A group's status is derived from its selected children; a single's is its own. */
function displayStatus(item: QueueItem): QueueStatus {
  if (item.status === "resolving") return "resolving";
  if (!item.children) return item.status;
  const sel = item.children.filter((c) => c.selected);
  if (sel.some((c) => c.status === "active")) return "active";
  if (sel.length === 0) return "pending";
  if (sel.every((c) => c.status !== "pending"))
    return sel.some((c) => c.status === "done") ? "done" : "error";
  return "pending";
}

function itemDone(item: QueueItem): boolean {
  return displayStatus(item) === "done";
}

/** The status dot/icon shared by item rows and their child rows. */
function statusIcon(status: QueueStatus) {
  switch (status) {
    case "active":
      return <Loader2 size={16} className="animate-spin text-violet-400" />;
    case "resolving":
      return <Loader2 size={16} className="animate-spin text-zinc-500" />;
    case "done":
      return <CheckCircle2 size={16} className="text-emerald-400" />;
    case "error":
      return <AlertCircle size={16} className="text-red-400" />;
    case "skipped":
      return <SkipForward size={16} className="text-zinc-500" />;
    default:
      return <span className="block size-2 rounded-full bg-zinc-500" />;
  }
}

/** Pending or active work an item still owes (itself, or its selected children)
 * — drives the Start button + the header badge. */
function unfinishedCount(item: QueueItem): number {
  if (item.status === "resolving") return 1;
  if (!item.children)
    return item.status === "pending" || item.status === "active" ? 1 : 0;
  return item.children.filter(
    (c) => c.selected && (c.status === "pending" || c.status === "active"),
  ).length;
}

/** Media-level tallies for the whole-queue progress: a group counts its selected
 * children, a single counts as one. */
function mediaTotal(item: QueueItem): number {
  if (item.status === "resolving") return 1;
  if (!item.children) return 1;
  return item.children.filter((c) => c.selected).length;
}
function mediaMatching(item: QueueItem, match: (s: QueueStatus) => boolean): number {
  if (!item.children) return match(item.status) ? 1 : 0;
  return item.children.filter((c) => c.selected && match(c.status)).length;
}
const isTerminalStatus = (s: QueueStatus): boolean =>
  s === "done" || s === "skipped" || s === "error";

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
  /** Whether "notify on complete" is on (Settings) — gates the finish notification. */
  notifyOnComplete?: boolean;
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
  notifyOnComplete,
  onDownloadFinished,
  onPendingChange,
}: QueuePanelProps) {
  const { t } = useTranslation();
  // Keep the latest `t` for the long-running drain loop / download callbacks,
  // which are created once and would otherwise use a stale translator after a
  // mid-run language change.
  const tRef = useRef(t);
  const notifyRef = useRef(notifyOnComplete);
  useEffect(() => {
    tRef.current = t;
    notifyRef.current = notifyOnComplete;
  });
  const [items, setItems] = useState<QueueItem[]>(() => loadQueue());
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  // Full live progress event (percent + speed + ETA + status) for the active
  // item, so its row shows the same readout as a normal download.
  const [progress, setProgress] = useState<DownloadProgressEvent | null>(null);
  // Shared download lock: the main panel / music import holding it blocks Start
  // so the queue can't run a second concurrent download into the same folder.
  const lockOwner = useDownloadLock();
  const lockedByOther = lockOwner !== null && lockOwner !== "queue";
  // Parse the textarea once per change instead of on every render (it's read by
  // the Add button's disabled state and by addUrls).
  const parsedInput = useMemo(() => parseUrls(input), [input]);

  const itemsRef = useRef(items);
  const handleRef = useRef<DownloadHandle | null>(null);
  const runningRef = useRef(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Format for the whole queue, seeded from Settings but editable here (the queue
  // has no per-item picker). Music-service URLs ignore the video/audio choice.
  const [kind, setKind] = useState<MediaKind>(defaultKind ?? "video");
  const [quality, setQuality] = useState(defaultQuality ?? "best");
  const [container, setContainer] = useState<VideoContainer>(
    defaultContainer ?? "mp4",
  );
  const [audioFormat, setAudioFormat] = useState<AudioFormat>(
    defaultAudioFormat ?? "mp3",
  );
  const isVideo = kind === "video";
  // Live snapshot so a running queue picks up format changes made mid-run
  // (processNext recurses from a closure and would otherwise keep the old values).
  const optsRef = useRef({ kind, quality, container, audioFormat });
  useEffect(() => {
    optsRef.current = { kind, quality, container, audioFormat };
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
    onPendingChange?.(items.reduce((n, i) => n + unfinishedCount(i), 0));
  }, [items, onPendingChange]);

  // Tear down a live socket + free the lock if the panel unmounts.
  useEffect(
    () => () => {
      handleRef.current?.cancel();
      releaseDownloadLock("queue");
    },
    [],
  );

  const update = (id: string, patch: Partial<QueueItem>) =>
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, ...patch } : i)));

  const updateChild = (
    itemId: string,
    childId: string,
    patch: Partial<QueueChild>,
  ) =>
    setItems((prev) =>
      prev.map((i) =>
        i.id === itemId && i.children
          ? {
              ...i,
              children: i.children.map((c) =>
                c.id === childId ? { ...c, ...patch } : c,
              ),
            }
          : i,
      ),
    );

  const toggleExpanded = (id: string) =>
    setItems((prev) =>
      prev.map((i) => (i.id === id ? { ...i, expanded: !i.expanded } : i)),
    );

  const toggleChild = (itemId: string, childId: string) =>
    setItems((prev) =>
      prev.map((i) =>
        i.id === itemId && i.children
          ? {
              ...i,
              children: i.children.map((c) =>
                c.id === childId ? { ...c, selected: !c.selected } : c,
              ),
            }
          : i,
      ),
    );

  const setAllChildren = (itemId: string, selected: boolean) =>
    setItems((prev) =>
      prev.map((i) =>
        i.id === itemId && i.children
          ? { ...i, children: i.children.map((c) => ({ ...c, selected })) }
          : i,
      ),
    );

  // --- Adding URLs: resolve each into a single item or a selectable group ---

  const addUrls = () => {
    const urls = parsedInput;
    if (urls.length === 0) return;
    // Skip URLs already queued (by source url) so re-pasting is idempotent;
    // failed items can be re-added to retry.
    const existing = new Set(
      itemsRef.current.filter((i) => i.status !== "error").map((i) => i.url),
    );
    const fresh = urls.filter((url) => !existing.has(url));
    if (fresh.length === 0) {
      setInput("");
      return;
    }
    const placeholders = fresh.map((url) => ({
      id: newQueueId(),
      url,
      status: "resolving" as const,
    }));
    setItems((prev) => [...prev, ...placeholders]);
    setInput("");
    placeholders.forEach((p) => void resolveItem(p.id, p.url));
  };

  // Turn a placeholder into a plain single item, or a group of selectable
  // children (a music album/playlist, or a regular video playlist).
  const resolveItem = async (id: string, url: string) => {
    try {
      if (isMusicUrl(url)) {
        const info = await resolveMusic(url);
        const source = MUSIC_SOURCE_NAMES[info.source];
        // Fall back to the album/playlist cover so tagging always has art.
        const withCover = (t: MusicTrack): MusicTrack => ({
          ...t,
          cover_url: t.cover_url ?? info.cover_url,
        });
        if (info.tracks.length === 1) {
          // A single track is a plain music item — no chevron, downloaded via
          // match + tag.
          const track = withCover(info.tracks[0]);
          update(id, {
            status: "pending",
            title: `${track.artists} — ${track.title}`,
            track,
            sourceLabel: source,
          });
        } else {
          const children: QueueChild[] = info.tracks.map((track) => ({
            id: newQueueId(),
            title: `${track.artists} — ${track.title}`,
            status: "pending",
            selected: true,
            track: withCover(track),
          }));
          update(id, {
            status: "pending",
            title: info.name,
            children,
            sourceLabel: source,
          });
        }
      } else {
        const info = await fetchInfo(url);
        if (info.type === "playlist" && info.playlist) {
          const children: QueueChild[] = info.playlist.entries.map((e) => ({
            id: newQueueId(),
            title: e.title,
            url: e.url,
            status: "pending",
            selected: true,
          }));
          update(id, {
            status: "pending",
            title: info.playlist.title,
            children,
            sourceLabel: playlistSource(url) ?? tRef.current("queue.playlist"),
          });
        } else {
          update(id, {
            status: "pending",
            title: info.video?.title ?? url,
            sourceLabel: playlistSource(url) ?? undefined,
          });
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      // A music URL that won't resolve is a hard error (yt-dlp can't take it
      // either). A non-music resolve failure (anti-bot/network) falls back to a
      // plain item so the download can still try it later.
      if (isMusicUrl(url)) update(id, { status: "error", error: message });
      else
        update(id, {
          status: "pending",
          title: url,
          sourceLabel: playlistSource(url) ?? undefined,
        });
    }
  };

  // --- Download engine: an async drain loop over singles + group children ---

  const [activeChildId, setActiveChildId] = useState<string | null>(null);
  const runIdRef = useRef(0);
  const rejectRef = useRef<((reason: unknown) => void) | null>(null);

  // Wrap one yt-dlp download in a promise. cancel() suppresses the socket
  // callbacks, so skip/stop reject through rejectRef instead of leaving the
  // loop's await hanging forever.
  const downloadOne = (req: DownloadRequest) =>
    new Promise<{ filepath: string; filename: string }>((resolve, reject) => {
      rejectRef.current = reject;
      let settled = false;
      handleRef.current = startDownload(req, {
        onEvent: (event) => {
          if (settled) return;
          if (event.type === "progress") {
            setProgress(event);
            return;
          }
          settled = true;
          handleRef.current = null;
          rejectRef.current = null;
          if (event.type === "completed")
            resolve({ filepath: event.filepath, filename: event.filename });
          else reject(new Error(event.message));
        },
        onClose: () => {
          if (settled) return;
          settled = true;
          handleRef.current = null;
          rejectRef.current = null;
          reject(new Error(tRef.current("errors.downloadConnectionLost")));
        },
      });
    });

  const findNextWork = (): Work | null => {
    for (const item of itemsRef.current) {
      if (item.children) {
        const child = item.children.find(
          (c) => c.selected && c.status === "pending",
        );
        if (child) return { item, child };
      } else if (item.status === "pending") {
        return { item, child: null };
      }
    }
    return null;
  };

  // Music: match on YouTube → download audio → tag with the source metadata.
  const downloadMusic = async (track: MusicTrack, runId: number) => {
    const url = await matchMusic(track);
    if (!runningRef.current || runIdRef.current !== runId) throw new StopSignal();
    if (!url) throw new SkipSignal(); // nothing cleared the match threshold
    const res = await downloadOne({
      url,
      kind: "audio",
      audio_format: optsRef.current.audioFormat,
    });
    await applyAudioTags({
      path: res.filepath,
      title: track.title,
      artist: track.artists,
      album: track.album,
      year: track.year,
      cover_url: track.cover_url,
    }).catch(() => undefined); // tagging is best-effort
  };

  const doWork = async (work: Work, runId: number) => {
    const opts = optsRef.current;
    // A single music track (plain item) or a music child both download + tag.
    const track = work.child ? work.child.track : work.item.track;
    if (track) {
      await downloadMusic(track, runId);
      return;
    }
    // Otherwise a plain video/audio download at the queue's chosen format.
    const url = work.child ? work.child.url! : work.item.url;
    await downloadOne({
      url,
      kind: opts.kind,
      quality: opts.quality,
      container: opts.container,
      audio_format: opts.audioFormat,
      auto_vr: true, // no preview, so auto-detect + tag VR during the download
    });
  };

  const drain = async (runId: number) => {
    while (runningRef.current && runIdRef.current === runId) {
      const work = findNextWork();
      if (!work) break;
      setProgress(null);
      if (work.child) {
        setActiveChildId(work.child.id);
        updateChild(work.item.id, work.child.id, {
          status: "active",
          error: undefined,
        });
      } else {
        setActiveChildId(null);
        update(work.item.id, { status: "active", error: undefined });
      }
      try {
        await doWork(work, runId);
        if (runIdRef.current !== runId) return; // superseded by stop/restart
        if (work.child)
          updateChild(work.item.id, work.child.id, { status: "done" });
        else update(work.item.id, { status: "done" });
      } catch (err) {
        if (runIdRef.current !== runId) return;
        if (err instanceof StopSignal) return; // stop() already reset the row
        const skipped = err instanceof SkipSignal;
        const status = skipped ? "skipped" : "error";
        const error = skipped
          ? undefined
          : err instanceof Error
            ? err.message
            : String(err);
        if (work.child)
          updateChild(work.item.id, work.child.id, { status, error });
        else update(work.item.id, { status, error });
      }
      setActiveChildId(null);
      onDownloadFinished?.();
    }
    finish(runId);
  };

  const finish = (runId: number) => {
    if (runIdRef.current !== runId) return; // superseded by stop/restart
    runningRef.current = false;
    releaseDownloadLock("queue");
    setRunning(false);
    setProgress(null);
    setActiveChildId(null);
    onDownloadFinished?.();
    // A "launch it and walk away" queue shouldn't finish in silence.
    let done = 0;
    let failed = 0;
    for (const i of itemsRef.current) {
      for (const r of i.children ?? [i]) {
        if (r.status === "done") done += 1;
        else if (r.status === "error") failed += 1;
      }
    }
    if (notifyRef.current)
      void notify(
        tRef.current("notify.queueDone"),
        tRef.current("notify.queueSummary", { completed: done, failed }),
      );
  };

  const start = () => {
    if (runningRef.current) return;
    // Refuse to start while another engine downloads (Start is also disabled in
    // the UI; this guards the render-vs-click race).
    if (!acquireDownloadLock("queue")) return;
    runningRef.current = true;
    setRunning(true);
    void drain((runIdRef.current += 1));
  };

  const stop = () => {
    runningRef.current = false;
    runIdRef.current += 1; // invalidate the running drain's continuations
    handleRef.current?.cancel();
    rejectRef.current?.(new StopSignal());
    rejectRef.current = null;
    handleRef.current = null;
    releaseDownloadLock("queue");
    setRunning(false);
    setProgress(null);
    setActiveChildId(null);
    // Put the interrupted item/child back in line so it resumes next run.
    setItems((prev) => prev.map(resetActive));
    onDownloadFinished?.();
  };

  // Skip just the current download and move on — the run keeps going (unlike
  // Stop). Rejecting the in-flight promise unblocks the drain loop's await.
  const skipCurrent = () => {
    handleRef.current?.cancel();
    handleRef.current = null;
    rejectRef.current?.(new SkipSignal());
    rejectRef.current = null;
    setProgress(null);
  };

  // Drag-reorder pending items so the user can change the download order.
  const [dragId, setDragId] = useState<string | null>(null);
  const reorder = (fromId: string, toId: string) => {
    if (fromId === toId) return;
    setItems((prev) => {
      const from = prev.findIndex((i) => i.id === fromId);
      const to = prev.findIndex((i) => i.id === toId);
      if (from < 0 || to < 0) return prev;
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
  };

  const removeItem = (id: string) =>
    setItems((prev) => prev.filter((i) => i.id !== id));
  const clearDone = () => setItems((prev) => prev.filter((i) => !itemDone(i)));

  // Downloadable pending work (excludes resolving/active) — gates the Start button.
  const pending = items.reduce((n, i) => {
    if (i.children)
      return (
        n + i.children.filter((c) => c.selected && c.status === "pending").length
      );
    return n + (i.status === "pending" ? 1 : 0);
  }, 0);
  const hasDone = items.some(itemDone);

  // Same readout as DownloadProgressCard, shown on the active item's row.
  const percent = progress?.percent ?? 0;
  // Whole-queue progress, counted in media (album/playlist tracks, not rows).
  const mediaTotals = items.reduce((n, i) => n + mediaTotal(i), 0);
  const mediaDoneCount = items.reduce(
    (n, i) => n + mediaMatching(i, (s) => s === "done"),
    0,
  );
  const mediaFinishedCount = items.reduce(
    (n, i) => n + mediaMatching(i, isTerminalStatus),
    0,
  );
  // Fill by finished media plus the fraction of the one in flight, so the bar
  // glides instead of jumping a whole media at a time.
  const queuePercent =
    mediaTotals > 0
      ? Math.min(100, ((mediaFinishedCount + Math.min(1, percent / 100)) / mediaTotals) * 100)
      : 0;
  const isProcessing = progress?.status === "processing";
  const progressDetail = isProcessing
    ? t("progress.merging")
    : [progress?.speed, progress?.eta && `${t("progress.eta")} ${progress.eta}`]
        .filter(Boolean)
        .join(" • ");

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
          aria-label={t("queue.placeholder")}
          placeholder={t("queue.placeholder")}
          rows={2}
          className="flex-1 resize-none overflow-y-auto rounded-xl border border-white/10 bg-surface px-4 py-2.5 text-sm outline-none focus:border-violet-500"
        />
        <div className="flex gap-2 sm:flex-col">
          <Button
            onClick={addUrls}
            disabled={parsedInput.length === 0}
            className="h-10 px-4 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ListPlus size={16} />
            {t("queue.add")}
          </Button>
          {running ? (
            <>
              <button
                type="button"
                onClick={skipCurrent}
                className="flex h-10 items-center justify-center gap-2 rounded-xl border border-white/10 bg-surface px-4 text-sm text-zinc-200 transition hover:border-white/20"
              >
                <SkipForward size={15} />
                {t("queue.skip")}
              </button>
              <button
                type="button"
                onClick={stop}
                className="flex h-10 items-center justify-center gap-2 rounded-xl border border-white/10 bg-surface px-4 text-sm text-zinc-200 transition hover:border-white/20"
              >
                <Square size={15} />
                {t("queue.stop")}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={start}
              disabled={pending === 0 || lockedByOther}
              title={lockedByOther ? t("common.busy") : undefined}
              className="flex h-10 items-center justify-center gap-2 rounded-xl border border-violet-500/40 bg-violet-600/10 px-4 text-sm text-white transition hover:bg-violet-600/20 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Play size={15} />
              {t("queue.start")}
            </button>
          )}
        </div>
      </div>

      {/* Format for the whole queue (music URLs always download audio). */}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-xs text-zinc-500">{t("preview.format")}</span>
        <Select
          ariaLabel={t("preview.format")}
          value={kind}
          onChange={(v) => setKind(v as MediaKind)}
          options={[
            { value: "video", label: t("preview.video") },
            { value: "audio", label: t("preview.audio") },
          ]}
          className="h-9 rounded-lg border border-white/10 bg-surface px-3 text-sm"
        />
        {isVideo ? (
          <>
            <Select
              ariaLabel={t("preview.quality")}
              value={quality}
              onChange={setQuality}
              options={QUALITY_OPTIONS.map((o) => ({
                value: o,
                label: o === "best" ? t("settings.qualityBest") : o,
              }))}
              className="h-9 rounded-lg border border-white/10 bg-surface px-3 text-sm"
            />
            <Select
              ariaLabel={t("preview.container")}
              value={container}
              onChange={(v) => setContainer(v as VideoContainer)}
              options={VIDEO_CONTAINERS}
              className="h-9 rounded-lg border border-white/10 bg-surface px-3 text-sm"
            />
          </>
        ) : (
          <Select
            ariaLabel={t("preview.audioFormat")}
            value={audioFormat}
            onChange={(v) => setAudioFormat(v as AudioFormat)}
            options={AUDIO_FORMATS.map((o) => ({ value: o.value, label: o.label }))}
            className="h-9 rounded-lg border border-white/10 bg-surface px-3 text-sm"
          />
        )}
      </div>

      {mediaTotals > 0 && (
        <div className="mt-3 border-t border-white/5 pt-3">
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="text-zinc-400">
              {t("queue.progressCount", {
                done: mediaDoneCount,
                total: mediaTotals,
              })}
            </span>
            <span className="tabular-nums text-zinc-500">
              {Math.round(queuePercent)}%
            </span>
          </div>
          <ProgressBar percent={queuePercent} className="h-1.5" />
        </div>
      )}

      {items.length === 0 && (
        <div className="mt-3 flex flex-col items-center gap-2 py-6 text-center text-zinc-500">
          <ListPlus size={28} className="opacity-60" />
          <p className="text-xs">{t("queue.empty")}</p>
        </div>
      )}

      {items.length > 0 && (
        <ul className="mt-3 flex max-h-72 flex-col gap-1.5 overflow-auto pr-1">
          {items.map((item) => {
            const status = displayStatus(item);
            const total = item.children?.length ?? 0;
            const selectedCount =
              item.children?.filter((c) => c.selected).length ?? 0;
            return (
              <li
                key={item.id}
                draggable
                onDragStart={(e) => {
                  setDragId(item.id);
                  // Drag only the row as the ghost — dragging an expanded group
                  // would otherwise carry its whole child list, which looks messy.
                  const row = e.currentTarget.firstElementChild;
                  if (row) e.dataTransfer.setDragImage(row, 16, 16);
                }}
                // Reorder live as the dragged row passes over another one.
                onDragEnter={() => {
                  if (dragId && dragId !== item.id) reorder(dragId, item.id);
                }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragId(null);
                }}
                onDragEnd={() => setDragId(null)}
                className={dragId === item.id ? "opacity-50" : ""}
              >
                <div className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-surface/60 p-2.5">
                  <GripVertical
                    size={15}
                    className="shrink-0 cursor-grab text-zinc-600"
                  />
                  {item.children && (
                    <button
                      type="button"
                      onClick={() => toggleExpanded(item.id)}
                      aria-label={t("queue.expand")}
                      className="shrink-0 text-zinc-400 transition hover:text-white"
                    >
                      <ChevronRight
                        size={15}
                        className={`transition-transform ${
                          item.expanded ? "rotate-90" : ""
                        }`}
                      />
                    </button>
                  )}
                  <span className="shrink-0">{statusIcon(status)}</span>
                  <div className="min-w-0 flex-1">
                    <span className="flex items-center justify-between gap-2">
                      <span className="block truncate text-sm">
                        {item.status === "resolving"
                          ? t("queue.resolving")
                          : (item.title ?? item.url)}
                      </span>
                      {status === "active" && (
                        <span className="shrink-0 text-xs font-medium text-violet-400">
                          {Math.round(percent)}%
                        </span>
                      )}
                    </span>
                    {item.sourceLabel && item.status !== "resolving" && (
                      <span className="mt-0.5 block truncate text-xs text-zinc-500">
                        {item.children
                          ? `${item.sourceLabel} · ${t("queue.selectedOfTracks", {
                              selected: selectedCount,
                              total,
                            })}`
                          : item.sourceLabel}
                      </span>
                    )}
                    {status === "active" && (
                      <>
                        <ProgressBar percent={percent} className="mt-1 h-1" />
                        {progressDetail && (
                          <span className="mt-1 block truncate text-xs text-zinc-400">
                            {progressDetail}
                          </span>
                        )}
                      </>
                    )}
                    {status === "error" && item.error && (
                      <span className="block truncate text-xs text-red-300">
                        {item.error}
                      </span>
                    )}
                  </div>
                  {status !== "active" && (
                    <button
                      type="button"
                      onClick={() => removeItem(item.id)}
                      aria-label={t("queue.remove")}
                      className="shrink-0 text-zinc-500 transition hover:text-white"
                    >
                      <X size={15} />
                    </button>
                  )}
                </div>

                {item.children && item.expanded && (
                  <ul className="ml-5 mt-1 flex flex-col gap-1 border-l border-white/10 py-1 pl-3">
                    <li className="flex justify-end pr-1">
                      <button
                        type="button"
                        onClick={() =>
                          setAllChildren(item.id, selectedCount < total)
                        }
                        className="text-[11px] text-zinc-400 transition hover:text-white"
                      >
                        {selectedCount < total
                          ? t("playlist.selectAll")
                          : t("playlist.deselectAll")}
                      </button>
                    </li>
                    {item.children.map((child) => (
                      <li key={child.id} className="flex items-start gap-2 pr-1">
                        <input
                          type="checkbox"
                          checked={child.selected}
                          onChange={() => toggleChild(item.id, child.id)}
                          className="mt-0.5 size-3.5 shrink-0 accent-violet-500"
                        />
                        <span className="mt-px shrink-0">
                          {statusIcon(child.status)}
                        </span>
                        <span
                          className={`min-w-0 flex-1 break-words text-xs leading-snug ${
                            child.selected ? "text-zinc-300" : "text-zinc-600"
                          }`}
                        >
                          {child.title}
                        </span>
                        {child.id === activeChildId && (
                          <span className="mt-px shrink-0 text-[11px] font-medium text-violet-400">
                            {Math.round(percent)}%
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </GlassPanel>
  );
}
