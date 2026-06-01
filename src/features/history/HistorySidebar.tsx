import { Trash2 } from "lucide-react";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { HistoryItemCard } from "./components/HistoryItemCard";
import { StatsCard } from "./components/StatsCard";
import type { DownloadStats, HistoryEntry } from "../../types/download";

interface HistorySidebarProps {
  items: HistoryEntry[];
  stats: DownloadStats;
  onOpenFolder?: (entry: HistoryEntry) => void;
  onClear?: () => void;
}

/** Right column: recent downloads list and aggregate stats. */
export function HistorySidebar({
  items,
  stats,
  onOpenFolder,
  onClear,
}: HistorySidebarProps) {
  return (
    <GlassPanel className="w-full lg:h-full p-5 flex flex-col">
      <div className="flex items-center justify-between mb-5">
        <h3 className="font-semibold text-lg">Historial de Descargas</h3>
        <button
          type="button"
          onClick={onClear}
          disabled={items.length === 0}
          className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-red-400 transition disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-zinc-400"
        >
          <Trash2 size={15} />
          Limpiar
        </button>
      </div>

      <div className="flex flex-col gap-3 overflow-auto">
        {items.length === 0 ? (
          <p className="text-sm text-zinc-500 py-8 text-center">
            Aún no hay descargas. Analiza una URL para empezar.
          </p>
        ) : (
          items.map((item) => (
            <HistoryItemCard
              key={item.id}
              item={item}
              onOpenFolder={onOpenFolder}
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
