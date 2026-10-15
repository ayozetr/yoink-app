// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { HistoryItemCard } from "./components/HistoryItemCard";
import type { DownloadStats, HistoryEntry } from "../../types/download";

interface HistorySidebarProps {
  items: HistoryEntry[];
  stats: DownloadStats;
  onOpenFolder?: (entry: HistoryEntry) => void;
  onOpenFile?: (entry: HistoryEntry) => void;
  onRetag?: (entry: HistoryEntry) => void;
  onReanalyze?: (entry: HistoryEntry) => void;
  onClear?: () => void;
}

type Bucket = "today" | "week" | "month" | "older";

/** Bucket an ISO timestamp into a relative date group. */
function bucketOf(iso: string): Bucket {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "older";
  const now = new Date();
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  const DAY = 86_400_000;
  if (then >= startOfToday) return "today";
  if (then >= startOfToday - 6 * DAY) return "week";
  if (then >= startOfToday - 29 * DAY) return "month";
  return "older";
}

const GROUPS: { key: Bucket; labelKey: string }[] = [
  { key: "today", labelKey: "history.groupToday" },
  { key: "week", labelKey: "history.groupWeek" },
  { key: "month", labelKey: "history.groupMonth" },
  { key: "older", labelKey: "history.groupOlder" },
];

/** Download history view (v4 editorial): Gloock stats header, a search field and
 *  hairline rows grouped by relative date. */
export function HistorySidebar({
  items,
  stats,
  onOpenFolder,
  onOpenFile,
  onRetag,
  onReanalyze,
  onClear,
}: HistorySidebarProps) {
  const { t } = useTranslation();
  // Clearing history is destructive — require a confirming second click.
  const [confirming, setConfirming] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    },
    [],
  );
  const handleClear = () => {
    if (confirming) {
      if (resetTimer.current) clearTimeout(resetTimer.current);
      setConfirming(false);
      onClear?.();
    } else {
      setConfirming(true);
      resetTimer.current = setTimeout(() => setConfirming(false), 3000);
    }
  };

  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q
      ? items.filter((i) => (i.title ?? "").toLowerCase().includes(q))
      : items;
  }, [items, query]);

  // Group the (newest-first) filtered items into date buckets.
  const grouped = useMemo(() => {
    const map: Record<Bucket, HistoryEntry[]> = {
      today: [],
      week: [],
      month: [],
      older: [],
    };
    for (const it of filtered) map[bucketOf(it.created_at)].push(it);
    return map;
  }, [filtered]);

  return (
    <div className="flex flex-col gap-5">
      {/* Header — editorial stats + clear. */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-fg-faint">
            {t("tabs.history")}
          </span>
          <div className="mt-2 flex gap-8">
            <div>
              <div className="font-display text-[26px] leading-none">
                {stats.total_downloads}
              </div>
              <div className="mt-1.5 text-[11px] uppercase tracking-[0.14em] text-fg-faint">
                {t("stats.downloads")}
              </div>
            </div>
            <div>
              <div className="font-display text-[26px] leading-none">
                {stats.transferred}
              </div>
              <div className="mt-1.5 text-[11px] uppercase tracking-[0.14em] text-fg-faint">
                {t("stats.transferred")}
              </div>
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={handleClear}
          disabled={items.length === 0}
          className={`flex items-center gap-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${
            confirming ? "text-red-400" : "text-fg-dim hover:text-red-400"
          }`}
        >
          <Trash2 size={15} />
          {confirming ? t("history.clearConfirm") : t("history.clear")}
        </button>
      </div>

      {/* Search */}
      {items.length > 0 && (
        <div className="flex h-11 items-center gap-2.5 rounded-xl border border-line/10 bg-surface px-3.5">
          <Search size={16} className="shrink-0 text-fg-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("history.search")}
            aria-label={t("history.search")}
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-fg-faint"
          />
        </div>
      )}

      {/* List */}
      {items.length === 0 ? (
        <p className="py-10 text-center text-sm text-fg-dim">
          {t("history.empty")}
        </p>
      ) : filtered.length === 0 ? (
        <p className="py-10 text-center text-sm text-fg-dim">
          {t("url.noResults")}
        </p>
      ) : (
        <div className="flex flex-col">
          {GROUPS.map(({ key, labelKey }) =>
            grouped[key].length > 0 ? (
              <div key={key} className="mt-4 first:mt-0">
                <div className="mb-1 px-2.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-fg-faint">
                  {t(labelKey)}
                </div>
                <div className="flex flex-col divide-y divide-line/[0.06]">
                  {grouped[key].map((item) => (
                    <HistoryItemCard
                      key={item.id}
                      item={item}
                      onOpenFolder={onOpenFolder}
                      onOpenFile={onOpenFile}
                      onRetag={onRetag}
                      onReanalyze={onReanalyze}
                    />
                  ))}
                </div>
              </div>
            ) : null,
          )}
        </div>
      )}
    </div>
  );
}
