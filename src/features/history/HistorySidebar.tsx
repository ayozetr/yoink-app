import { useEffect, useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { HistoryItemCard } from "./components/HistoryItemCard";
import { StatsCard } from "./components/StatsCard";
import type { DownloadStats, HistoryEntry } from "../../types/download";

interface HistorySidebarProps {
  items: HistoryEntry[];
  stats: DownloadStats;
  historyVersion?: number;
  onOpenFolder?: (entry: HistoryEntry) => void;
  onOpenFile?: (entry: HistoryEntry) => void;
  onRetag?: (entry: HistoryEntry) => void;
  onClear?: () => void;
}

/** Right column: recent downloads list and aggregate stats. */
export function HistorySidebar({
  items,
  stats,
  historyVersion,
  onOpenFolder,
  onOpenFile,
  onRetag,
  onClear,
}: HistorySidebarProps) {
  const { t } = useTranslation();
  // Clearing history is destructive and irreversible — require a second click to
  // confirm (auto-resets after a few seconds), avoiding a heavier modal.
  const [confirming, setConfirming] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    },
    [],
  );

  const handleClear = () => {
    if (confirming) {
      if (resetTimer.current) clearTimeout(resetTimer.current);
      setConfirming(false);
      onClear?.();
    } else {
      setConfirming(true);
      resetTimer.current = setTimeout(() => setConfirming(false), 3000);
    }
  };

  return (
    <GlassPanel className="w-full lg:h-full p-5 flex flex-col">
      <div className="flex items-center justify-between mb-5">
        <h2 className="font-semibold text-lg">{t("history.title")}</h2>
        <button
          type="button"
          onClick={handleClear}
          disabled={items.length === 0}
          className={`flex items-center gap-1.5 text-sm transition disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-zinc-400 ${
            confirming ? "text-red-400" : "text-zinc-400 hover:text-red-400"
          }`}
        >
          <Trash2 size={15} />
          {confirming ? t("history.clearConfirm") : t("history.clear")}
        </button>
      </div>

      <div className="flex flex-col gap-3 overflow-auto">
        {items.length === 0 ? (
          <p className="text-sm text-zinc-400 py-8 text-center">
            {t("history.empty")}
          </p>
        ) : (
          items.map((item) => (
            <HistoryItemCard
              key={item.id}
              item={item}
              historyVersion={historyVersion}
              onOpenFolder={onOpenFolder}
              onOpenFile={onOpenFile}
              onRetag={onRetag}
            />
          ))
        )}
      </div>

      <div className="mt-auto pt-5">
        <StatsCard stats={stats} />
      </div>
    </GlassPanel>
  );
}
