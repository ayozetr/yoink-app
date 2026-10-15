// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

import { memo } from "react";
import { Download, ImageIcon, User } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { Button } from "../../../components/ui/Button";
import { Thumbnail } from "../../../components/ui/Thumbnail";
import type { VideoInfo } from "../../../types/download";
import type { DownloadSelection } from "./PreviewCard";

interface ImagePreviewCardProps {
  info: VideoInfo;
  onDownload: (selection: DownloadSelection) => void;
  locked?: boolean;
}

/**
 * Preview + download for a still-image item (e.g. an Instagram photo). Images
 * are a separate output kind — no video/audio formats, no quality/container
 * picker — so this is a deliberately minimal card: show the picture and offer a
 * one-click image download (`kind: "image"`). The regular {@link PreviewCard} is
 * used for everything with real video/audio formats.
 */
export const ImagePreviewCard = memo(function ImagePreviewCard({
  info,
  onDownload,
  locked = false,
}: ImagePreviewCardProps) {
  const { t } = useTranslation();

  return (
    <GlassPanel className="p-5">
      <div className="flex flex-col gap-5 sm:flex-row">
        {/* The image itself — contain (not cover) so a portrait photo isn't cropped. */}
        <div className="relative flex aspect-video w-full shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br from-violet-600/40 to-blue-600/40 sm:aspect-auto sm:h-[180px] sm:w-[320px]">
          {info.thumbnail_url ? (
            <Thumbnail
              src={info.thumbnail_url}
              alt={info.title}
              referer={info.webpage_url}
              className="absolute inset-0 h-full w-full object-contain"
              fallback={<ImageIcon className="size-14 text-white/80" />}
            />
          ) : (
            <ImageIcon className="size-14 text-white/80" />
          )}
        </div>

        {/* Info + download */}
        <div className="flex flex-1 flex-col justify-between">
          <div>
            <span className="text-xs uppercase tracking-wider text-accent-soft">
              {t("preview.imageLabel")}
            </span>
            <h2 className="mt-2 text-xl font-semibold">{info.title}</h2>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-fg-dim">
              <span className="flex items-center gap-1.5 rounded-full bg-accent/15 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-accent-soft ring-1 ring-accent/30">
                <ImageIcon size={14} />
                {t("preview.imageBadge")}
              </span>
              {info.uploader && (
                <span className="flex items-center gap-2 text-sm">
                  <User size={16} />
                  {info.uploader}
                </span>
              )}
            </div>
          </div>

          <div className="mt-6">
            <Button
              onClick={() => onDownload({ kind: "image" })}
              disabled={locked}
              className="w-full sm:w-auto"
            >
              <Download size={18} />
              {t("preview.downloadImage")}
            </Button>
          </div>
        </div>
      </div>
    </GlassPanel>
  );
});
