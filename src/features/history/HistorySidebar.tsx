import { GlassPanel } from "../../components/ui/GlassPanel";
import { Badge } from "../../components/ui/Badge";
import { HistoryItemCard } from "./components/HistoryItemCard";
import { StatsCard } from "./components/StatsCard";
import type { DownloadStats, HistoryEntry } from "../../types/download";

interface HistorySidebarProps {
  items: HistoryEntry[];
  stats: DownloadStats;
  onOpenFolder?: (entry: HistoryEntry) => void;
}

/** Right column: recent downloads list and aggregate stats. */
export function HistorySidebar({
  items,
  stats,
  onOpenFolder,
}: HistorySidebarProps) {
  return (
    <GlassPanel className="w-[360px] shrink-0 p-5 flex flex-col">
      <div className="flex items-center justify-between mb-5">
        <h3 className="font-semibold text-lg">Historial de Descargas</h3>
        <Badge className="bg-violet-500/10 text-violet-300 border-violet-500/20">
          Recientes
        </Badge>
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
