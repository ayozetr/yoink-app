import type { HTMLAttributes, ReactNode } from "react";

interface GlassPanelProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

/**
 * Frosted-glass container used across the app (cards, sidebar, input wrapper).
 * Centralizes the border / blur / translucent-background treatment so the
 * look stays consistent and is tweakable in one place.
 */
export function GlassPanel({
  children,
  className = "",
  ...rest
}: GlassPanelProps) {
  return (
    <div
      className={`rounded-3xl border border-white/10 bg-white/[0.06] ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
