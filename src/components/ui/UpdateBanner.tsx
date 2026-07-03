import { ArrowUpCircle, X } from "lucide-react";
import { useTranslation } from "react-i18next";

interface UpdateBannerProps {
  version: string;
  /** Open Settings (its update section installs / links to the release). */
  onAction: () => void;
  onDismiss: () => void;
}

/** A dismissible "a newer version is available" toast, floated at the bottom-left
 * when the opt-in launch check finds an update. */
export function UpdateBanner({ version, onAction, onDismiss }: UpdateBannerProps) {
  const { t } = useTranslation();
  return (
    <div className="fixed bottom-4 left-4 z-40 flex max-w-md items-center gap-3 rounded-xl border border-violet-500/40 bg-[#1c1926] px-4 py-2.5 text-sm shadow-2xl">
      <ArrowUpCircle size={18} className="shrink-0 text-violet-300" />
      <span className="flex-1">{t("update.available", { version })}</span>
      <button
        type="button"
        onClick={onAction}
        className="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-violet-500"
      >
        {t("update.action")}
      </button>
      <button
        type="button"
        onClick={onDismiss}
        aria-label={t("update.dismiss")}
        className="shrink-0 text-zinc-400 transition hover:text-white"
      >
        <X size={16} />
      </button>
    </div>
  );
}
