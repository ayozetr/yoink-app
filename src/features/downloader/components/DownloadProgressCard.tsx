import {
  CheckCircle2,
  ExternalLink,
  FolderOpen,
  Loader2,
  X,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { ProgressBar } from "../../../components/ui/ProgressBar";
import { coverUrl, openInFileManager } from "../../../lib/api";
import type {
  DownloadCompletedEvent,
  DownloadProgressEvent,
} from "../../../types/download";

interface DownloadProgressCardProps {
  progress: DownloadProgressEvent | null;
  completed: DownloadCompletedEvent | null;
  onCancel?: () => void;
  onDismiss?: () => void;
}

/** Live download indicator fed by yt-dlp progress_hooks (over WS). */
export function DownloadProgressCard({
  progress,
  completed,
  onCancel,
  onDismiss,
}: DownloadProgressCardProps) {
  const { t } = useTranslation();
  const [coverFor, setCoverFor] = useState<string | null>(null);
  const [coverFailed, setCoverFailed] = useState(false);

  // The card persists across downloads (no remount), so reset the cover-failed
  // flag whenever a new file completes — otherwise one cover-less download would
  // stick the icon fallback for the rest of the session.
  if (completed && completed.filepath !== coverFor) {
    setCoverFor(completed.filepath);
    setCoverFailed(false);
  }

  if (completed) {
    return (
      <GlassPanel className="p-5">
        <div role="status" className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3 text-emerald-300">
            {!coverFailed && completed.filepath ? (
              <img
                src={coverUrl(completed.filepath)}
                alt=""
                className="h-11 w-11 shrink-0 rounded-lg object-cover"
                onError={() => setCoverFailed(true)}
              />
            ) : (
              <CheckCircle2 size={18} className="shrink-0" />
            )}
            <span className="min-w-0 text-sm">
              {t("progress.completed")}{" "}
              <span className="break-all font-medium text-emerald-200">
                {completed.filename}
              </span>
            </span>
          </div>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="shrink-0 text-zinc-400 transition hover:text-white"
              aria-label={t("progress.dismiss")}
            >
              <X size={16} />
            </button>
          )}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void openInFileManager(completed.filepath, true)}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-surface px-3 py-1.5 text-sm text-zinc-200 transition hover:border-white/20 hover:text-white"
          >
            <ExternalLink size={15} />
            {t("progress.openFile")}
          </button>
          <button
            type="button"
            onClick={() => void openInFileManager(completed.filepath)}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-surface px-3 py-1.5 text-sm text-zinc-200 transition hover:border-white/20 hover:text-white"
          >
            <FolderOpen size={15} />
            {t("progress.openFolder")}
          </button>
        </div>
      </GlassPanel>
    );
  }

  if (!progress) return null;

  const isProcessing = progress.status === "processing";
  // Before yt-dlp reports the first byte (extraction / format resolution / an
  // ffmpeg seek to the trim point), percent sits at 0 with no speed. Show
  // "Preparing…" so the bar doesn't look frozen at 0%.
  const isPreparing = !isProcessing && progress.percent === 0 && !progress.speed;
  const label = isProcessing
    ? t("progress.processing")
    : isPreparing
      ? t("progress.preparing")
      : t("progress.downloading");
  const detail =
    isProcessing || isPreparing
      ? isProcessing
        ? t("progress.merging")
        : ""
      : [progress.speed, progress.eta && `${t("progress.eta")} ${progress.eta}`]
          .filter(Boolean)
          .join(" • ");

  return (
    <GlassPanel className="p-5">
      <div className="flex items-center justify-between mb-3">
        <span
          aria-live="polite"
          className="flex items-center gap-2 text-sm text-zinc-300"
        >
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
