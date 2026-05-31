import { useState } from "react";
import { DownloaderHeader } from "./components/DownloaderHeader";
import { UrlInput } from "./components/UrlInput";
import { PreviewCard } from "./components/PreviewCard";
import { DownloadProgressCard } from "./components/DownloadProgressCard";
import type { DownloadProgress, VideoInfo } from "../../types/download";

// Placeholder data until the FastAPI backend (/api/info, WS progress) is wired in.
const SAMPLE_INFO: VideoInfo = {
  title: "Complete React + TypeScript Course 2026",
  duration: "1h 24m 18s",
};

const SAMPLE_PROGRESS: DownloadProgress = {
  percent: 45,
  speed: "3 MB/s",
};

/** Main column: orchestrates URL input, preview and download progress. */
export function DownloaderPanel() {
  const [url, setUrl] = useState("https://youtube.com/watch?v=example");

  const handleAnalyze = () => {
    // TODO: call POST /api/info on the FastAPI backend to fetch real metadata.
  };

  const handleDownload = () => {
    // TODO: start the download and subscribe to progress over WebSocket/SSE.
  };

  return (
    <>
      <DownloaderHeader activeDownloads={1} />
      <UrlInput value={url} onChange={setUrl} onAnalyze={handleAnalyze} />
      <PreviewCard info={SAMPLE_INFO} onDownload={handleDownload} />
      <DownloadProgressCard progress={SAMPLE_PROGRESS} />
    </>
  );
}
