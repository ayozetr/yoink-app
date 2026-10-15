// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

import type { HTMLAttributes, ReactNode, Ref } from "react";

interface GlassPanelProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  /** Render the boxed surface (rounded + hairline border + surface bg). Used by
   *  dialogs/modals. Content views leave it off so they sit flat on the canvas
   *  (the v4 "no boxes" editorial look). */
  boxed?: boolean;
  /** Optional ref to the underlying div (React 19 ref-as-prop). */
  ref?: Ref<HTMLDivElement>;
}

/**
 * Container used across the app. In the v4 "Flat Minimal" redesign content sits
 * directly on the canvas (no card boxes) — so this is a plain passthrough by
 * default, and only opts into a surface box when `boxed` is set (dialogs).
 */
export function GlassPanel({
  children,
  className = "",
  boxed = false,
  ref,
  ...rest
}: GlassPanelProps) {
  return (
    <div
      ref={ref}
      className={`${boxed ? "rounded-2xl border border-line/10 bg-surface " : ""}${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
