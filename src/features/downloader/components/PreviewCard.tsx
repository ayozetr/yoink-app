import { useMemo, useState } from "react";
import { Clock3, Download, User, Video } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { Button } from "../../../components/ui/Button";
import { Select } from "../../../components/ui/Select";
import type { MediaKind, VideoInfo } from "../../../types/download";
import { availableKinds, videoQualities } from "../formatOptions";

export interface DownloadSelection {
  kind: MediaKind;
  /** Target quality, e.g. "1080p". Undefined for audio-only downloads. */
  quality?: string;
}

interface PreviewCardProps {
  info: VideoInfo;
  onDownload: (selection: DownloadSelection) => void;
  defaultKind?: MediaKind;
  defaultQuality?: string;
}

/** Preview of the analyzed media: thumbnail, info and download controls. */
export function PreviewCard({
  info,
  onDownload,
  defaultKind,
  defaultQuality,
}: PreviewCardProps) {
  const { t } = useTranslation();
  const kinds = useMemo(() => availableKinds(info), [info]);
  const qualities = useMemo(() => videoQualities(info), [info]);

  // Seed from the user's defaults when they're actually available for this media.
  const [kind, setKind] = useState<MediaKind>(
    kinds.some((k) => k.kind === defaultKind) ? defaultKind! : kinds[0].kind,
  );
  const [quality, setQuality] = useState<string>(
    defaultQuality && qualities.includes(defaultQuality)
      ? defaultQuality
      : (qualities[0] ?? ""),
  );

  const isVideo = kind === "video";

  return (
    <GlassPanel className="p-5">
      <div className="flex gap-5">
        {/* Thumbnail */}
        <div className="w-[320px] h-[180px] rounded-2xl overflow-hidden relative bg-gradient-to-br from-violet-600/40 to-blue-600/40 flex items-center justify-center">
          {info.thumbnail_url ? (
            <img
              src={info.thumbnail_url}
              alt={info.title}
              className="absolute inset-0 h-full w-full object-cover"
            />
          ) : (
            <Video className="size-14 text-white/80" />
          )}
          <div className="absolute inset-0 bg-black/20" />
        </div>

        {/* Info + controls */}
        <div className="flex-1 flex flex-col justify-between">
          <div>
            <span className="text-xs uppercase tracking-wider text-violet-400">
              {t("preview.label")}
            </span>
            <h2 className="text-xl font-semibold mt-2">{info.title}</h2>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3 text-zinc-400">
              {info.duration_string && (
                <span className="flex items-center gap-2 text-sm">
                  <Clock3 size={16} />
                  {info.duration_string}
                </span>
              )}
              {info.uploader && (
                <span className="flex items-center gap-2 text-sm">
                  <User size={16} />
                  {info.uploader}
                </span>
              )}
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-3 mt-6">
            <Select
              ariaLabel={t("preview.format")}
              value={kind}
              onChange={(v) => setKind(v as MediaKind)}
              options={kinds.map((option) => ({
                value: option.kind,
                label:
                  option.kind === "video"
                    ? t("preview.video")
                    : t("preview.audio"),
              }))}
              className="h-12 rounded-xl bg-surface border border-white/10 px-4 w-full text-sm"
            />

            <Select
              ariaLabel={t("preview.quality")}
              value={isVideo && qualities.length > 0 ? quality : "__best__"}
              onChange={setQuality}
              disabled={!isVideo || qualities.length === 0}
              options={
                isVideo && qualities.length > 0
                  ? qualities.map((option) => ({ value: option, label: option }))
                  : [{ value: "__best__", label: t("preview.bestQuality") }]
              }
              className="h-12 rounded-xl bg-surface border border-white/10 px-4 w-full text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            />

            <Button
              variant="gradient"
              onClick={() =>
                onDownload({ kind, quality: isVideo ? quality : undefined })
              }
              className="h-12"
            >
              <Download size={18} />
              {t("preview.download")}
            </Button>
          </div>
        </div>
      </div>
    </GlassPanel>
  );
}
