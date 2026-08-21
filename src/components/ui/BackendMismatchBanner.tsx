import { AlertTriangle, X } from "lucide-react";
import { useTranslation } from "react-i18next";

interface BackendMismatchBannerProps {
  /** Version the running backend reports. */
  backendVersion: string;
  /** Version this frontend was built as (`__APP_VERSION__`). */
  appVersion: string;
  onDismiss: () => void;
}

/** A stale-backend warning: after a self-update the app can end up talking to a
 * leftover backend process from the previous version (old yt-dlp, old fixes).
 * Shown when the backend's reported version differs from the app's — restarting
 * Yoink kills the orphan and starts the bundled backend for this version. */
export function BackendMismatchBanner({
  backendVersion,
  appVersion,
  onDismiss,
}: BackendMismatchBannerProps) {
  const { t } = useTranslation();
  return (
    <div className="fixed bottom-4 left-4 z-40 flex max-w-md items-start gap-3 rounded-xl border border-amber-500/40 bg-[#1c1926] px-4 py-2.5 text-sm shadow-2xl">
      <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-300" />
      <span className="flex-1">
        {t("update.backendMismatch", { backend: backendVersion, app: appVersion })}
      </span>
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
