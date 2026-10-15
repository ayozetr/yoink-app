import {
  AlertCircle,
  CheckCircle2,
  FolderOpen,
  Image as ImageIcon,
  Music4,
  Play,
  RotateCcw,
  Tag,
  Video,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CopyButton } from "../../../components/ui/CopyButton";
import { coverUrl } from "../../../lib/api";
import type { HistoryEntry } from "../../../types/download";

interface HistoryItemCardProps {
  item: HistoryEntry;
  onOpenFolder?: (item: HistoryEntry) => void;
  onOpenFile?: (item: HistoryEntry) => void;
  onRetag?: (item: HistoryEntry) => void;
  onReanalyze?: (item: HistoryEntry) => void;
}

/** The output format, from the file extension (e.g. "MP4") — shown on the cover. */
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
  try {
    const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
    const abs = Math.abs(diffSec);
    if (abs < 60) return rtf.format(diffSec, "second");
    if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
    if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
    if (abs < 2592000) return rtf.format(Math.round(diffSec / 86400), "day");
    if (abs < 31536000) return rtf.format(Math.round(diffSec / 2592000), "month");
    return rtf.format(Math.round(diffSec / 31536000), "year");
  } catch {
    return null; // malformed locale tag → just omit the relative time
  }
}

/** One hairline row in the download history list (v4 editorial design). */
export function HistoryItemCard({
  item,
  onOpenFolder,
  onOpenFile,
  onRetag,
  onReanalyze,
}: HistoryItemCardProps) {
  const { t, i18n } = useTranslation();
  const [coverFailed, setCoverFailed] = useState(false);
  const [coverNonce, setCoverNonce] = useState(item.mtime);
  // Re-check the cover only when THIS file changed (its mtime bumped, e.g. after
  // tagging), not on every global history refresh.
  if (item.mtime !== coverNonce) {
    setCoverNonce(item.mtime);
    setCoverFailed(false);
  }
  const isCompleted = item.status === "completed";
  const fmt = isCompleted ? formatLabel(item.filename) : null;
  const size = isCompleted ? formatBytes(item.filesize) : null;
  const when = relativeTime(item.created_at, i18n.language);

  // Show the embedded cover for tagged audio; fall back to the icon if none.
  const showCover =
    isCompleted && item.kind === "audio" && !!item.filepath && !coverFailed;

  const metaLead = isCompleted
    ? [item.quality, size].filter(Boolean).join(" · ")
    : t("history.error");

  const actionBtn = "grid size-7 place-items-center rounded-lg text-fg-dim transition hover:bg-surface-hover hover:text-fg";

  return (
    <div className="group flex items-center gap-3.5 rounded-xl px-2.5 py-2.5 transition hover:bg-surface">
      {/* Cover art (tagged audio) or a kind icon, with the output format chip. */}
      <div className="relative flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-violet-500/40 to-blue-500/40">
        {showCover && item.filepath ? (
          <img
            src={coverUrl(item.filepath, item.mtime ?? undefined)}
            alt=""
            className="h-full w-full object-cover"
            onError={() => setCoverFailed(true)}
          />
        ) : item.kind === "audio" ? (
          <Music4 size={18} />
        ) : item.kind === "image" ? (
          <ImageIcon size={18} />
        ) : (
          <Video size={18} />
        )}
        {fmt && (
          <span className="absolute bottom-0 right-0 rounded-tl-md bg-black/75 px-1 py-px text-[9px] font-semibold leading-tight tracking-wide text-white">
            {fmt}
          </span>
        )}
      </div>

      {/* Title + meta */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm">{item.title}</p>
        <div className="mt-0.5 flex items-center gap-1.5 text-xs text-fg-dim">
          {isCompleted ? (
            <CheckCircle2 size={13} className="shrink-0 text-emerald-400" />
          ) : (
            <AlertCircle size={13} className="shrink-0 text-red-400" />
          )}
          {metaLead && <span className="truncate">{metaLead}</span>}
        </div>

        {!isCompleted && item.error_message && (
          <div className="mt-1 flex items-start gap-1">
            <p
              className="line-clamp-2 min-w-0 flex-1 text-xs text-red-300/80"
              title={item.error_message}
            >
              {item.error_message}
            </p>
            <CopyButton text={item.error_message} label={t("common.copyError")} />
          </div>
        )}
      </div>

      {/* Right: the time, swapped for the action icons on hover. */}
      <div className="shrink-0">
        {when && (
          <span className="text-xs text-fg-faint group-hover:hidden">{when}</span>
        )}
        {isCompleted && (
          <div className="hidden items-center gap-0.5 group-hover:flex has-[:focus-visible]:flex">
            {item.url && (
              <button
                type="button"
                onClick={() => onReanalyze?.(item)}
                className={actionBtn}
                aria-label={t("history.reanalyze")}
                title={t("history.reanalyze")}
              >
                <RotateCcw size={15} />
              </button>
            )}
            <button
              type="button"
              onClick={() => onOpenFolder?.(item)}
              className={actionBtn}
              aria-label={t("history.openFolder")}
              title={t("history.openFolder")}
            >
              <FolderOpen size={15} />
            </button>
            <button
              type="button"
              onClick={() => onOpenFile?.(item)}
              className={actionBtn}
              aria-label={t("history.openFile")}
              title={t("history.openFile")}
            >
              <Play size={15} />
            </button>
            {item.kind === "audio" && (
              <button
                type="button"
                onClick={() => onRetag?.(item)}
                className={actionBtn}
                aria-label={t("history.retag")}
                title={t("history.retag")}
              >
                <Tag size={15} />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
