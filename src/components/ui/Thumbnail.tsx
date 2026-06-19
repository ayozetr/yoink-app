import { useState, type ReactNode } from "react";
import { thumbnailProxyUrl } from "../../lib/api";

/** Stages of the thumbnail load fallback chain. */
type Stage = "direct" | "proxy" | "failed";

interface ThumbnailProps {
  /** Remote image URL from the source CDN. */
  src: string;
  alt: string;
  className?: string;
  /** Rendered when both the direct and proxied loads fail. */
  fallback: ReactNode;
  /**
   * Page URL forwarded as the proxy's `Referer`. Some CDNs hotlink-protect
   * by Referer and 403 the proxy without it.
   */
  referer?: string | null;
  /** Native `<img>` loading hint — "lazy" defers offscreen loads in long lists. */
  loading?: "lazy" | "eager";
}

/**
 * Thumbnail image with a graceful fallback chain:
 * direct CDN URL → backend proxy (`/api/thumbnail`) → placeholder.
 *
 * Some CDNs block hotlinking by Referer or origin; `referrerPolicy` handles the
 * easy cases, and the proxy (with the page `referer`) handles the strict ones.
 * A small stage flag guards against an infinite `onError` loop.
 */
export function Thumbnail({
  src,
  alt,
  className,
  fallback,
  referer,
  loading,
}: ThumbnailProps) {
  const [stage, setStage] = useState<Stage>("direct");
  const [prevSrc, setPrevSrc] = useState(src);

  // Restart the fallback chain when the image changes, so a reused instance
  // (rendered without a fresh key) doesn't keep a previous "failed"/"proxy".
  // React's "adjust state during render" pattern — no effect, no extra paint.
  if (src !== prevSrc) {
    setPrevSrc(src);
    setStage("direct");
  }

  if (stage === "failed") {
    return <>{fallback}</>;
  }

  return (
    <img
      src={stage === "direct" ? src : thumbnailProxyUrl(src, referer)}
      alt={alt}
      className={className}
      loading={loading}
      referrerPolicy="no-referrer"
      onError={() => setStage(stage === "direct" ? "proxy" : "failed")}
    />
  );
}
