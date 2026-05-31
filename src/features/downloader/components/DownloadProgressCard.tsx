import { GlassPanel } from "../../../components/ui/GlassPanel";
import { ProgressBar } from "../../../components/ui/ProgressBar";
import type { DownloadProgress } from "../../../types/download";

interface DownloadProgressCardProps {
  progress: DownloadProgress;
}

/** Live download indicator fed by yt-dlp progress_hooks (via WS/SSE). */
export function DownloadProgressCard({ progress }: DownloadProgressCardProps) {
  return (
    <GlassPanel className="p-5">
      <div className="flex justify-between mb-3">
        <span className="text-sm text-zinc-300">Descargando...</span>
        <span className="text-sm font-medium text-violet-400">
          {progress.percent}% • {progress.speed}
        </span>
      </div>
      <ProgressBar percent={progress.percent} />
    </GlassPanel>
  );
}
