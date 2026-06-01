import { CheckCircle2, Loader2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { ProgressBar } from "../../../components/ui/ProgressBar";
import type {
  DownloadCompletedEvent,
  DownloadProgressEvent,
} from "../../../types/download";

interface DownloadProgressCardProps {
  progress: DownloadProgressEvent | null;
  completed: DownloadCompletedEvent | null;
  onCancel?: () => void;
}

/** Live download indicator fed by yt-dlp progress_hooks (over WS). */
export function DownloadProgressCard({
  progress,
  completed,
  onCancel,
}: DownloadProgressCardProps) {
  const { t } = useTranslation();

  if (completed) {
    return (
      <GlassPanel className="p-5">
        <div className="flex items-center gap-3 text-emerald-300">
          <CheckCircle2 size={18} className="shrink-0" />
          <span className="text-sm">
            {t("progress.completed")}{" "}
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
  const label = isProcessing ? t("progress.processing") : t("progress.downloading");
  const detail = isProcessing
    ? t("progress.merging")
    : [progress.speed, progress.eta && `ETA ${progress.eta}`]
        .filter(Boolean)
        .join(" • ");

  return (
    <GlassPanel className="p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="flex items-center gap-2 text-sm text-zinc-300">
          <Loader2 size={14} className="animate-spin text-violet-400" />
          {label}
        </span>
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-violet-400">
            {Math.round(progress.percent)}%{detail && ` • ${detail}`}
          </span>
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="text-zinc-400 hover:text-red-400 transition"
              aria-label={t("progress.cancel")}
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>
      <ProgressBar percent={progress.percent} />
    </GlassPanel>
  );
}
