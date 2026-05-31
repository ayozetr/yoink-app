import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, RotateCw, X } from "lucide-react";
import { DownloaderHeader } from "./components/DownloaderHeader";
import { UrlInput } from "./components/UrlInput";
import { PreviewCard, type DownloadSelection } from "./components/PreviewCard";
import { PlaylistCard } from "./components/PlaylistCard";
import { DownloadProgressCard } from "./components/DownloadProgressCard";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { fetchInfo, ApiError } from "../../lib/api";
import { startDownload, type DownloadHandle } from "../../lib/downloadSocket";
import type {
  DownloadCompletedEvent,
  DownloadProgressEvent,
  DownloadRequest,
  InfoResponse,
  PlaylistEntry,
} from "../../types/download";

interface DownloaderPanelProps {
  /** Called when a download terminates (completed or failed) to refresh history. */
  onDownloadFinished?: () => void;
}

interface DownloadJob {
  request: DownloadRequest;
  title: string;
}

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
export function DownloaderPanel({ onDownloadFinished }: DownloaderPanelProps) {
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

  const requestRef = useRef<AbortController | null>(null);
  const downloadRef = useRef<DownloadHandle | null>(null);
  const queueRef = useRef<DownloadJob[]>([]);
  const resultsRef = useRef<boolean[]>([]);
  const lastJobsRef = useRef<DownloadJob[]>([]);

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
  };

  const runJob = (index: number) => {
    const jobs = queueRef.current;
    if (index >= jobs.length) {
      setDownloading(false);
      setProgress(null);
      if (jobs.length > 1) {
        const failed = resultsRef.current.filter((ok) => !ok).length;
        setSummary({ completed: resultsRef.current.length - failed, failed });
      }
      return;
    }

    const job = jobs[index];
    setQueueIndex(index);
    setCurrentTitle(job.title);
    setDownloading(true);
    setProgress(initialProgress());

    downloadRef.current = startDownload(job.request, {
      onEvent: (event) => {
        if (event.type === "progress") {
          setProgress(event);
          return;
        }
        if (event.type === "completed") {
          resultsRef.current.push(true);
          if (jobs.length === 1) setCompleted(event);
        } else {
          resultsRef.current.push(false);
          if (jobs.length === 1) setDownloadError(event.message);
        }
        onDownloadFinished?.();
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

  const handleAnalyze = async () => {
    const trimmed = url.trim();
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
          : "Ocurrió un error inesperado al analizar la URL.",
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
    startQueue([
      {
        request: { url: target, kind: selection.kind, quality: selection.quality },
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
      <DownloaderHeader activeDownloads={downloading ? 1 : 0} />
      <UrlInput
        value={url}
        onChange={setUrl}
        onAnalyze={handleAnalyze}
        loading={loading}
      />

      {error && (
        <GlassPanel className="p-4 border-red-500/30">
          <div className="flex items-center gap-3 text-red-300">
            <AlertCircle size={18} className="shrink-0" />
            <span className="text-sm">{error}</span>
          </div>
        </GlassPanel>
      )}

      {info?.type === "video" && info.video && (
        <PreviewCard
          key={info.video.id}
          info={info.video}
          onDownload={handleDownload}
        />
      )}

      {info?.type === "playlist" && info.playlist && (
        <PlaylistCard
          key={info.playlist.id}
          playlist={info.playlist}
          onDownload={handleDownloadPlaylist}
          busy={downloading}
        />
      )}

      {downloading && queueTotal > 1 && (
        <p className="text-xs text-zinc-400 px-1">
          Descargando {queueIndex + 1} de {queueTotal}:{" "}
          <span className="text-zinc-200">{currentTitle}</span>
        </p>
      )}

      <DownloadProgressCard
        progress={progress}
        completed={completed}
        onCancel={resetDownload}
      />

      {summary && (
        <GlassPanel className="p-4">
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-sm text-zinc-200">
              <CheckCircle2 size={18} className="text-emerald-400 shrink-0" />
              {summary.completed} completadas
              {summary.failed > 0 && ` · ${summary.failed} con error`}
            </span>
            <button
              type="button"
              onClick={() => setSummary(null)}
              className="text-zinc-400 hover:text-white transition"
              aria-label="Cerrar resumen"
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
              Reintentar
            </button>
          </div>
        </GlassPanel>
      )}
    </>
  );
}
