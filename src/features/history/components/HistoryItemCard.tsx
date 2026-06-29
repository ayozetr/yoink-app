import {
  AlertCircle,
  CheckCircle2,
  FolderOpen,
  Music4,
  Play,
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

/** One row in the download history list. */
export function HistoryItemCard({
  item,
  onOpenFolder,
  onOpenFile,
  onRetag,
}: HistoryItemCardProps) {
  const { t, i18n } = useTranslation();
  const [coverFailed, setCoverFailed] = useState(false);
  const [coverNonce, setCoverNonce] = useState(item.mtime);
  // Re-check the cover only when THIS file changed (its mtime bumped, e.g. after
  // tagging), not on every global history refresh — so the other rows' covers
  // stay cached instead of all refetching (and re-404ing the cover-less ones).
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

  // Completed: "1080p · 45 MB · 5 min ago". Failed: "Failed · 5 min ago".
  const meta = isCompleted
    ? [item.quality, size, when].filter(Boolean).join(" · ")
    : [t("history.error"), when].filter(Boolean).join(" · ");

  return (
    <div className="group rounded-2xl border border-white/10 bg-surface/70 hover:bg-surface-hover transition p-3">
      <div className="flex items-center gap-3">
        {/* Cover art (tagged audio) or a kind icon over a gradient */}
        <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-violet-500/40 to-blue-500/40 flex items-center justify-center shrink-0 overflow-hidden">
          {showCover && item.filepath ? (
            <img
              src={coverUrl(item.filepath, item.mtime ?? undefined)}
              alt=""
              className="h-full w-full object-cover"
              onError={() => setCoverFailed(true)}
            />
          ) : item.kind === "audio" ? (
            <Music4 size={18} />
          ) : (
            <Video size={18} />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{item.title}</p>

          {/* Status icon + format badge + size · time (truncates if tight) */}
          <div className="mt-1.5 flex items-center gap-1.5 text-xs min-w-0">
            {isCompleted ? (
              <CheckCircle2 size={13} className="shrink-0 text-emerald-400" />
            ) : (
              <AlertCircle size={13} className="shrink-0 text-red-400" />
            )}
            {isCompleted && fmt && (
              <span className="shrink-0 rounded bg-white/10 px-1.5 py-0.5 font-medium text-zinc-300">
                {fmt}
              </span>
            )}
            <span className="truncate text-zinc-400">{meta}</span>
          </div>

          {!isCompleted && item.error_message && (
            <div className="mt-1 flex items-start gap-1">
              <p
                className="line-clamp-2 min-w-0 flex-1 text-xs text-red-300/80"
                title={item.error_message}
              >
                {item.error_message}
              </p>
              <CopyButton
                text={item.error_message}
                label={t("common.copyError")}
              />
            </div>
          )}
        </div>

        {/* Open folder + open file (play), revealed on hover (always shown on
            touch / narrow screens where there's no hover). */}
        {isCompleted && (
          <div className="flex flex-col justify-center gap-1.5 shrink-0 opacity-100 transition group-hover:opacity-100 focus-within:opacity-100 sm:opacity-0">
            <button
              type="button"
              onClick={() => onOpenFolder?.(item)}
              className="text-zinc-400 hover:text-white transition"
              aria-label={t("history.openFolder")}
              title={t("history.openFolder")}
            >
              <FolderOpen size={16} />
            </button>
            <button
              type="button"
              onClick={() => onOpenFile?.(item)}
              className="text-zinc-400 hover:text-white transition"
              aria-label={t("history.openFile")}
              title={t("history.openFile")}
            >
              <Play size={16} />
            </button>
            {item.kind === "audio" && (
              <button
                type="button"
                onClick={() => onRetag?.(item)}
                className="text-zinc-400 hover:text-white transition"
                aria-label={t("history.retag")}
                title={t("history.retag")}
              >
                <Tag size={16} />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
