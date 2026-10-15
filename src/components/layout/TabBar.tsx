// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

import { memo, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Home, ListVideo, History, Settings, ScrollText } from "lucide-react";
import { useTranslation } from "react-i18next";

/** The app's top-level views. */
export type TabId = "home" | "queue" | "history" | "settings" | "logs";

const TABS: { id: TabId; icon: typeof Home; labelKey: string }[] = [
  { id: "home", icon: Home, labelKey: "tabs.home" },
  { id: "queue", icon: ListVideo, labelKey: "tabs.queue" },
  { id: "history", icon: History, labelKey: "tabs.history" },
  { id: "settings", icon: Settings, labelKey: "tabs.settings" },
  { id: "logs", icon: ScrollText, labelKey: "tabs.logs" },
];

interface TabBarProps {
  active: TabId;
  onChange: (tab: TabId) => void;
  /** Unfinished queue items — badged on the Queue tab. */
  queueCount?: number;
}

/**
 * Primary navigation: the four modular views (Flat Minimal). The active tab is a
 * solid violet pill; the rest are quiet until hovered.
 */
export const TabBar = memo(function TabBar({
  active,
  onChange,
  queueCount = 0,
}: TabBarProps) {
  const { t } = useTranslation();

  // Roving-tabindex arrow-key navigation (WAI-ARIA tabs): move + activate on
  // ◀/▶/Home/End, then focus the newly-active tab after it re-renders.
  const onKeyDown = (event: ReactKeyboardEvent) => {
    const idx = TABS.findIndex((tab) => tab.id === active);
    let next: number;
    if (event.key === "ArrowRight") next = (idx + 1) % TABS.length;
    else if (event.key === "ArrowLeft") next = (idx - 1 + TABS.length) % TABS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = TABS.length - 1;
    else return;
    event.preventDefault();
    const nextId = TABS[next].id;
    onChange(nextId);
    requestAnimationFrame(() =>
      document.getElementById(`yoink-tab-${nextId}`)?.focus(),
    );
  };

  return (
    <nav
      className="flex items-center gap-1"
      role="tablist"
      aria-label={t("tabs.navigation")}
      onKeyDown={onKeyDown}
    >
      {TABS.map(({ id, icon: Icon, labelKey }) => {
        const isActive = active === id;
        return (
          <button
            key={id}
            id={`yoink-tab-${id}`}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={`yoink-panel-${id}`}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onChange(id)}
            className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition ${
              isActive
                ? "bg-accent text-white"
                : "text-fg-dim hover:bg-surface-hover hover:text-fg"
            }`}
          >
            <Icon size={16} className="shrink-0" />
            <span>{t(labelKey)}</span>
            {id === "queue" && queueCount > 0 && (
              <span className={isActive ? "opacity-80" : "text-fg-faint"}>
                · {queueCount}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
});
