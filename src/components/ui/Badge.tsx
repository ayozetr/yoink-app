import type { ReactNode } from "react";

interface BadgeProps {
  children: ReactNode;
  className?: string;
}

/** Small pill-shaped label (e.g. "Recientes", status chips). */
export function Badge({ children, className = "" }: BadgeProps) {
  return (
    <span
      className={`text-xs px-2 py-1 rounded-lg border ${className}`}
    >
      {children}
    </span>
  );
}
