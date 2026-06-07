import { useCallback, useEffect, useState } from "react";
import { AppLayout } from "./components/layout/AppLayout";
import { Splash } from "./components/layout/Splash";
import { EditMenu } from "./components/ui/EditMenu";
import { AutoTagPanel } from "./features/autotag/AutoTagPanel";
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

/** Reveal a finished download's folder in the OS file manager. */
function handleOpenFolder(entry: HistoryEntry) {
  void openInFileManager(entry.filepath);
}

/** Open a finished download's file with its default app. */
function handleOpenFile(entry: HistoryEntry) {
  void openInFileManager(entry.filepath, true);
}

export default function App() {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [stats, setStats] = useState<DownloadStats>(EMPTY_STATS);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [ready, setReady] = useState(false);
  // Bumped on every history refresh so rows can re-check their cover art (a file
  // tagged after download gains a cover the row didn't see on first render).
  const [historyVersion, setHistoryVersion] = useState(0);
  const [retagItem, setRetagItem] = useState<HistoryEntry | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [entries, aggregate] = await Promise.all([
        fetchHistory(),
        fetchStats(),
      ]);
      setHistory(entries);
      setStats(aggregate);
      setHistoryVersion((v) => v + 1);
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

  // Global shortcuts: Ctrl/Cmd+L focus the URL field, Ctrl/Cmd+, toggle Settings,
  // Esc close Settings.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "l") {
        e.preventDefault();
        const input = document.getElementById(
          "yoink-url-input",
        ) as HTMLInputElement | null;
        input?.focus();
        input?.select();
      } else if (mod && e.key === ",") {
        e.preventDefault();
        setSettingsOpen((open) => !open);
      } else if (e.key === "Escape") {
        // Let an open inner dropdown/popover consume Escape first; only close
        // Settings when none is open (so one Esc closes the dropdown, not both).
        if (document.querySelector('[role="listbox"], [data-popover="true"]')) {
          return;
        }
        setSettingsOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
            historyVersion={historyVersion}
            onOpenFolder={handleOpenFolder}
            onOpenFile={handleOpenFile}
            onRetag={setRetagItem}
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

      {retagItem?.filepath && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setRetagItem(null)}
        >
          <div
            className="w-full max-w-2xl max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <AutoTagPanel
              path={retagItem.filepath}
              filename={retagItem.filename ?? undefined}
              onDismiss={() => setRetagItem(null)}
              onApplied={refresh}
              autoOpen
            />
          </div>
        </div>
      )}

      <Splash visible={!ready} />
      <EditMenu />
    </>
  );
}
