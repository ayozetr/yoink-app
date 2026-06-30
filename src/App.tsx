import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AppLayout } from "./components/layout/AppLayout";
import { Splash } from "./components/layout/Splash";
import { EditMenu } from "./components/ui/EditMenu";
import { useFocusTrap } from "./lib/useFocusTrap";
import { DownloaderPanel } from "./features/downloader/DownloaderPanel";
import { QueuePanel } from "./features/queue/QueuePanel";
import { HistorySidebar } from "./features/history/HistorySidebar";

// Modal-ish, opened on demand — split into their own chunks to keep the initial
// bundle small (they're not needed on first paint).
const SettingsModal = lazy(() =>
  import("./features/settings/SettingsModal").then((m) => ({
    default: m.SettingsModal,
  })),
);
const AutoTagPanel = lazy(() =>
  import("./features/autotag/AutoTagPanel").then((m) => ({
    default: m.AutoTagPanel,
  })),
);
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
  const [retagItem, setRetagItem] = useState<HistoryEntry | null>(null);
  // External "analyze this URL" requests for the downloader (re-analyze from a
  // history row, drag-and-drop). The bumped nonce re-triggers the same URL.
  const [analyzeReq, setAnalyzeReq] = useState<{ url: string; nonce: number } | null>(null);
  const nonceRef = useRef(0);
  const requestAnalyze = useCallback((rawUrl: string) => {
    const url = rawUrl.trim();
    if (url) setAnalyzeReq({ url, nonce: (nonceRef.current += 1) });
  }, []);
  // Download queue: opened from the header button; keeps running while hidden.
  const [queueOpen, setQueueOpen] = useState(false);
  const [queuePending, setQueuePending] = useState(0);
  const { t } = useTranslation();
  // Trap focus inside the re-tag dialog while it's open (a11y).
  const retagDialogRef = useFocusTrap<HTMLDivElement>(retagItem?.filepath != null);

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
          // After ~30s of refused connections, drop the splash so the UI is
          // usable anyway — but keep retrying (at a slower cadence) instead of
          // giving up. Otherwise a backend that comes up late leaves the app
          // permanently settings-less and the Settings modal unopenable.
          if (attempt === 60 && !cancelled) setReady(true);
          const delay = attempt < 60 ? 500 : 2000;
          await new Promise((resolve) => setTimeout(resolve, delay));
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
      // Don't let the mod shortcuts (focus URL / toggle Settings) reach behind an
      // open modal dialog — focus must stay trapped and a second modal mustn't
      // stack on top. Escape (below) still closes whatever's open.
      if (
        mod &&
        document.querySelector('[role="dialog"][aria-modal="true"]')
      ) {
        return;
      }
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

  // Drag-and-drop a link onto the window → analyze it. Only intercepts text/URL
  // drags, and leaves drops onto editable fields alone (so the user can still
  // drop text into the URL input normally).
  useEffect(() => {
    // `dataTransfer.types` is a frozen array in Chromium but a DOMStringList in
    // WebKitGTK (Tauri's Linux webview) — `Array.from` reads both.
    const carriesText = (e: DragEvent) => {
      const types = e.dataTransfer ? Array.from(e.dataTransfer.types) : [];
      return types.includes("text/uri-list") || types.includes("text/plain");
    };
    const onEditable = (target: EventTarget | null) =>
      !!(target as HTMLElement | null)?.closest?.(
        "input, textarea, [contenteditable='true']",
      );
    const onDragOver = (e: DragEvent) => {
      if (carriesText(e) && !onEditable(e.target)) e.preventDefault(); // allow drop
    };
    const onDrop = (e: DragEvent) => {
      if (onEditable(e.target) || !carriesText(e)) return;
      e.preventDefault();
      const raw =
        e.dataTransfer!.getData("text/uri-list") ||
        e.dataTransfer!.getData("text/plain");
      const url = raw
        .split(/\r?\n/)
        .map((line) => line.trim())
        .find((line) => /^https?:\/\//i.test(line));
      if (url) requestAnalyze(url);
    };
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
    };
  }, [requestAnalyze]);

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
          <>
            <DownloaderPanel
              onDownloadFinished={refresh}
              onOpenSettings={() => setSettingsOpen(true)}
              onToggleQueue={() => setQueueOpen((o) => !o)}
              queueCount={queuePending}
              queueOpen={queueOpen}
              defaultKind={settings?.default_kind}
              defaultQuality={settings?.default_quality}
              defaultAudioFormat={settings?.default_audio_format}
              defaultEmbedSubs={settings?.default_embed_subs}
              defaultEmbedChapters={settings?.default_embed_chapters}
              fetchLyrics={settings?.fetch_lyrics}
              analyzeRequest={analyzeReq}
            />
            <QueuePanel
              open={queueOpen}
              onClose={() => setQueueOpen(false)}
              defaultKind={settings?.default_kind}
              defaultQuality={settings?.default_quality}
              defaultContainer={settings?.default_container}
              defaultAudioFormat={settings?.default_audio_format}
              onDownloadFinished={refresh}
              onPendingChange={setQueuePending}
            />
          </>
        }
        sidebar={
          <HistorySidebar
            items={history}
            stats={stats}
            onOpenFolder={handleOpenFolder}
            onOpenFile={handleOpenFile}
            onRetag={setRetagItem}
            onReanalyze={(entry) => requestAnalyze(entry.url)}
            onClear={handleClear}
          />
        }
      />

      {settingsOpen && settings && (
        <Suspense fallback={null}>
          <SettingsModal
            settings={settings}
            onClose={() => setSettingsOpen(false)}
            onSaved={setSettings}
          />
        </Suspense>
      )}

      {retagItem?.filepath && (
        <div
          role="presentation"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setRetagItem(null)}
        >
          <div
            ref={retagDialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={t("autotag.title")}
            tabIndex={-1}
            className="w-full max-w-2xl max-h-[90vh] overflow-y-auto outline-none"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              // Esc closes the dialog — unless an inner dropdown should eat it first.
              if (
                e.key === "Escape" &&
                !document.querySelector('[role="listbox"], [data-popover="true"]')
              ) {
                setRetagItem(null);
              }
            }}
          >
            <Suspense fallback={null}>
              <AutoTagPanel
                path={retagItem.filepath}
                filename={retagItem.filename ?? undefined}
                onDismiss={() => setRetagItem(null)}
                onApplied={refresh}
                autoOpen
                fetchLyrics={settings?.fetch_lyrics}
                panelClassName="!bg-[#16181f]"
              />
            </Suspense>
          </div>
        </div>
      )}

      <Splash visible={!ready} />
      <EditMenu />
    </>
  );
}
