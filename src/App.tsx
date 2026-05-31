import { useCallback, useEffect, useState } from "react";
import { AppLayout } from "./components/layout/AppLayout";
import { DownloaderPanel } from "./features/downloader/DownloaderPanel";
import { HistorySidebar } from "./features/history/HistorySidebar";
import { fetchHistory, fetchStats, openInFileManager } from "./lib/api";
import type { DownloadStats, HistoryEntry } from "./types/download";

const EMPTY_STATS: DownloadStats = {
  total_downloads: 0,
  total_bytes: 0,
  transferred: "0 B",
};

export default function App() {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [stats, setStats] = useState<DownloadStats>(EMPTY_STATS);

  const refresh = useCallback(async () => {
    try {
      const [entries, aggregate] = await Promise.all([
        fetchHistory(),
        fetchStats(),
      ]);
      setHistory(entries);
      setStats(aggregate);
    } catch {
      // Backend not reachable yet — keep the current view rather than crash.
    }
  }, []);

  useEffect(() => {
    // Initial load; setState runs asynchronously after the fetch resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  const handleOpenFolder = (entry: HistoryEntry) => {
    void openInFileManager(entry.filepath);
  };

  return (
    <AppLayout
      main={<DownloaderPanel onDownloadFinished={refresh} />}
      sidebar={
        <HistorySidebar
          items={history}
          stats={stats}
          onOpenFolder={handleOpenFolder}
        />
      }
    />
  );
}
