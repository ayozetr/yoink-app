import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "./GlassPanel";

/**
 * Blocking "downloading the update…" popup — a spinner plus a progress bar that
 * tracks the real download (`progress` is 0–1 of bytes fetched). The bar just
 * fills from empty (the spinner already signals activity while connecting, so no
 * indeterminate sweep that would then jump to the real fill). After the bytes land
 * it sits full while the installer runs, and the app relaunches on success (on
 * failure the caller dismisses it).
 */
export function UpdatingModal({ progress }: { progress: number }) {
  const { t } = useTranslation();
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4">
      <GlassPanel boxed className="flex w-full max-w-sm flex-col items-center gap-4 p-6 !bg-surface">
        <Loader2 size={30} className="animate-spin text-accent-soft" />
        <p className="text-sm font-medium text-fg">
          {t("update.downloading")}
        </p>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-200"
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </div>
        <p className="text-xs text-fg-dim">{t("update.dontClose")}</p>
      </GlassPanel>
    </div>
  );
}
