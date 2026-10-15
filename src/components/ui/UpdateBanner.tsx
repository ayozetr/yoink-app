// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

import { ArrowUpCircle, X } from "lucide-react";
import { useTranslation } from "react-i18next";

interface UpdateBannerProps {
  version: string;
  /** Open Settings (its update section installs / links to the release). */
  onAction: () => void;
  onDismiss: () => void;
}

/** A dismissible "a newer version is available" toast, floated at the bottom-left
 * when the opt-in launch check finds an update. */
export function UpdateBanner({ version, onAction, onDismiss }: UpdateBannerProps) {
  const { t } = useTranslation();
  return (
    <div className="fixed bottom-4 left-4 z-40 flex max-w-md items-center gap-3 rounded-xl border border-accent/40 bg-surface px-4 py-2.5 text-sm shadow-2xl">
      <ArrowUpCircle size={18} className="shrink-0 text-accent-soft" />
      <span className="flex-1">{t("update.available", { version })}</span>
      <button
        type="button"
        onClick={onAction}
        className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white transition hover:bg-accent-soft"
      >
        {t("update.action")}
      </button>
      <button
        type="button"
        onClick={onDismiss}
        aria-label={t("update.dismiss")}
        className="shrink-0 text-fg-dim transition hover:text-fg"
      >
        <X size={16} />
      </button>
    </div>
  );
}
