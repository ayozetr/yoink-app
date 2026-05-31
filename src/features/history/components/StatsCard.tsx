import type { DownloadStats } from "../../../types/download";

interface StatsCardProps {
  stats: DownloadStats;
}

/** Aggregate download statistics shown at the bottom of the sidebar. */
export function StatsCard({ stats }: StatsCardProps) {
  return (
    <div className="rounded-2xl border border-violet-500/15 bg-gradient-to-r from-violet-500/10 to-blue-500/10 p-4">
      <p className="text-xs uppercase tracking-wider text-zinc-400">
        Estadísticas
      </p>

      <div className="grid grid-cols-2 gap-4 mt-3">
        <div>
          <p className="text-2xl font-bold">{stats.totalDownloads}</p>
          <p className="text-xs text-zinc-400">Descargas</p>
        </div>
        <div>
          <p className="text-2xl font-bold">{stats.transferred}</p>
          <p className="text-xs text-zinc-400">Transferidos</p>
        </div>
      </div>
    </div>
  );
}
