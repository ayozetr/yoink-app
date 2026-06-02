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
}

/**
 * Thumbnail image with a graceful fallback chain:
 * direct CDN URL → backend proxy (`/api/thumbnail`) → placeholder.
 *
 * Some CDNs block hotlinking by Referer or origin; `referrerPolicy` handles the
 * easy cases, and the proxy handles the strict ones. A small stage flag guards
 * against an infinite `onError` loop.
 */
export function Thumbnail({ src, alt, className, fallback }: ThumbnailProps) {
  const [stage, setStage] = useState<Stage>("direct");

  if (stage === "failed") {
    return <>{fallback}</>;
  }

  return (
    <img
      src={stage === "direct" ? src : thumbnailProxyUrl(src)}
      alt={alt}
      className={className}
      referrerPolicy="no-referrer"
      onError={() => setStage(stage === "direct" ? "proxy" : "failed")}
    />
  );
}
