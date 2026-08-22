import { AlertTriangle, RotateCw, X } from "lucide-react";
import { useTranslation } from "react-i18next";

interface BackendMismatchBannerProps {
  /** Version the running backend reports. */
  backendVersion: string;
  /** Version this frontend was built as (`__APP_VERSION__`). */
  appVersion: string;
  /** Relaunch the app (kills the stale backend, starts this version's). */
  onRestart: () => void;
  onDismiss: () => void;
}

/** A stale-backend warning: after a self-update the app can end up talking to a
 * leftover backend process from the previous version (old yt-dlp, old fixes).
 * Shown when the backend's reported version differs from the app's — restarting
 * Yoink kills the orphan and starts the bundled backend for this version. */
export function BackendMismatchBanner({
  backendVersion,
  appVersion,
  onRestart,
  onDismiss,
}: BackendMismatchBannerProps) {
  const { t } = useTranslation();
  return (
    <div className="fixed bottom-4 left-4 z-40 w-[22rem] max-w-[calc(100vw-2rem)] rounded-2xl border border-amber-500/30 bg-[#1c1926] p-4 shadow-2xl">
      <button
        type="button"
        onClick={onDismiss}
        aria-label={t("update.dismiss")}
        className="absolute right-3 top-3 text-zinc-500 transition hover:text-white"
      >
        <X size={15} />
      </button>
      <div className="flex gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/25">
          <AlertTriangle size={17} />
        </div>
        <div className="min-w-0 flex-1 pr-4">
          <p className="text-sm font-semibold text-white">
            {t("update.backendMismatchTitle")}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-zinc-400">
            {t("update.backendMismatch", {
              backend: backendVersion,
              app: appVersion,
            })}
          </p>
          <button
            type="button"
            onClick={onRestart}
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-[#1c1926] transition hover:bg-amber-400"
          >
            <RotateCw size={13} />
            {t("update.restart")}
          </button>
        </div>
      </div>
    </div>
  );
}
