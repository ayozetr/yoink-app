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
}: ThumbnailProps) {
  const [stage, setStage] = useState<Stage>("direct");

  if (stage === "failed") {
    return <>{fallback}</>;
  }

  return (
    <img
      src={stage === "direct" ? src : thumbnailProxyUrl(src, referer)}
      alt={alt}
      className={className}
      referrerPolicy="no-referrer"
      onError={() => setStage(stage === "direct" ? "proxy" : "failed")}
    />
  );
}
