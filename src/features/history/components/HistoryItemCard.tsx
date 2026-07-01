import {
  AlertCircle,
  CheckCircle2,
  FolderOpen,
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

/** One row in the download history list. */
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

  // The flexible lead ("1080p · 45 MB" / "Failed") may truncate if space is
  // tight; the time (`when`) is rendered separately and pinned (shrink-0) so it's
  // always shown in full — a long relative time ("hace 3 horas") no longer gets
  // cut off the end.
  const metaLead = isCompleted
    ? [item.quality, size].filter(Boolean).join(" · ")
    : t("history.error");

  return (
    <div className="group rounded-2xl border border-white/10 bg-surface/70 hover:bg-surface-hover transition p-3">
      <div className="relative flex items-center gap-3">
        {/* Cover art (tagged audio) or a kind icon over a gradient, with the
            output format as a small chip in the corner — so it stays visible
            without taking width from the "quality · size · time" line. */}
        <div className="relative w-12 h-12 rounded-lg bg-gradient-to-br from-violet-500/40 to-blue-500/40 flex items-center justify-center shrink-0 overflow-hidden">
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
          {fmt && (
            <span className="absolute bottom-0 right-0 rounded-tl-md bg-black/75 px-1 py-px text-[9px] font-semibold leading-tight tracking-wide text-white">
              {fmt}
            </span>
          )}
        </div>

        {/* Title + meta fade fully out on hover so only the cover + action pill
            remain (the info reads when not hovering). A fade, not a CSS blur —
            blur ghosts in the packaged WebKitGTK build over the scrollable list.
            The cover is a sibling, so it stays sharp. */}
        <div className="flex-1 min-w-0 transition-opacity duration-150 sm:group-hover:opacity-0">
          <p className="text-sm font-medium truncate">{item.title}</p>

          {/* Status icon + "format · quality · size" (truncates if tight) + the
              time, pinned so it always shows in full. */}
          <div className="mt-1.5 flex items-center gap-1.5 text-xs min-w-0">
            {isCompleted ? (
              <CheckCircle2 size={13} className="shrink-0 text-emerald-400" />
            ) : (
              <AlertCircle size={13} className="shrink-0 text-red-400" />
            )}
            {metaLead && <span className="truncate text-zinc-400">{metaLead}</span>}
            {when && (
              <span className="shrink-0 text-zinc-400">
                {metaLead ? "· " : ""}
                {when}
              </span>
            )}
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

        {/* Actions in a row so their count (audio has an extra "re-tag") doesn't
            change the card's height. On ≥sm they're absolutely positioned and
            revealed on hover, so they reserve no width — the title/meta (format ·
            quality · size · time) keeps the full row and isn't truncated. On
            touch/narrow screens (no hover) they stay in flow, always visible. */}
        {isCompleted && (
          <div className="flex items-center gap-2 shrink-0 opacity-100 transition group-hover:opacity-100 focus-within:opacity-100 sm:absolute sm:left-[calc(50%_+_1.875rem)] sm:top-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-xl sm:bg-surface-hover sm:px-2 sm:py-1.5 sm:opacity-0 sm:shadow-md sm:shadow-black/20">
            {item.url && (
              <button
                type="button"
                onClick={() => onReanalyze?.(item)}
                className="text-zinc-400 hover:text-white transition"
                aria-label={t("history.reanalyze")}
                title={t("history.reanalyze")}
              >
                <RotateCcw size={16} />
              </button>
            )}
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
