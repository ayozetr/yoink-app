import { CheckCircle2, Loader2 } from "lucide-react";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { ProgressBar } from "../../../components/ui/ProgressBar";
import type {
  DownloadCompletedEvent,
  DownloadProgressEvent,
} from "../../../types/download";

interface DownloadProgressCardProps {
  progress: DownloadProgressEvent | null;
  completed: DownloadCompletedEvent | null;
}

/** Live download indicator fed by yt-dlp progress_hooks (over WS). */
export function DownloadProgressCard({
  progress,
  completed,
}: DownloadProgressCardProps) {
  if (completed) {
    return (
      <GlassPanel className="p-5">
        <div className="flex items-center gap-3 text-emerald-300">
          <CheckCircle2 size={18} className="shrink-0" />
          <span className="text-sm">
            Descarga completada:{" "}
            <span className="font-medium text-emerald-200">
              {completed.filename}
            </span>
          </span>
        </div>
      </GlassPanel>
    );
  }

  if (!progress) return null;

  const isProcessing = progress.status === "processing";
  const label = isProcessing ? "Procesando (ffmpeg)..." : "Descargando...";
  const detail = isProcessing
    ? "Uniendo pistas"
    : [progress.speed, progress.eta && `ETA ${progress.eta}`]
        .filter(Boolean)
        .join(" • ");

  return (
    <GlassPanel className="p-5">
      <div className="flex justify-between mb-3">
        <span className="flex items-center gap-2 text-sm text-zinc-300">
          <Loader2 size={14} className="animate-spin text-violet-400" />
          {label}
        </span>
        <span className="text-sm font-medium text-violet-400">
          {Math.round(progress.percent)}%{detail && ` • ${detail}`}
        </span>
      </div>
      <ProgressBar percent={progress.percent} />
    </GlassPanel>
  );
}
