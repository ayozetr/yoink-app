import { Loader2 } from "lucide-react";

interface SplashProps {
  /** While true the splash covers the app; it fades out when false. */
  visible: boolean;
}

/**
 * Startup overlay shown while the bundled backend (sidecar) boots — it can take
 * a few seconds to unpack ffmpeg and start. Fades out once the API responds.
 */
export function Splash({ visible }: SplashProps) {
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
      <Loader2 className="h-9 w-9 animate-spin text-violet-400" />
      <p className="text-sm text-zinc-400">Preparando todo…</p>
    </div>
  );
}
