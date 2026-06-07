import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, RotateCw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { DownloaderHeader } from "./components/DownloaderHeader";
import { UrlInput } from "./components/UrlInput";
import { PreviewCard, type DownloadSelection } from "./components/PreviewCard";
import { PlaylistCard } from "./components/PlaylistCard";
import { DownloadProgressCard } from "./components/DownloadProgressCard";
import { AutoTagPanel } from "../autotag/AutoTagPanel";
import { AutoTagBatchPanel } from "../autotag/AutoTagBatchPanel";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { fetchInfo, ApiError } from "../../lib/api";
import { startDownload, type DownloadHandle } from "../../lib/downloadSocket";
import type {
  DownloadCompletedEvent,
  DownloadProgressEvent,
  DownloadRequest,
  InfoResponse,
  MediaKind,
  PlaylistEntry,
} from "../../types/download";

interface DownloaderPanelProps {
  /** Called when a download terminates (completed or failed) to refresh history. */
  onDownloadFinished?: () => void;
  /** Open the settings modal. */
  onOpenSettings?: () => void;
  /** Default media kind / quality from settings, used to seed the selectors. */
  defaultKind?: MediaKind;
  defaultQuality?: string;
}

interface DownloadJob {
  request: DownloadRequest;
  title: string;
}

/** A finished audio file eligible for tagging. */
type TagItem = { path: string; filename: string };

/** Audio extensions Yoink can tag (matched on the output filepath). */
const AUDIO_EXT = /\.(mp3|m4a|flac|wav|opus|ogg|aac)$/i;

function initialProgress(): DownloadProgressEvent {
  return {
    type: "progress",
    status: "downloading",
    percent: 0,
    downloaded_bytes: null,
    total_bytes: null,
    speed: null,
    eta: null,
    filename: null,
  };
}

/** Main column: orchestrates URL input, preview/playlist and download progress. */
export function DownloaderPanel({
  onDownloadFinished,
  onOpenSettings,
  defaultKind,
  defaultQuality,
}: DownloaderPanelProps) {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [info, setInfo] = useState<InfoResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [progress, setProgress] = useState<DownloadProgressEvent | null>(null);
  const [completed, setCompleted] = useState<DownloadCompletedEvent | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  // Queue position (1-based shown as index+1) and a multi-item summary.
  const [queueIndex, setQueueIndex] = useState(0);
  const [queueTotal, setQueueTotal] = useState(0);
  const [currentTitle, setCurrentTitle] = useState("");
  const [summary, setSummary] = useState<{ completed: number; failed: number } | null>(
    null,
  );
  // Auto-tag: whether the user dismissed each inline tagging card (single vs
  // playlist batch are independent), + the last download kind so the card only
  // shows for audio downloads.
  const [tagDismissedSingle, setTagDismissedSingle] = useState(false);
  const [tagDismissedBatch, setTagDismissedBatch] = useState(false);
  const [lastKind, setLastKind] = useState<MediaKind | null>(null);
  // Audio files from a finished playlist, for the batch tagging card.
  const [batchItems, setBatchItems] = useState<TagItem[]>([]);

  const requestRef = useRef<AbortController | null>(null);
  const downloadRef = useRef<DownloadHandle | null>(null);
  const queueRef = useRef<DownloadJob[]>([]);
  const resultsRef = useRef<boolean[]>([]);
  const lastJobsRef = useRef<DownloadJob[]>([]);
  const audioPathsRef = useRef<TagItem[]>([]);

  // Tear down the socket if the panel unmounts mid-download.
  useEffect(() => () => downloadRef.current?.cancel(), []);

  const resetDownload = () => {
    downloadRef.current?.cancel();
    downloadRef.current = null;
    queueRef.current = [];
    resultsRef.current = [];
    setProgress(null);
    setCompleted(null);
    setDownloadError(null);
    setDownloading(false);
    setSummary(null);
    setQueueTotal(0);
    setQueueIndex(0);
    setTagDismissedSingle(false);
    setTagDismissedBatch(false);
    setBatchItems([]);
    audioPathsRef.current = [];
  };

  const handleCancel = () => {
    // A cancelled queue may already have items the backend finished and persisted
    // to history before the user hit cancel. resetDownload() (also used for other
    // resets) doesn't refresh, so trigger it here so those downloads show up.
    resetDownload();
    onDownloadFinished?.();
  };

  const runJob = (index: number) => {
    const jobs = queueRef.current;
    if (index >= jobs.length) {
      setDownloading(false);
      setProgress(null);
      if (jobs.length > 1) {
        const failed = resultsRef.current.filter((ok) => !ok).length;
        setSummary({ completed: resultsRef.current.length - failed, failed });
        if (audioPathsRef.current.length > 0) {
          setBatchItems([...audioPathsRef.current]);
        }
      }
      // Refresh history/stats once, when the whole queue is done — not per item.
      onDownloadFinished?.();
      return;
    }

    const job = jobs[index];
    setQueueIndex(index);
    setCurrentTitle(job.title);
    setDownloading(true);
    setProgress(initialProgress());

    let settled = false;
    downloadRef.current = startDownload(job.request, {
      onEvent: (event) => {
        // Ignore anything after a terminal event: a buffered or abnormal-close
        // error could otherwise double-count this item and double-advance the
        // queue (onClose already guards on `settled`; keep onEvent symmetric).
        if (settled) return;
        if (event.type === "progress") {
          setProgress(event);
          return;
        }
        settled = true;
        if (event.type === "completed") {
          resultsRef.current.push(true);
          if (jobs.length === 1) setCompleted(event);
          else if (AUDIO_EXT.test(event.filepath)) {
            audioPathsRef.current.push({
              path: event.filepath,
              filename: event.filename,
            });
          }
        } else {
          resultsRef.current.push(false);
          if (jobs.length === 1) setDownloadError(event.message);
        }
        runJob(index + 1);
      },
      onClose: () => {
        // Socket closed with no terminal event (backend crash / dropped
        // connection): fail this job so the queue doesn't spin forever.
        if (settled) return;
        settled = true;
        resultsRef.current.push(false);
        if (jobs.length === 1) {
          setDownloadError(t("errors.downloadConnectionLost"));
        }
        runJob(index + 1);
      },
    });
  };

  const startQueue = (jobs: DownloadJob[]) => {
    resetDownload();
    if (jobs.length === 0) return;
    queueRef.current = jobs;
    lastJobsRef.current = jobs;
    resultsRef.current = [];
    setQueueTotal(jobs.length);
    runJob(0);
  };

  const handleAnalyze = async (overrideUrl?: string) => {
    const trimmed = (overrideUrl ?? url).trim();
    if (!trimmed) return;

    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;

    setLoading(true);
    setError(null);
    resetDownload();

    try {
      const result = await fetchInfo(trimmed, controller.signal);
      setInfo(result);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setInfo(null);
      setError(
        cause instanceof ApiError
          ? cause.message
          : t("panel.analyzeError"),
      );
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setLoading(false);
      }
    }
  };

  const handleDownload = (selection: DownloadSelection) => {
    const target = url.trim();
    setLastKind(selection.kind);
    startQueue([
      {
        request: {
          url: target,
          kind: selection.kind,
          quality: selection.quality,
          container: selection.container,
          audio_format: selection.audio_format,
          embed_subs: selection.embed_subs,
          subtitle_lang: selection.subtitle_lang,
          embed_chapters: selection.embed_chapters,
          audio_multistreams: selection.audio_multistreams,
          trim_start: selection.trim_start,
          trim_end: selection.trim_end,
        },
        title: info?.video?.title ?? target,
      },
    ]);
  };

  const handleDownloadPlaylist = (
    entries: PlaylistEntry[],
    selection: DownloadSelection,
  ) => {
    startQueue(
      entries.map((entry) => ({
        request: {
          url: entry.url,
          kind: selection.kind,
          quality: selection.quality,
          container: selection.container,
          audio_format: selection.audio_format,
          embed_subs: selection.embed_subs,
          subtitle_lang: selection.subtitle_lang,
          embed_chapters: selection.embed_chapters,
          audio_multistreams: selection.audio_multistreams,
        },
        title: entry.title,
      })),
    );
  };

  const handleRetry = () => {
    if (lastJobsRef.current.length > 0) startQueue(lastJobsRef.current);
  };

  return (
    <>
      <DownloaderHeader
        activeDownloads={downloading ? 1 : 0}
        onOpenSettings={onOpenSettings}
      />
      <UrlInput
        value={url}
        onChange={setUrl}
        onAnalyze={handleAnalyze}
        onSelectResult={(entry) => {
          setUrl(entry.url);
          void handleAnalyze(entry.url);
        }}
        loading={loading}
      />

      {error && (
        <GlassPanel className="p-4 border-red-500/30">
          <div className="flex items-center gap-3 text-red-300">
            <AlertCircle size={18} className="shrink-0" />
            <span className="text-sm">{error}</span>
          </div>
          {/forbidden|\b403\b/i.test(error) && (
            <p className="mt-2 pl-[30px] text-xs text-zinc-400">
              {t("panel.blockedHint")}
            </p>
          )}
        </GlassPanel>
      )}

      {info?.type === "video" && info.video && (
        <PreviewCard
          key={info.video.id}
          info={info.video}
          onDownload={handleDownload}
          defaultKind={defaultKind}
          defaultQuality={defaultQuality}
        />
      )}

      {info?.type === "playlist" && info.playlist && (
        <PlaylistCard
          key={info.playlist.id}
          playlist={info.playlist}
          onDownload={handleDownloadPlaylist}
          busy={downloading}
          defaultKind={defaultKind}
          defaultQuality={defaultQuality}
        />
      )}

      {downloading && queueTotal > 1 && (
        <p className="text-xs text-zinc-400 px-1">
          {t("panel.downloadingOf", { current: queueIndex + 1, total: queueTotal })}{" "}
          <span className="text-zinc-200">{currentTitle}</span>
        </p>
      )}

      <DownloadProgressCard
        progress={progress}
        completed={completed}
        onCancel={handleCancel}
      />

      {completed?.filepath && lastKind === "audio" && !downloading && !tagDismissedSingle && (
        <AutoTagPanel
          path={completed.filepath}
          filename={completed.filename}
          onDismiss={() => setTagDismissedSingle(true)}
        />
      )}

      {batchItems.length > 0 && !downloading && !tagDismissedBatch && (
        <AutoTagBatchPanel
          items={batchItems}
          onDismiss={() => setTagDismissedBatch(true)}
        />
      )}

      {summary && (
        <GlassPanel className="p-4">
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-sm text-zinc-200">
              <CheckCircle2 size={18} className="text-emerald-400 shrink-0" />
              {t("panel.summaryDone", { count: summary.completed })}
              {summary.failed > 0 &&
                t("panel.summaryFailed", { count: summary.failed })}
            </span>
            <button
              type="button"
              onClick={() => setSummary(null)}
              className="text-zinc-400 hover:text-white transition"
              aria-label={t("panel.closeSummary")}
            >
              <X size={16} />
            </button>
          </div>
        </GlassPanel>
      )}

      {downloadError && (
        <GlassPanel className="p-4 border-red-500/30">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 text-red-300 min-w-0">
              <AlertCircle size={18} className="shrink-0" />
              <span className="text-sm truncate">{downloadError}</span>
            </div>
            <button
              type="button"
              onClick={handleRetry}
              className="flex items-center gap-1.5 text-sm text-zinc-300 hover:text-white transition shrink-0"
            >
              <RotateCw size={15} />
              {t("panel.retry")}
            </button>
          </div>
        </GlassPanel>
      )}

    </>
  );
}
