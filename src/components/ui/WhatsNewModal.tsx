import { useEffect, useState } from "react";
import { Loader2, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "./GlassPanel";
import { Markdown } from "./Markdown";
import { fetchWhatsNew } from "../../lib/api";
import type { ReleaseNotes } from "../../types/download";

/**
 * "What's new" popup shown once after an update (and re-openable from Settings).
 * Fetches the release notes since `since` (the version last run) — cumulative,
 * so skipping releases still shows every version's notes, newest first — and
 * renders them; if none can be loaded it says so rather than showing nothing.
 */
export function WhatsNewModal({
  since,
  onClose,
}: {
  since: string | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<ReleaseNotes[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetchWhatsNew(since, controller.signal)
      .then((r) => setEntries(r.entries))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [since]);

  // Header shows the newest version; each entry is labelled when there's more
  // than one (a multi-version catch-up).
  const version = entries[0]?.version ?? "";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <GlassPanel className="flex max-h-[85vh] flex-col overflow-hidden p-0 !bg-[#16181f]">
          <div className="flex items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
            <span className="flex items-center gap-2 text-lg font-semibold">
              <Sparkles size={18} className="text-violet-400" />
              {t("whatsNew.title", { version })}
            </span>
            <button
              type="button"
              onClick={onClose}
              aria-label={t("whatsNew.close")}
              className="text-zinc-400 transition hover:text-white"
            >
              <X size={18} />
            </button>
          </div>

          <div className="overflow-y-auto px-5 py-4">
            {loading ? (
              <p className="flex items-center gap-2 text-sm text-zinc-400">
                <Loader2 size={15} className="animate-spin" />
                {t("whatsNew.loading")}
              </p>
            ) : entries.length ? (
              <div className="space-y-6">
                {entries.map((entry) => (
                  <section key={entry.version}>
                    {entries.length > 1 && (
                      <h3 className="mb-2 text-sm font-semibold text-violet-300">
                        {entry.version}
                      </h3>
                    )}
                    <Markdown source={entry.notes ?? ""} />
                  </section>
                ))}
              </div>
            ) : (
              <p className="text-sm text-zinc-400">{t("whatsNew.unavailable")}</p>
            )}
          </div>

          <div className="border-t border-white/10 px-5 py-3 text-right">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-violet-500"
            >
              {t("whatsNew.gotIt")}
            </button>
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}
