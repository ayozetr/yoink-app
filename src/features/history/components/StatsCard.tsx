import { useTranslation } from "react-i18next";
import type { DownloadStats } from "../../../types/download";

interface StatsCardProps {
  stats: DownloadStats;
}

/** Aggregate download statistics shown at the bottom of the sidebar. */
export function StatsCard({ stats }: StatsCardProps) {
  const { t } = useTranslation();

  return (
    <div className="rounded-2xl border border-violet-500/15 bg-gradient-to-r from-violet-500/10 to-blue-500/10 p-4">
      <p className="text-xs uppercase tracking-wider text-zinc-400">
        {t("stats.title")}
      </p>

      <div className="grid grid-cols-2 gap-4 mt-3">
        <div>
          <p className="text-2xl font-bold">{stats.total_downloads}</p>
          <p className="text-xs text-zinc-400">{t("stats.downloads")}</p>
        </div>
        <div>
          <p className="text-2xl font-bold">{stats.transferred}</p>
          <p className="text-xs text-zinc-400">{t("stats.transferred")}</p>
        </div>
      </div>
    </div>
  );
}
