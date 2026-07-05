/**
 * A country flag (flag-icons 4x3 SVG, served from /public/flags) used to mark
 * each language in the settings language picker. SVG — not the flag emoji, which
 * Windows renders as bare country-code letters instead of a flag.
 */
export function FlagIcon({
  code,
  className = "",
}: {
  code: string;
  className?: string;
}) {
  return (
    <img
      src={`/flags/${code}.svg`}
      alt=""
      aria-hidden="true"
      className={`h-3.5 w-5 shrink-0 rounded-[3px] object-cover ring-1 ring-white/15 ${className}`}
    />
  );
}
