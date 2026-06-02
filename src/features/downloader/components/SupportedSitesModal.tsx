import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Globe, X } from "lucide-react";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { openExternal } from "../../../lib/openExternal";

interface SupportedSitesModalProps {
  onClose: () => void;
}

interface SupportedSite {
  /** Brand name — not translated. */
  name: string;
  /** Page opened when the row is clicked. */
  url: string;
  /** Simple Icons slug for the CDN logo. */
  slug: string;
}

/** Manually verified platforms. Typed array so it's easy to extend later. */
const SUPPORTED_SITES: readonly SupportedSite[] = [
  { name: "YouTube", url: "https://youtube.com", slug: "youtube" },
  { name: "YouTube Music", url: "https://music.youtube.com", slug: "ytmusic" },
  { name: "Vimeo", url: "https://vimeo.com", slug: "vimeo" },
  { name: "Dailymotion", url: "https://dailymotion.com", slug: "dailymotion" },
  { name: "Instagram", url: "https://instagram.com", slug: "instagram" },
  { name: "TikTok", url: "https://tiktok.com", slug: "tiktok" },
  { name: "X (Twitter)", url: "https://x.com", slug: "x" },
];

/** Modal listing the manually-verified sites (logo + name), each clickable. */
export function SupportedSitesModal({ onClose }: SupportedSitesModalProps) {
  const { t } = useTranslation();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      role="presentation"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
    >
      <GlassPanel
        role="dialog"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-lg max-h-[calc(100vh-2rem)] overflow-y-auto p-6 !bg-[#16181f]"
      >
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Globe size={18} className="text-violet-400" />
            {t("sites.title")}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-400 hover:text-white transition"
            aria-label={t("sites.close")}
          >
            <X size={18} />
          </button>
        </div>

        <p className="text-sm text-zinc-400 mb-5">{t("sites.intro")}</p>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {SUPPORTED_SITES.map((site) => (
            <button
              key={site.slug}
              type="button"
              onClick={() => void openExternal(site.url)}
              className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-left text-sm text-zinc-200 transition hover:bg-white/10 hover:text-white"
            >
              <img
                src={`https://cdn.simpleicons.org/${site.slug}/white`}
                alt=""
                aria-hidden="true"
                width={22}
                height={22}
                className="size-[22px] shrink-0"
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                }}
              />
              <span className="truncate">{site.name}</span>
            </button>
          ))}
        </div>

        <p className="mt-5 text-center text-[11px] text-zinc-500">
          {t("sites.footer")}
        </p>
      </GlassPanel>
    </div>
  );
}
