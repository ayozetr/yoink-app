import { AppLayout } from "./components/layout/AppLayout";
import { DownloaderPanel } from "./features/downloader/DownloaderPanel";
import { HistorySidebar } from "./features/history/HistorySidebar";
import type { DownloadStats, HistoryItem } from "./types/download";

// Placeholder data — replaced by real backend state once /api/info and the
// download history persistence layer are wired in.
const HISTORY: HistoryItem[] = [
  {
    id: 1,
    title: "How Linux Actually Boots - Complete Guide",
    status: "completed",
    kind: "video",
  },
  {
    id: 2,
    title: "Top 50 Cybersecurity Tools in 2026",
    status: "completed",
    kind: "audio",
  },
  {
    id: 3,
    title: "LoFi Mix for Coding & Studying",
    status: "error",
    kind: "video",
  },
  {
    id: 4,
    title: "Building a NAS Server at Home",
    status: "completed",
    kind: "audio",
  },
];

const STATS: DownloadStats = {
  totalDownloads: 248,
  transferred: "182 GB",
};

export default function App() {
  return (
    <AppLayout
      main={<DownloaderPanel />}
      sidebar={<HistorySidebar items={HISTORY} stats={STATS} />}
    />
  );
}
