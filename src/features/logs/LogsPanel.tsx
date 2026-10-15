// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, Download, RefreshCw } from "lucide-react";
import { fetchLogs } from "../../lib/api";
import { subscribeLogs } from "../../lib/logsPoll";
import { toast } from "../../lib/toast";
import type { LogsResponse } from "../../types/download";

interface LogsPanelProps {
  /** Only load + poll while the Logs tab is the active one. */
  active: boolean;
}

const BTN =
  "flex h-9 items-center gap-1.5 rounded-lg border border-line/10 bg-surface px-3 text-sm text-fg transition hover:border-line/20 disabled:cursor-not-allowed disabled:opacity-40";

/**
 * Registro (Logs) view: the tail of the app's rotating log (`~/.yoink/logs/
 * yoink.log`), refreshed live while the tab is open, with copy-to-clipboard and
 * export-to-file. Lines are lightly colour-coded by level.
 */
export function LogsPanel({ active }: LogsPanelProps) {
  const { t } = useTranslation();
  const [data, setData] = useState<LogsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Only auto-scroll to the newest line when the user is already at the bottom,
  // so reading older entries isn't interrupted by a refresh.
  const atBottomRef = useRef(true);

  // Poll while the tab is active. The fetch + delivery lives in the store helper;
  // the effect just subscribes and hands it `setData` (no state set in the effect).
  useEffect(() => {
    if (!active) return;
    return subscribeLogs(setData);
  }, [active]);

  const content = data?.content ?? "";

  // Follow the tail when pinned to the bottom.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && atBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [content]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    atBottomRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 24;
  };

  const lines = useMemo(() => {
    return content.split("\n").map((line) => {
      const level = /\s(ERROR|CRITICAL|WARNING|INFO|DEBUG)\s/.exec(line)?.[1];
      const cls =
        level === "ERROR" || level === "CRITICAL"
          ? "text-red-300"
          : level === "WARNING"
            ? "text-amber-300"
            : level === "DEBUG"
              ? "text-fg-faint"
              : "text-fg-dim";
      return { line, cls };
    });
  }, [content]);

  // Manual refresh (an event handler — state updates here are fine).
  const refresh = () => {
    setLoading(true);
    fetchLogs(2000)
      .then(setData)
      .catch(() => undefined)
      .finally(() => setLoading(false));
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
      toast.success(t("logs.copied"));
    } catch {
      // Clipboard blocked (rare) — the text stays selectable in the view.
    }
  };

  const exportLog = () => {
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    a.href = url;
    a.download = `yoink-${stamp}.log`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast.success(t("logs.exported"));
  };

  return (
    <div className="flex h-full flex-col gap-4 pb-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-2xl font-normal leading-tight">
            {t("tabs.logs")}
          </h2>
          {data?.path && (
            <p
              className="mt-0.5 truncate font-mono text-[11px] text-fg-faint"
              title={data.path}
            >
              {t("logs.path")}: {data.path}
              {data.lines > 0 ? ` · ${data.lines}` : ""}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={refresh}
            className={BTN}
            aria-label={t("logs.refresh")}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            {t("logs.refresh")}
          </button>
          <button
            type="button"
            onClick={copy}
            disabled={!content}
            className={BTN}
          >
            {copied ? (
              <Check size={14} className="text-emerald-400" />
            ) : (
              <Copy size={14} />
            )}
            {t("logs.copy")}
          </button>
          <button
            type="button"
            onClick={exportLog}
            disabled={!content}
            className={BTN}
          >
            <Download size={14} />
            {t("logs.export")}
          </button>
        </div>
      </div>

      {content ? (
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="min-h-0 flex-1 overflow-auto rounded-xl border border-line/10 bg-surface p-4 font-mono text-xs leading-relaxed"
        >
          {lines.map((l, i) => (
            <div key={i} className={`whitespace-pre-wrap break-words ${l.cls}`}>
              {l.line || " "}
            </div>
          ))}
        </div>
      ) : (
        <p className="py-16 text-center text-sm text-fg-faint">
          {t("logs.empty")}
        </p>
      )}
    </div>
  );
}
