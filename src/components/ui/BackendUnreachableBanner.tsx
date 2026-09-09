import { Loader2, PlugZap, RotateCw } from "lucide-react";
import { useTranslation } from "react-i18next";

interface BackendUnreachableBannerProps {
  /** Relaunch the app (desktop only) — helps when the bundled backend failed to
   * spawn. Omitted in the browser, where there's nothing to restart. */
  onRestart?: () => void;
}

/** Shown when the app has dropped the splash but still can't reach its backend
 * after retrying (a bundled backend slow to start, or one that failed to spawn).
 * It stays up — and keeps retrying in the background — until the backend answers,
 * so the user knows why the app is empty instead of staring at a blank screen. */
export function BackendUnreachableBanner({
  onRestart,
}: BackendUnreachableBannerProps) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      className="fixed bottom-4 left-4 z-40 w-[22rem] max-w-[calc(100vw-2rem)] rounded-2xl border border-amber-500/30 bg-[#1c1926] p-4 shadow-2xl"
    >
      <div className="flex gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/25">
          <PlugZap size={17} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 text-sm font-semibold text-white">
            {t("backend.unreachableTitle")}
            <Loader2 size={13} className="animate-spin text-amber-300" />
          </p>
          <p className="mt-1 text-xs leading-relaxed text-zinc-400">
            {t("backend.unreachable")}
          </p>
          {onRestart && (
            <button
              type="button"
              onClick={onRestart}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-[#1c1926] transition hover:bg-amber-400"
            >
              <RotateCw size={13} />
              {t("update.restart")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
