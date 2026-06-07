import { useState } from "react";
import { Download, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SupportedSitesModal } from "./SupportedSitesModal";

interface DownloaderHeaderProps {
  activeDownloads: number;
  onOpenSettings?: () => void;
}

/** Page title plus the "active downloads" status pill and settings button. */
export function DownloaderHeader({
  activeDownloads,
  onOpenSettings,
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
        <div className="flex items-center gap-2 px-4 py-2 rounded-xl border border-white/10 bg-white/[0.06]">
          <Download className="size-4 text-violet-400" />
          <span className="text-sm text-zinc-300">
            {t("header.active", { count: activeDownloads })}
          </span>
        </div>
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
