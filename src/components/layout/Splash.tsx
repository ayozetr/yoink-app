import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

interface SplashProps {
  /** While true the splash covers the app; it fades out when false. */
  visible: boolean;
}

/**
 * Startup overlay shown while the bundled backend (sidecar) boots — it can take
 * a few seconds to unpack ffmpeg and start. Fades out once the API responds,
 * then **unmounts** so a hidden splash never leaves a full-screen `z-100`
 * overlay (with a perpetually spinning icon) in the DOM — which wasted work and
 * intermittently destabilized clicks in the tests.
 */
export function Splash({ visible }: SplashProps) {
  const { t } = useTranslation();
  const [mounted, setMounted] = useState(visible);

  useEffect(() => {
    if (visible) {
      setMounted(true);
      return;
    }
    // Keep it around for the fade-out, then remove it entirely.
    const timer = setTimeout(() => setMounted(false), 500); // matches duration-500
    return () => clearTimeout(timer);
  }, [visible]);

  if (!mounted) return null;

  return (
    <div
      aria-hidden={!visible}
      className={`fixed inset-0 z-[100] flex flex-col items-center justify-center gap-5 transition-opacity duration-500 ${
        visible ? "opacity-100" : "pointer-events-none opacity-0"
      }`}
      style={{
        background: "radial-gradient(circle at center, #16131f, #0a0a0f 70%)",
      }}
    >
      <Loader2 className="size-9 animate-spin text-violet-400" />
      <p className="text-sm text-zinc-400">{t("splash.preparing")}</p>
    </div>
  );
}
