import { useEffect, useRef, useState } from "react";
import { AlertCircle } from "lucide-react";
import { DownloaderHeader } from "./components/DownloaderHeader";
import { UrlInput } from "./components/UrlInput";
import { PreviewCard, type DownloadSelection } from "./components/PreviewCard";
import { DownloadProgressCard } from "./components/DownloadProgressCard";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { fetchVideoInfo, ApiError } from "../../lib/api";
import { startDownload, type DownloadHandle } from "../../lib/downloadSocket";
import type {
  DownloadCompletedEvent,
  DownloadProgressEvent,
  DownloadRequest,
  VideoInfo,
} from "../../types/download";

/** Main column: orchestrates URL input, preview and download progress. */
export function DownloaderPanel() {
  const [url, setUrl] = useState("");
  const [info, setInfo] = useState<VideoInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [progress, setProgress] = useState<DownloadProgressEvent | null>(null);
  const [completed, setCompleted] = useState<DownloadCompletedEvent | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  // Track the in-flight analysis request and the active download socket.
  const requestRef = useRef<AbortController | null>(null);
  const downloadRef = useRef<DownloadHandle | null>(null);

  // Tear down the socket if the panel unmounts mid-download.
  useEffect(() => () => downloadRef.current?.cancel(), []);

  const resetDownload = () => {
    downloadRef.current?.cancel();
    downloadRef.current = null;
    setProgress(null);
    setCompleted(null);
    setDownloadError(null);
    setDownloading(false);
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
      const result = await fetchVideoInfo(trimmed, controller.signal);
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
    resetDownload();
    setDownloading(true);
    setProgress({
      type: "progress",
      status: "downloading",
      percent: 0,
      downloaded_bytes: null,
      total_bytes: null,
      speed: null,
      eta: null,
      filename: null,
    });

    const request: DownloadRequest = {
      url: url.trim(),
      kind: selection.kind,
      quality: selection.quality,
    };

    downloadRef.current = startDownload(request, {
      onEvent: (event) => {
        if (event.type === "progress") {
          setProgress(event);
        } else if (event.type === "completed") {
          setCompleted(event);
          setProgress(null);
          setDownloading(false);
        } else {
          setDownloadError(event.message);
          setProgress(null);
          setDownloading(false);
        }
      },
      onClose: () => setDownloading(false),
    });
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

      {info && (
        <PreviewCard key={info.id} info={info} onDownload={handleDownload} />
      )}

      <DownloadProgressCard progress={progress} completed={completed} />

      {downloadError && (
        <GlassPanel className="p-4 border-red-500/30">
          <div className="flex items-center gap-3 text-red-300">
            <AlertCircle size={18} className="shrink-0" />
            <span className="text-sm">{downloadError}</span>
          </div>
        </GlassPanel>
      )}
    </>
  );
}
