import { useCallback, useEffect, useState } from "react";
import { AppLayout } from "./components/layout/AppLayout";
import { Splash } from "./components/layout/Splash";
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
  const [ready, setReady] = useState(false);

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
    let cancelled = false;

    // The bundled backend (PyInstaller sidecar) can take several seconds to
    // start — unpacking ffmpeg is slow, especially on Windows. Retry the
    // initial load until it answers instead of giving up on the first refused
    // connection (which left the app with no data and Settings unopenable).
    const load = async () => {
      for (let attempt = 0; !cancelled; attempt++) {
        try {
          const loaded = await fetchSettings();
          if (cancelled) return;
          setSettings(loaded);
          await refresh();
          setReady(true);
          return;
        } catch {
          if (attempt >= 60) {
            // Give up after ~30s; drop the splash so the UI is usable anyway.
            if (!cancelled) setReady(true);
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, 500));
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
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

      <Splash visible={!ready} />
    </>
  );
}
