// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

import type { ReactNode } from "react";
import { TabBar, type TabId } from "./TabBar";
import logoUrl from "../../assets/logo.png";

interface AppShellProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  queueCount?: number;
  /** The active view's content (all views stay mounted; the shell just frames). */
  children: ReactNode;
}

/**
 * Top-level shell for the v4 "Flat Minimal" redesign: a flat dark (or light)
 * canvas, a slim brand/topbar, the modular tab navigation, and a single content
 * column. No fixed side panels, no background glow — everything lives in a tab.
 */
export function AppShell({
  activeTab,
  onTabChange,
  queueCount,
  children,
}: AppShellProps) {
  return (
    <div className="flex h-screen flex-col bg-canvas text-fg">
      <div className="mx-auto flex h-full w-full max-w-4xl flex-col px-4 sm:px-6">
        <header className="flex flex-none items-center gap-4 pb-4 pt-5">
          <div className="flex items-center gap-2.5">
            <img
              src={logoUrl}
              alt=""
              className="size-7 shrink-0 rounded-lg"
              aria-hidden
            />
            <span className="font-display text-2xl leading-none tracking-tight">
              Yoink
            </span>
          </div>
        </header>

        <div className="flex-none pb-5">
          <TabBar
            active={activeTab}
            onChange={onTabChange}
            queueCount={queueCount}
          />
        </div>

        {/* Scrolling content area: the brand + tabs stay fixed above. No top
            padding here (the tab bar's pb-5 provides the gap) so a per-view
            sticky header anchors flush at the top with nothing peeking above it. */}
        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto pb-5">
          {children}
        </main>
      </div>
    </div>
  );
}
