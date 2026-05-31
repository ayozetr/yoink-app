import { useCallback, useEffect, useState } from "react";
import { AppLayout } from "./components/layout/AppLayout";
import { DownloaderPanel } from "./features/downloader/DownloaderPanel";
import { HistorySidebar } from "./features/history/HistorySidebar";
import { SettingsModal } from "./features/settings/SettingsModal";
import {
  clearHistory,
  fetchHistory,
  fetchSettings,
  fetchStats,
  openInFileManager,
} from "./lib/api";
import type {
  AppSettings,
  DownloadStats,
  HistoryEntry,
} from "./types/download";

const EMPTY_STATS: DownloadStats = {
  total_downloads: 0,
  total_bytes: 0,
  transferred: "0 B",
};

export default function App() {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [stats, setStats] = useState<DownloadStats>(EMPTY_STATS);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

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
    // Initial load; setState runs asynchronously after the fetches resolve.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    void fetchSettings()
      .then(setSettings)
      .catch(() => {});
  }, [refresh]);

  const handleOpenFolder = (entry: HistoryEntry) => {
    void openInFileManager(entry.filepath);
  };

  const handleClear = async () => {
    try {
      await clearHistory();
      await refresh();
    } catch {
      // Leave the current view if the clear request fails.
    }
  };

  return (
    <>
      <AppLayout
        main={
          <DownloaderPanel
            onDownloadFinished={refresh}
            onOpenSettings={() => setSettingsOpen(true)}
            defaultKind={settings?.default_kind}
            defaultQuality={settings?.default_quality}
          />
        }
        sidebar={
          <HistorySidebar
            items={history}
            stats={stats}
            onOpenFolder={handleOpenFolder}
            onClear={handleClear}
          />
        }
      />

      {settingsOpen && settings && (
        <SettingsModal
          settings={settings}
          onClose={() => setSettingsOpen(false)}
          onSaved={setSettings}
        />
      )}
    </>
  );
}
