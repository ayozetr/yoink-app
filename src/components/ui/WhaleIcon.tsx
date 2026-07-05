import type { SVGProps } from "react";

/**
 * Naver Whale (browser) — a whale in the lucide line style (from lucide-lab), so it
 * sits with the app's other line icons in the cookie-source dropdown. Naver's brand
 * mark for the browser isn't in simple-icons, and it *is* a whale.
 */
export function WhaleIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M18 9.1V5a2 2 0 0 0-4 0m4 0a2 2 0 0 1 4 0" />
      <path d="M6 9.7L3.9 8.4C2.7 7.7 2 6.4 2 5V3c2 0 4 2 4 2s2-2 4-2v2c0 1.4-.7 2.7-1.9 3.4l-3.8 2.4A5 5 0 0 0 7 20h12c1.7 0 3-1.3 3-3v-3c0-2.8-2.2-5-5-5c-2.7 0-5.1 1.4-6.4 3.6L9.7 14A2 2 0 0 1 6 13Zm9 5.3h.01" />
    </svg>
  );
}
