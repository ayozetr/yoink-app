import {
  AlertCircle,
  CheckCircle2,
  FolderOpen,
  Music4,
  Video,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { HistoryEntry } from "../../../types/download";

interface HistoryItemCardProps {
  item: HistoryEntry;
  onOpenFolder?: (item: HistoryEntry) => void;
}

/** The output format badge, derived from the file extension (e.g. "MP4"). */
function formatLabel(filename: string | null): string | null {
  if (!filename) return null;
  const ext = filename.split(".").pop();
  return ext && ext.length <= 4 ? ext.toUpperCase() : null;
}

/** Human-readable file size (B/KB/MB/GB). */
function formatBytes(bytes: number | null): string | null {
  if (bytes == null) return null;
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/** Localized relative time ("5 minutes ago") from an ISO timestamp. */
function relativeTime(iso: string, lang: string): string | null {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const diffSec = Math.round((then - Date.now()) / 1000); // negative = past
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
  const abs = Math.abs(diffSec);
  if (abs < 60) return rtf.format(diffSec, "second");
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
  if (abs < 2592000) return rtf.format(Math.round(diffSec / 86400), "day");
  if (abs < 31536000) return rtf.format(Math.round(diffSec / 2592000), "month");
  return rtf.format(Math.round(diffSec / 31536000), "year");
}

/** One row in the download history list. */
export function HistoryItemCard({ item, onOpenFolder }: HistoryItemCardProps) {
  const { t, i18n } = useTranslation();
  const isCompleted = item.status === "completed";
  const fmt = isCompleted ? formatLabel(item.filename) : null;
  const size = isCompleted ? formatBytes(item.filesize) : null;
  const when = relativeTime(item.created_at, i18n.language);

  return (
    <div className="group rounded-2xl border border-white/10 bg-surface/70 hover:bg-surface-hover transition p-3">
      <div className="flex gap-3">
        {/* Small thumb */}
        <div className="w-16 h-12 rounded-lg bg-gradient-to-br from-violet-500/40 to-blue-500/40 flex items-center justify-center shrink-0">
          {item.kind === "audio" ? <Music4 size={18} /> : <Video size={18} />}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{item.title}</p>

          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-2 text-xs">
            {isCompleted ? (
              <span className="flex items-center gap-1 text-emerald-400">
                <CheckCircle2 size={14} /> {t("history.completed")}
              </span>
            ) : (
              <span className="flex items-center gap-1 text-red-400">
                <AlertCircle size={14} /> {t("history.error")}
              </span>
            )}
            {fmt && (
              <span className="rounded bg-white/10 px-1.5 py-0.5 font-medium text-zinc-300">
                {fmt}
              </span>
            )}
            {size && <span className="text-zinc-500">{size}</span>}
            {when && <span className="text-zinc-500">{when}</span>}
          </div>
        </div>

        {isCompleted && (
          <button
            type="button"
            onClick={() => onOpenFolder?.(item)}
            className="opacity-60 hover:opacity-100 transition self-start"
            aria-label={t("history.openFolder")}
          >
            <FolderOpen size={18} className="text-zinc-400" />
          </button>
        )}
      </div>
    </div>
  );
}
