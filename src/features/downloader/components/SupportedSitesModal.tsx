import { useEffect, type ComponentType } from "react";
import { useTranslation } from "react-i18next";
import { Globe, X } from "lucide-react";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { openExternal } from "../../../lib/openExternal";
import { useFocusTrap } from "../../../lib/useFocusTrap";

interface SupportedSitesModalProps {
  onClose: () => void;
}

interface SupportedSite {
  /** Brand name — not translated. */
  name: string;
  /** Page opened when the row is clicked. */
  url: string;
  /** Simple Icons slug for the CDN logo. Omitted when there's no brand icon. */
  slug?: string;
  /** Inline logo for brands missing from Simple Icons (takes precedence over slug). */
  Icon?: ComponentType<{ className?: string }>;
}

/** Medal's logo (not in Simple Icons); strokes use currentColor. */
function MedalIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 48 48"
      aria-hidden="true"
      className={className}
    >
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        d="m11.061 27.188l5.856-3.474M24 27.758l12.939-7.388v15.064l6.561-4.102V16.476l-6.561-3.91L24 20.146l-12.939-7.58l-6.561 3.91v14.856l6.561 4.102V20.37z"
      />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M36.939 35.434L24 27.758l-12.939 7.676m25.878-8.246l-5.856-3.474"
      />
    </svg>
  );
}

/** Manually verified platforms. Typed array so it's easy to extend later. */
const SUPPORTED_SITES: readonly SupportedSite[] = [
  { name: "YouTube", url: "https://youtube.com", slug: "youtube" },
  { name: "Dailymotion", url: "https://dailymotion.com", slug: "dailymotion" },
  { name: "TikTok", url: "https://tiktok.com", slug: "tiktok" },
  { name: "Facebook", url: "https://facebook.com", slug: "facebook" },
  { name: "Instagram", url: "https://instagram.com", slug: "instagram" },
  { name: "Threads", url: "https://threads.com", slug: "threads" },
  { name: "X (Twitter)", url: "https://x.com", slug: "x" },
  { name: "Reddit", url: "https://reddit.com", slug: "reddit" },
  { name: "Vimeo", url: "https://vimeo.com", slug: "vimeo" },
  { name: "Twitch", url: "https://twitch.tv", slug: "twitch" },
  { name: "Kick", url: "https://kick.com", slug: "kick" },
  { name: "Medal", url: "https://medal.tv", Icon: MedalIcon },
  { name: "YouTube Music", url: "https://music.youtube.com", slug: "youtubemusic" },
  { name: "Spotify", url: "https://spotify.com", slug: "spotify" },
  { name: "SoundCloud", url: "https://soundcloud.com", slug: "soundcloud" },
  { name: "BandLab", url: "https://bandlab.com", slug: "bandlab" },
];

/** Modal listing the manually-verified sites (logo + name), each clickable. */
export function SupportedSitesModal({ onClose }: SupportedSitesModalProps) {
  const { t } = useTranslation();
  const dialogRef = useFocusTrap<HTMLDivElement>();

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
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-lg max-h-[calc(100vh-2rem)] overflow-y-auto p-6 !bg-[#16181f] outline-none"
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
              key={site.name}
              type="button"
              onClick={() => void openExternal(site.url)}
              className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-left text-sm text-zinc-200 transition hover:bg-white/10 hover:text-white"
            >
              {site.slug ? (
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
              ) : site.Icon ? (
                <site.Icon className="size-[22px] shrink-0 text-white" />
              ) : (
                <Globe size={20} className="size-[22px] shrink-0 text-zinc-500" />
              )}
              <span className="truncate">{site.name}</span>
            </button>
          ))}
        </div>

        <p className="mt-5 text-center text-[11px] text-zinc-400">
          {t("sites.footer")}
        </p>
      </GlassPanel>
    </div>
  );
}
