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
    <div className="min-h-screen bg-canvas text-white overflow-hidden">
      <BackgroundGlow />

      <div className="relative flex h-screen p-6 gap-6">
        <main className="flex-1 flex flex-col gap-6">{main}</main>
        {sidebar}
      </div>
    </div>
  );
}
