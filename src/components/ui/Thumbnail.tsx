import { useMemo, useState, type ReactNode } from "react";
import { thumbnailProxyUrl } from "../../lib/api";
import { youtubeFallback } from "./youtubeFallback";

/** Stages of loading a single candidate URL. */
type Stage = "direct" | "proxy";

interface ThumbnailProps {
  /** Remote image URL from the source CDN. */
  src: string;
  alt: string;
  className?: string;
  /** Rendered when every candidate (direct + proxied) fails. */
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
 * Thumbnail image with a graceful fallback chain. Each candidate URL is tried
 * directly, then through the backend proxy (`/api/thumbnail`); when all
 * candidates fail, the placeholder shows.
 *
 * Candidates: the source URL, then — for YouTube — a guaranteed `hqdefault.jpg`
 * (the reported `maxresdefault` 404s on videos without a high-res thumbnail).
 * Some CDNs block hotlinking by Referer or origin; `referrerPolicy` handles the
 * easy cases, and the proxy (with the page `referer`) handles the strict ones.
 */
export function Thumbnail({
  src,
  alt,
  className,
  fallback,
  referer,
  loading,
}: ThumbnailProps) {
  const candidates = useMemo(() => {
    const list = [src];
    const yt = youtubeFallback(src);
    if (yt) list.push(yt);
    return list;
  }, [src]);

  const [prevSrc, setPrevSrc] = useState(src);
  const [index, setIndex] = useState(0);
  const [stage, setStage] = useState<Stage>("direct");

  // Restart the chain when the image changes, so a reused instance (rendered
  // without a fresh key) doesn't keep a previous index/stage. React's "adjust
  // state during render" pattern — no effect, no extra paint.
  if (src !== prevSrc) {
    setPrevSrc(src);
    setIndex(0);
    setStage("direct");
  }

  if (index >= candidates.length) {
    return <>{fallback}</>;
  }

  const current = candidates[index];
  return (
    <img
      src={stage === "direct" ? current : thumbnailProxyUrl(current, referer)}
      alt={alt}
      className={className}
      loading={loading}
      referrerPolicy="no-referrer"
      onError={() => {
        if (stage === "direct") {
          setStage("proxy");
        } else {
          setIndex(index + 1);
          setStage("direct");
        }
      }}
      onLoad={(e) => {
        // YouTube serves a 120x90 grey "no thumbnail" placeholder with HTTP 200
        // (not a 404) for a missing maxresdefault, so onError never fires. Treat
        // a tiny image as a miss and advance to the next candidate (hqdefault is
        // always full-size). Real thumbnails are >= 320px wide.
        if (
          index < candidates.length - 1 &&
          e.currentTarget.naturalWidth > 0 &&
          e.currentTarget.naturalWidth <= 120
        ) {
          setIndex(index + 1);
          setStage("direct");
        }
      }}
    />
  );
}
