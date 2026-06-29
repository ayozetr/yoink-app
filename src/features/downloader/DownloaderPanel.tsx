import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, DownloadCloud, RotateCw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { DownloaderHeader } from "./components/DownloaderHeader";
import { UrlInput } from "./components/UrlInput";
import { PreviewCard, type DownloadSelection } from "./components/PreviewCard";
import { PlaylistCard } from "./components/PlaylistCard";
import { DownloadProgressCard } from "./components/DownloadProgressCard";
const AutoTagPanel = lazy(() =>
  import("../autotag/AutoTagPanel").then((m) => ({ default: m.AutoTagPanel })),
);
const AutoTagBatchPanel = lazy(() =>
  import("../autotag/AutoTagBatchPanel").then((m) => ({
    default: m.AutoTagBatchPanel,
  })),
);
import { CopyButton } from "../../components/ui/CopyButton";
import { GlassPanel } from "../../components/ui/GlassPanel";
import {
  fetchInfo,
  isMusicUrl,
  resolveMusic,
  ApiError,
  type SearchSource,
} from "../../lib/api";
import { loadSearchSource, persistSearchSource } from "../../lib/searchSource";
import { MusicImportCard } from "../music/MusicImportCard";
import type { MusicImportInfo } from "../../types/music";
import { startDownload, type DownloadHandle } from "../../lib/downloadSocket";
import { clearBatch, loadPendingBatch, saveBatch } from "../../lib/batchStore";
import {
  acquireDownloadLock,
  releaseDownloadLock,
  useDownloadLock,
} from "../../lib/downloadLock";
import { setWindowProgress } from "../../lib/windowProgress";
import { notify } from "../../lib/notify";
import type {
  DownloadCompletedEvent,
  DownloadProgressEvent,
  DownloadRequest,
  AudioFormat,
  InfoResponse,
  MediaKind,
  PlaylistEntry,
} from "../../types/download";

interface DownloaderPanelProps {
  /** Called when a download terminates (completed or failed) to refresh history. */
  onDownloadFinished?: () => void;
  /** Open the settings modal. */
  onOpenSettings?: () => void;
  /** Toggle the download queue panel + how many items it has unfinished. */
  onToggleQueue?: () => void;
  queueCount?: number;
  queueOpen?: boolean;
  /** Default media kind / quality from settings, used to seed the selectors. */
  defaultKind?: MediaKind;
  defaultQuality?: string;
  defaultAudioFormat?: AudioFormat;
  /** Persisted "embed subtitles/chapters by default" toggles (seed the preview). */
  defaultEmbedSubs?: boolean;
  defaultEmbedChapters?: boolean;
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
  onToggleQueue,
  queueCount = 0,
  queueOpen,
  defaultKind,
  defaultQuality,
  defaultAudioFormat,
  defaultEmbedSubs,
  defaultEmbedChapters,
}: DownloaderPanelProps) {
  const { t } = useTranslation();
  // Shared download lock: another engine (the queue / music import) holding it
  // disables this panel's download buttons so two jobs can't collide on disk.
  const lockOwner = useDownloadLock();
  const lockedByOther = lockOwner !== null && lockOwner !== "downloader";
  const [url, setUrl] = useState("");
  // The URL we actually analyzed (the field text at analyze time). Downloads and
  // the music card key off this, not the live field — the user may edit the field
  // after analysis without re-analyzing.
  const [analyzedUrl, setAnalyzedUrl] = useState("");
  const [info, setInfo] = useState<InfoResponse | null>(null);
  const [musicInfo, setMusicInfo] = useState<MusicImportInfo | null>(null);
  // Search platform for the URL-field typeahead; the toggle lives in the header.
  const [searchSource, setSearchSource] = useState<SearchSource>(loadSearchSource);
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
  // A batch left unfinished by a previous session (persisted), offered for resume.
  // Read once at mount from localStorage so an interrupted multi-item download
  // can be picked up where it stopped.
  const [resumeJobs, setResumeJobs] = useState<DownloadJob[] | null>(() => {
    const pending = loadPendingBatch();
    return pending.length > 0 ? pending : null;
  });
  // The jobs that failed in the last batch, for a "retry failed" action.
  const [retryJobs, setRetryJobs] = useState<DownloadJob[]>([]);

  const requestRef = useRef<AbortController | null>(null);
  const downloadRef = useRef<DownloadHandle | null>(null);
  const queueRef = useRef<DownloadJob[]>([]);
  const resultsRef = useRef<boolean[]>([]);
  const lastJobsRef = useRef<DownloadJob[]>([]);
  const audioPathsRef = useRef<TagItem[]>([]);

  // Tear down the socket + free the lock if the panel unmounts mid-download.
  // Note: this does NOT clear the persisted batch — that's the point, so an
  // interrupted multi-item download can be resumed on the next launch.
  useEffect(
    () => () => {
      downloadRef.current?.cancel();
      releaseDownloadLock("downloader");
    },
    [],
  );

  const resetDownload = (opts?: { keepBatch?: boolean }) => {
    downloadRef.current?.cancel();
    downloadRef.current = null;
    releaseDownloadLock("downloader");
    // Analyzing a new URL mid-download cancels the active job; keep the persisted
    // batch so the in-progress run stays resumable instead of being silently lost.
    if (!opts?.keepBatch) clearBatch();
    setResumeJobs(null);
    setRetryJobs([]);
    queueRef.current = [];
    resultsRef.current = [];
    setProgress(null);
    setWindowProgress(null);
    setCompleted(null);
    setDownloadError(null);
    setDownloading(false);
    setSummary(null);
    setQueueTotal(0);
    setQueueIndex(0);
    setCurrentTitle("");
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
      releaseDownloadLock("downloader");
      clearBatch(); // whole batch finished — nothing left to resume
      setDownloading(false);
      setProgress(null);
      setWindowProgress(null);
      const failed = resultsRef.current.filter((ok) => !ok).length;
      const ok = resultsRef.current.length - failed;
      if (jobs.length > 1) {
        setSummary({ completed: ok, failed });
        // Keep the failed jobs (results are in job order) so just those can be
        // retried from the summary.
        setRetryJobs(jobs.filter((_, i) => resultsRef.current[i] === false));
        if (audioPathsRef.current.length > 0) {
          setBatchItems([...audioPathsRef.current]);
        }
        void notify(
          t("notify.queueDone"),
          t("notify.queueSummary", { completed: ok, failed }),
        );
      } else if (failed === 0) {
        void notify(t("notify.completed"), jobs[0].title);
      } else {
        void notify(t("notify.failed"), jobs[0].title);
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
          setWindowProgress(event.percent);
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
        // Persist progress so a close/crash resumes from the next item.
        saveBatch(jobs, resultsRef.current.length);
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
        saveBatch(jobs, resultsRef.current.length);
        runJob(index + 1);
      },
    });
  };

  const startQueue = (jobs: DownloadJob[]) => {
    resetDownload();
    if (jobs.length === 0) return;
    // Take the shared lock so the queue / music import can't run concurrently
    // (the buttons are already disabled when another engine holds it; this is
    // the correctness backstop against a race).
    if (!acquireDownloadLock("downloader")) return;
    queueRef.current = jobs;
    lastJobsRef.current = jobs;
    resultsRef.current = [];
    saveBatch(jobs, 0); // persist so the batch survives a close mid-run
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
    // Keep the resumable batch if a download is in progress — analyzing a new URL
    // cancels the active job but shouldn't wipe its resume record.
    resetDownload({ keepBatch: downloading });

    try {
      if (isMusicUrl(trimmed)) {
        setInfo(null);
        setMusicInfo(await resolveMusic(trimmed, controller.signal));
      } else {
        setMusicInfo(null);
        setInfo(await fetchInfo(trimmed, controller.signal));
      }
      // Remember exactly what we analyzed, so downloads / the music-card key
      // target the analyzed source even if the user edits the field after.
      setAnalyzedUrl(trimmed);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setInfo(null);
      setMusicInfo(null);
      setError(
        cause instanceof ApiError
          ? cause.status === 503
            ? t("panel.analyzeTransient")
            : cause.message
          : t("panel.analyzeError"),
      );
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setLoading(false);
      }
    }
  };

  // Paste-and-analyze: Ctrl/Cmd+Shift+V grabs a URL from the clipboard and
  // analyzes it in one go (a keyboard gesture lets the clipboard read through).
  const analyzeRef = useRef(handleAnalyze);
  useEffect(() => {
    analyzeRef.current = handleAnalyze;
  });
  useEffect(() => {
    const onKeydown = (e: KeyboardEvent) => {
      if (e.shiftKey && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "v") {
        e.preventDefault();
        void (async () => {
          try {
            const text = (await navigator.clipboard.readText()).trim();
            if (text) {
              setUrl(text);
              void analyzeRef.current(text);
            }
          } catch {
            // Clipboard unavailable / blocked — ignore.
          }
        })();
      }
    };
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, []);

  const handleDownload = (selection: DownloadSelection) => {
    // The analyzed source URL, not the live field (which the user may have
    // edited since analyzing — that would download the wrong thing / 422).
    const target = analyzedUrl || url.trim();
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
          is_vr: selection.is_vr,
          vr_layout: selection.vr_layout,
          estimated_size: selection.estimated_size,
        },
        title: info?.video?.title ?? target,
      },
    ]);
  };

  const handleDownloadPlaylist = (
    entries: PlaylistEntry[],
    selection: DownloadSelection,
  ) => {
    // Remember the kind so a finished single-entry audio playlist still offers
    // the auto-tag card (the single-download path already sets this).
    setLastKind(selection.kind);
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
          is_vr: selection.is_vr,
          vr_layout: selection.vr_layout,
        },
        title: entry.title,
      })),
    );
  };

  const handleRetry = () => {
    if (lastJobsRef.current.length > 0) startQueue(lastJobsRef.current);
  };

  // Resume / discard a batch left unfinished by a previous session.
  const handleResume = () => {
    if (resumeJobs && resumeJobs.length > 0) startQueue(resumeJobs);
  };
  const handleDismissResume = () => {
    setResumeJobs(null);
    clearBatch();
  };

  // Re-run only the items that failed in the last batch.
  const handleRetryFailed = () => {
    if (retryJobs.length > 0) startQueue(retryJobs);
  };

  return (
    <>
      <DownloaderHeader
        queueCount={queueCount}
        queueOpen={queueOpen}
        onToggleQueue={onToggleQueue}
        onOpenSettings={onOpenSettings}
        searchSource={searchSource}
        onSearchSourceChange={(source) => {
          setSearchSource(source);
          persistSearchSource(source);
        }}
      />
      <UrlInput
        value={url}
        onChange={setUrl}
        onAnalyze={handleAnalyze}
        onSelectResult={(entry) => {
          setUrl(entry.url);
          void handleAnalyze(entry.url);
        }}
        searchSource={searchSource}
        loading={loading}
      />

      {resumeJobs && resumeJobs.length > 0 && !downloading && (
        <GlassPanel className="p-4">
          <div className="flex items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-2 text-sm text-zinc-200">
              <RotateCw size={16} className="shrink-0 text-violet-400" />
              {t("panel.resumeTitle", { count: resumeJobs.length })}
            </span>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={handleResume}
                className="flex items-center gap-1.5 rounded-lg border border-violet-500/40 bg-violet-600/10 px-3 py-1.5 text-sm text-white transition hover:bg-violet-600/20"
              >
                <RotateCw size={14} />
                {t("panel.resume")}
              </button>
              <button
                type="button"
                onClick={handleDismissResume}
                className="text-sm text-zinc-400 transition hover:text-white"
              >
                {t("panel.resumeDismiss")}
              </button>
            </div>
          </div>
        </GlassPanel>
      )}

      {!loading &&
        !error &&
        !info &&
        !musicInfo &&
        !progress &&
        !completed &&
        !downloading &&
        batchItems.length === 0 &&
        !resumeJobs &&
        !summary &&
        !downloadError && (
          <GlassPanel className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <DownloadCloud className="size-10 text-zinc-600" />
            <div>
              <p className="text-sm font-medium text-zinc-200">
                {t("panel.emptyTitle")}
              </p>
              <p className="mx-auto mt-1 max-w-xs text-xs text-zinc-500">
                {t("panel.emptyHint")}
              </p>
            </div>
          </GlassPanel>
        )}

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
          defaultEmbedSubs={defaultEmbedSubs}
          defaultEmbedChapters={defaultEmbedChapters}
          locked={lockedByOther}
        />
      )}

      {info?.type === "playlist" && info.playlist && (
        <PlaylistCard
          key={info.playlist.id}
          playlist={info.playlist}
          onDownload={handleDownloadPlaylist}
          busy={downloading || lockedByOther}
          defaultKind={defaultKind}
          defaultQuality={defaultQuality}
        />
      )}

      {musicInfo && (
        <MusicImportCard
          key={analyzedUrl}
          info={musicInfo}
          defaultAudioFormat={defaultAudioFormat}
          onDownloadFinished={onDownloadFinished}
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
        onDismiss={() => setCompleted(null)}
      />

      {completed?.filepath && lastKind === "audio" && !downloading && !tagDismissedSingle && (
        <Suspense fallback={null}>
          <AutoTagPanel
            path={completed.filepath}
            filename={completed.filename}
            onDismiss={() => setTagDismissedSingle(true)}
            onApplied={onDownloadFinished}
          />
        </Suspense>
      )}

      {batchItems.length > 0 && !downloading && !tagDismissedBatch && (
        <Suspense fallback={null}>
          <AutoTagBatchPanel
            items={batchItems}
            onDismiss={() => setTagDismissedBatch(true)}
            onApplied={onDownloadFinished}
          />
        </Suspense>
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
            <div className="flex shrink-0 items-center gap-3">
              {summary.failed > 0 && retryJobs.length > 0 && (
                <button
                  type="button"
                  onClick={handleRetryFailed}
                  className="flex items-center gap-1.5 text-sm text-zinc-300 transition hover:text-white"
                >
                  <RotateCw size={15} />
                  {t("panel.retryFailed", { count: retryJobs.length })}
                </button>
              )}
              <button
                type="button"
                onClick={() => setSummary(null)}
                className="text-zinc-400 hover:text-white transition"
                aria-label={t("panel.closeSummary")}
              >
                <X size={16} />
              </button>
            </div>
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
            <div className="flex items-center gap-2 shrink-0">
              <CopyButton text={downloadError} label={t("common.copyError")} />
              <button
                type="button"
                onClick={handleRetry}
                className="flex items-center gap-1.5 text-sm text-zinc-300 hover:text-white transition"
              >
                <RotateCw size={15} />
                {t("panel.retry")}
              </button>
            </div>
          </div>
          {/forbidden|\b403\b/i.test(downloadError) && (
            <p className="mt-2 pl-[30px] text-xs text-zinc-400">
              {t("panel.blockedHint")}
            </p>
          )}
        </GlassPanel>
      )}

    </>
  );
}
