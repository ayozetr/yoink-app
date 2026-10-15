import { memo } from "react";
import { Home, ListVideo, History, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";

/** The app's top-level views. */
export type TabId = "home" | "queue" | "history" | "settings";

const TABS: { id: TabId; icon: typeof Home; labelKey: string }[] = [
  { id: "home", icon: Home, labelKey: "tabs.home" },
  { id: "queue", icon: ListVideo, labelKey: "tabs.queue" },
  { id: "history", icon: History, labelKey: "tabs.history" },
  { id: "settings", icon: Settings, labelKey: "tabs.settings" },
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

  return (
    <nav
      className="flex items-center gap-1"
      role="tablist"
      aria-label={t("tabs.home")}
    >
      {TABS.map(({ id, icon: Icon, labelKey }) => {
        const isActive = active === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={isActive}
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
