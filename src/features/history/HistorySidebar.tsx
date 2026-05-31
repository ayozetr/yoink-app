import { GlassPanel } from "../../components/ui/GlassPanel";
import { Badge } from "../../components/ui/Badge";
import { HistoryItemCard } from "./components/HistoryItemCard";
import { StatsCard } from "./components/StatsCard";
import type { DownloadStats, HistoryItem } from "../../types/download";

interface HistorySidebarProps {
  items: HistoryItem[];
  stats: DownloadStats;
}

/** Right column: recent downloads list and aggregate stats. */
export function HistorySidebar({ items, stats }: HistorySidebarProps) {
  return (
    <GlassPanel className="w-[360px] shrink-0 p-5 flex flex-col">
      <div className="flex items-center justify-between mb-5">
        <h3 className="font-semibold text-lg">Historial de Descargas</h3>
        <Badge className="bg-violet-500/10 text-violet-300 border-violet-500/20">
          Recientes
        </Badge>
      </div>

      <div className="flex flex-col gap-3 overflow-auto">
        {items.map((item) => (
          <HistoryItemCard key={item.id} item={item} />
        ))}
      </div>

      <div className="mt-auto pt-5">
        <StatsCard stats={stats} />
      </div>
    </GlassPanel>
  );
}
