import type { ReactNode } from "react";
import { BackgroundGlow } from "./BackgroundGlow";

interface AppLayoutProps {
  /** Primary column (the downloader). */
  main: ReactNode;
  /** Secondary column (the history sidebar). */
  sidebar: ReactNode;
}

/**
 * Top-level shell: dark canvas, background glow, and the two-column
 * main/sidebar flex layout.
 */
export function AppLayout({ main, sidebar }: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-canvas text-white">
      <BackgroundGlow />

      {/* Row on wide screens (each column scrolls on its own); stacked with
          page scroll on narrow ones. */}
      <div className="relative flex flex-col lg:flex-row lg:h-screen p-4 sm:p-6 gap-4 sm:gap-6">
        <main className="flex-1 min-w-0 flex flex-col gap-4 sm:gap-6 lg:overflow-y-auto">
          {main}
        </main>
        <div className="w-full lg:w-[360px] lg:shrink-0 lg:h-full">{sidebar}</div>
      </div>
    </div>
  );
}
