import type { HTMLAttributes, ReactNode, Ref } from "react";

interface GlassPanelProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  /** Optional ref to the underlying div (React 19 ref-as-prop). */
  ref?: Ref<HTMLDivElement>;
}

/**
 * Frosted-glass container used across the app (cards, sidebar, input wrapper).
 * Centralizes the border / blur / translucent-background treatment so the
 * look stays consistent and is tweakable in one place.
 */
export function GlassPanel({
  children,
  className = "",
  ref,
  ...rest
}: GlassPanelProps) {
  return (
    <div
      ref={ref}
      className={`rounded-3xl border border-white/10 bg-white/[0.06] ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
