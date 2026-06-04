/**
 * Best-effort "Artist - Title" guess from a download filename, used to seed the
 * catalogue search when a file isn't matched automatically. Strips the
 * extension and trailing tags like "(Official Video)"/"(prod. …)", then splits
 * on the first " - ".
 */
export function guessFromFilename(name?: string): {
  artist: string;
  title: string;
} {
  if (!name) return { artist: "", title: "" };
  const base = name
    .replace(/\.[^.]+$/, "")
    .replace(
      /\s*[([](?:official|video|audio|lyrics?|visualizer|hd|4k|mv|prod)[^)\]]*[)\]]/gi,
      "",
    )
    .trim();
  const match = base.match(/^(.+?)\s[-–—]\s(.+)$/);
  return match
    ? { artist: match[1].trim(), title: match[2].trim() }
    : { artist: "", title: base };
}
