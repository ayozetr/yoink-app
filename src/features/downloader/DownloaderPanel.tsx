import { useRef, useState } from "react";
import { AlertCircle } from "lucide-react";
import { DownloaderHeader } from "./components/DownloaderHeader";
import { UrlInput } from "./components/UrlInput";
import { PreviewCard, type DownloadSelection } from "./components/PreviewCard";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { fetchVideoInfo, ApiError } from "../../lib/api";
import type { VideoInfo } from "../../types/download";

/** Main column: orchestrates URL input, preview and download progress. */
export function DownloaderPanel() {
  const [url, setUrl] = useState("");
  const [info, setInfo] = useState<VideoInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track the in-flight request so a new analysis cancels the previous one.
  const requestRef = useRef<AbortController | null>(null);

  const handleAnalyze = async () => {
    const trimmed = url.trim();
    if (!trimmed) return;

    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;

    setLoading(true);
    setError(null);

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
    // TODO (Phase 3): start the job via POST /api/download and subscribe to
    // progress over WebSocket/SSE using `selection`.
    void selection;
  };

  return (
    <>
      <DownloaderHeader activeDownloads={0} />
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
    </>
  );
}
