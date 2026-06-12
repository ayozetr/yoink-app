import { useState } from "react";
import { ListPlus, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SupportedSitesModal } from "./SupportedSitesModal";
import { SearchSourceToggle } from "./SearchSourceToggle";
import type { SearchSource } from "../../../lib/api";

interface DownloaderHeaderProps {
  /** Number of unfinished queue items, badged on the queue button. */
  queueCount: number;
  /** Whether the queue panel is open (toggles the button's label). */
  queueOpen?: boolean;
  onToggleQueue?: () => void;
  onOpenSettings?: () => void;
  /** Platform the URL-field typeahead searches (YouTube/SoundCloud). */
  searchSource: SearchSource;
  onSearchSourceChange: (source: SearchSource) => void;
}

/** Page title plus the search-source toggle, download-queue and settings buttons. */
export function DownloaderHeader({
  queueCount,
  queueOpen,
  onToggleQueue,
  onOpenSettings,
  searchSource,
  onSearchSourceChange,
}: DownloaderHeaderProps) {
  const { t } = useTranslation();
  const [showSites, setShowSites] = useState(false);

  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          {t("header.title")}
        </h1>
        <p className="text-sm text-zinc-400 mt-1">
          {t("header.subtitlePrefix")}
          <button
            type="button"
            onClick={() => setShowSites(true)}
            className="text-violet-400 underline-offset-2 transition hover:text-violet-300 hover:underline"
          >
            {t("header.subtitleSitesLink")}
          </button>
          {"."}
        </p>
      </div>

      {showSites && <SupportedSitesModal onClose={() => setShowSites(false)} />}

      <div className="flex items-center gap-3">
        <SearchSourceToggle
          value={searchSource}
          onChange={onSearchSourceChange}
        />
        <button
          type="button"
          onClick={onToggleQueue}
          className="flex items-center gap-2 px-4 py-2 rounded-xl border border-white/10 bg-white/[0.06] text-zinc-300 hover:text-white hover:bg-white/10 transition"
        >
          <ListPlus className="size-4 text-violet-400" />
          <span className="text-sm">
            {t(queueOpen ? "queue.close" : "queue.open")}
          </span>
          {queueCount > 0 && (
            <span className="ml-0.5 rounded-full bg-violet-500/30 px-2 py-0.5 text-xs font-semibold text-violet-200">
              {queueCount}
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={onOpenSettings}
          className="p-2.5 rounded-xl border border-white/10 bg-white/[0.06] text-zinc-300 hover:text-white hover:bg-white/10 transition"
          aria-label={t("header.settings")}
        >
          <Settings className="size-4" />
        </button>
      </div>
    </div>
  );
}
