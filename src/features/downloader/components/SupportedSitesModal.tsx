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
  /** Optional size override for the inline Icon (e.g. wide wordmarks). */
  iconClass?: string;
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

/** Amazon Music's official logo (not in Simple Icons), folded to one colour. */
function AmazonMusicIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 90 90"
      aria-hidden="true"
      className={className}
      fill="currentColor"
    >
      <path d="M59.7,40.5c-0.6,0.4-1.5,0.7-2.6,0.7c-1.7,0-3.3-0.2-4.9-0.7c-0.4-0.1-0.7-0.2-0.9-0.2c-0.3,0-0.4,0.2-0.4,0.6 v1c0,0.3,0.1,0.5,0.2,0.7c0.1,0.1,0.3,0.3,0.6,0.4c1.6,0.7,3.4,1,5.4,1c2.1,0,3.7-0.5,5-1.5c1.3-1,1.9-2.3,1.9-4 c0-1.2-0.3-2.1-0.9-2.9c-0.6-0.7-1.6-1.4-3-1.9l-2.8-1.1c-1.1-0.4-1.9-0.8-2.2-1.2c-0.4-0.4-0.6-0.8-0.6-1.5c0-1.5,1.1-2.3,3.4-2.3 c1.3,0,2.6,0.2,3.8,0.6c0.4,0.1,0.7,0.2,0.8,0.2c0.3,0,0.5-0.2,0.5-0.6v-1c0-0.3-0.1-0.5-0.2-0.7c-0.1-0.2-0.3-0.3-0.6-0.4 c-1.5-0.5-3-0.8-4.5-0.8c-1.9,0-3.5,0.5-4.7,1.4c-1.2,0.9-1.8,2.2-1.8,3.7c0,2.3,1.3,4,3.9,5l3,1.1c1,0.4,1.6,0.7,2,1.1 c0.4,0.4,0.5,0.8,0.5,1.4C60.6,39.4,60.3,40.1,59.7,40.5z" />
      <path d="M44,26.1v13.3c-1.7,1.1-3.4,1.7-5.1,1.7c-1.1,0-1.9-0.3-2.4-0.9c-0.5-0.6-0.7-1.5-0.7-2.8V26.1 c0-0.5-0.2-0.7-0.7-0.7h-2.1c-0.5,0-0.7,0.2-0.7,0.7v12.4c0,1.7,0.4,3.1,1.3,4c0.9,0.9,2.2,1.4,3.9,1.4c2.3,0,4.6-0.8,6.8-2.4 l0.2,1.2c0,0.3,0.1,0.4,0.3,0.5c0.1,0.1,0.3,0.1,0.6,0.1h1.5c0.5,0,0.7-0.2,0.7-0.7V26.1c0-0.5-0.2-0.7-0.7-0.7h-2.1 C44.2,25.4,44,25.7,44,26.1z" />
      <path d="M25,43.4h2.1c0.5,0,0.7-0.2,0.7-0.7V30.2c0-1.7-0.4-3-1.3-3.9c-0.9-0.9-2.1-1.4-3.8-1.4c-2.3,0-4.7,0.8-7,2.5 c-0.8-1.7-2.3-2.5-4.5-2.5c-2.2,0-4.4,0.8-6.6,2.3l-0.2-1.1c0-0.3-0.1-0.4-0.3-0.5c-0.1-0.1-0.3-0.1-0.5-0.1H2 c-0.5,0-0.7,0.2-0.7,0.7v16.6c0,0.5,0.2,0.7,0.7,0.7h2.1c0.5,0,0.7-0.2,0.7-0.7V29.3c1.7-1,3.4-1.6,5.2-1.6c1,0,1.7,0.3,2.1,0.9 c0.4,0.6,0.7,1.4,0.7,2.6v11.5c0,0.5,0.2,0.7,0.7,0.7h2.1c0.5,0,0.7-0.2,0.7-0.7V30.4v-0.6c0-0.2,0-0.4,0-0.5 c1.8-1.1,3.5-1.6,5.2-1.6c1,0,1.7,0.3,2.1,0.9c0.4,0.6,0.7,1.4,0.7,2.6v11.5C24.3,43.2,24.5,43.4,25,43.4z" />
      <path d="M79.5,56.7c-10.9,4.6-22.8,6.9-33.6,6.9c-16,0-31.5-4.4-44-11.7c-0.2-0.1-0.4-0.2-0.6-0.2 c-0.7,0-1.1,0.8-0.4,1.5c11.6,10.5,27,16.8,44,16.8c12.2,0,26.3-3.8,36-11C82.6,57.8,81.2,56,79.5,56.7z" />
      <path d="M79.2,29.4c0.9-1,2.3-1.5,4.3-1.5c1,0,2,0.1,2.9,0.4c0.3,0.1,0.4,0.1,0.6,0.1c0.3,0,0.5-0.2,0.5-0.7v-1 c0-0.3-0.1-0.6-0.2-0.7c-0.1-0.1-0.3-0.3-0.5-0.4C85.5,25.3,84.2,25,83,25c-2.8,0-4.9,0.8-6.5,2.5c-1.5,1.6-2.3,4-2.3,7 c0,3,0.7,5.3,2.2,6.9c1.5,1.6,3.6,2.4,6.4,2.4c1.5,0,2.9-0.2,4-0.7c0.3-0.1,0.5-0.2,0.6-0.4c0.1-0.1,0.1-0.4,0.1-0.7v-1 c0-0.5-0.2-0.7-0.5-0.7c-0.1,0-0.3,0-0.5,0.1c-1.1,0.3-2.2,0.5-3.2,0.5c-1.9,0-3.3-0.5-4.2-1.5c-0.9-1-1.3-2.6-1.3-4.7v-0.5 C77.9,32,78.3,30.4,79.2,29.4z" />
      <path d="M83.7,66.1c5.2-4.4,6.6-13.5,5.5-14.9c-0.5-0.6-2.9-1.2-5.9-1.2c-3.2,0-7,0.7-9.9,2.7 c-0.9,0.6-0.7,1.4,0.2,1.3c3.1-0.4,10.1-1.2,11.4,0.4c1.2,1.6-1.4,8.2-2.6,11.1C82.1,66.4,82.8,66.7,83.7,66.1z" />
      <path d="M69.8,25.4h-2.1c-0.5,0-0.7,0.2-0.7,0.7v16.6c0,0.5,0.2,0.7,0.7,0.7h2.1c0.5,0,0.7-0.2,0.7-0.7V26.1 C70.5,25.7,70.3,25.4,69.8,25.4z" />
      <path d="M70.4,18.6C70,18.2,69.4,18,68.7,18c-0.7,0-1.2,0.2-1.6,0.6c-0.4,0.4-0.6,0.9-0.6,1.5c0,0.6,0.2,1.2,0.6,1.5 c0.4,0.4,0.9,0.6,1.6,0.6c0.7,0,1.2-0.2,1.6-0.6c0.4-0.4,0.6-0.9,0.6-1.5C70.9,19.5,70.8,18.9,70.4,18.6z" />
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
  { name: "Medal", url: "https://medal.tv", Icon: MedalIcon, iconClass: "size-[26px]" },
  { name: "YouTube Music", url: "https://music.youtube.com", slug: "youtubemusic" },
  { name: "Spotify", url: "https://spotify.com", slug: "spotify" },
  { name: "Deezer", url: "https://deezer.com", slug: "deezer" },
  { name: "Apple Music", url: "https://music.apple.com", slug: "applemusic" },
  { name: "Tidal", url: "https://tidal.com", slug: "tidal" },
  {
    name: "Amazon Music",
    url: "https://music.amazon.com",
    Icon: AmazonMusicIcon,
    iconClass: "size-[27px]",
  },
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
                <site.Icon
                  className={`${site.iconClass ?? "size-[22px]"} shrink-0 text-white`}
                />
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
