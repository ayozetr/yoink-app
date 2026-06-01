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

/** One row in the download history list. */
export function HistoryItemCard({ item, onOpenFolder }: HistoryItemCardProps) {
  const { t } = useTranslation();
  const isCompleted = item.status === "completed";

  return (
    <div className="group rounded-2xl border border-white/10 bg-surface/70 hover:bg-surface-hover transition p-3">
      <div className="flex gap-3">
        {/* Small thumb */}
        <div className="w-16 h-12 rounded-lg bg-gradient-to-br from-violet-500/40 to-blue-500/40 flex items-center justify-center shrink-0">
          {item.kind === "audio" ? <Music4 size={18} /> : <Video size={18} />}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{item.title}</p>

          <div className="flex items-center gap-2 mt-2">
            {isCompleted ? (
              <>
                <CheckCircle2 size={14} className="text-emerald-400" />
                <span className="text-xs text-emerald-400">
                  {t("history.completed")}
                </span>
              </>
            ) : (
              <>
                <AlertCircle size={14} className="text-red-400" />
                <span className="text-xs text-red-400">
                  {t("history.error")}
                </span>
              </>
            )}
          </div>
        </div>

        {isCompleted && (
          <button
            type="button"
            onClick={() => onOpenFolder?.(item)}
            className="opacity-60 hover:opacity-100 transition"
            aria-label={t("history.openFolder")}
          >
            <FolderOpen size={18} className="text-zinc-400" />
          </button>
        )}
      </div>
    </div>
  );
}
