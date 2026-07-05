/**
 * A YouTube thumbnail to fall back on when the picked one 404s.
 *
 * yt-dlp reports `maxresdefault.jpg` as the thumbnail, but YouTube only
 * generates the high-res variants (`maxresdefault`, `hq720`) for some videos;
 * for the rest it serves a 120x90 grey placeholder (HTTP 200, not a 404).
 * `hqdefault.jpg` is always generated full-size, so it's the safe fallback.
 * Returns null for non-YouTube URLs or one that's already the fallback.
 */
export function youtubeFallback(url: string): string | null {
  const m = url.match(
    /^(https?:\/\/i\.ytimg\.com)\/vi(?:_webp)?\/([^/]+)\/[^/]+$/,
  );
  if (!m) return null;
  const downgraded = `${m[1]}/vi/${m[2]}/hqdefault.jpg`;
  return downgraded === url ? null : downgraded;
}
