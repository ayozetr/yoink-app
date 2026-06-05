import { useMemo, useState } from "react";
import { Clock3, Download, Info, User, Video } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { Button } from "../../../components/ui/Button";
import { Select } from "../../../components/ui/Select";
import { Toggle } from "../../../components/ui/Toggle";
import { Thumbnail } from "../../../components/ui/Thumbnail";
import type {
  AudioFormat,
  MediaKind,
  VideoContainer,
  VideoInfo,
} from "../../../types/download";
import {
  AUDIO_FORMATS,
  DEFAULT_AUDIO_FORMAT,
  DEFAULT_CONTAINER,
  VIDEO_CONTAINERS,
  availableKinds,
  videoQualities,
} from "../formatOptions";

export interface DownloadSelection {
  kind: MediaKind;
  /** Target quality, e.g. "1080p". Undefined for audio-only downloads. */
  quality?: string;
  /** Output container, only meaningful for video downloads. */
  container?: VideoContainer;
  /** Output format, only meaningful for audio downloads. */
  audio_format?: AudioFormat;
  /** Embed subtitles into the video output. Only set for video downloads. */
  embed_subs?: boolean;
  /** Subtitle language to embed: a code like "en"/"es" or "all". */
  subtitle_lang?: string;
  /** Embed chapter markers. Only set for video downloads. */
  embed_chapters?: boolean;
  /** Include all audio tracks in the video output. Only set for video downloads. */
  audio_multistreams?: boolean;
}

/** Sentinel value for the "no subtitles" entry in the language picker. */
const SUBS_NONE = "__none__";

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
  const [container, setContainer] = useState<VideoContainer>(DEFAULT_CONTAINER);
  const [audioFormat, setAudioFormat] = useState<AudioFormat>(
    DEFAULT_AUDIO_FORMAT,
  );
  // "None" by default: subtitles are opt-in.
  const [subtitle, setSubtitle] = useState<string>(SUBS_NONE);
  const [embedChapters, setEmbedChapters] = useState(false);
  const [audioMultistreams, setAudioMultistreams] = useState(false);

  const isVideo = kind === "video";
  const hasSubtitles =
    info.subtitle_langs.length > 0 || info.auto_caption_langs.length > 0;
  const embedSubs = subtitle !== SUBS_NONE;
  // Subtitles embed losslessly only into MKV (MP4/MOV are limited to mov_text),
  // so the subtitle picker is offered for MKV only.
  const showSubtitles = isVideo && hasSubtitles && container === "mkv";
  // Multiple audio tracks embed cleanly only into MKV, and only when the source
  // actually exposes more than one audio language.
  const showMultiAudio =
    isVideo && container === "mkv" && info.audio_langs.length > 1;

  // FLAC/WAV only make sense from a lossless source; otherwise they'd upscale.
  const losslessAllowed = info.source_lossless;
  // If a lossless format is selected but the source isn't lossless, fall back.
  const effectiveAudioFormat: AudioFormat =
    !losslessAllowed &&
    AUDIO_FORMATS.find((o) => o.value === audioFormat)?.lossless
      ? DEFAULT_AUDIO_FORMAT
      : audioFormat;
  const showLosslessWarning = !isVideo && !losslessAllowed;

  return (
    <GlassPanel className="p-5">
      <div className="flex gap-5">
        {/* Thumbnail */}
        <div className="w-[320px] h-[180px] rounded-2xl overflow-hidden relative bg-gradient-to-br from-violet-600/40 to-blue-600/40 flex items-center justify-center">
          {info.thumbnail_url ? (
            <Thumbnail
              src={info.thumbnail_url}
              alt={info.title}
              referer={info.webpage_url}
              className="absolute inset-0 h-full w-full object-cover"
              fallback={<Video className="size-14 text-white/80" />}
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

          <div className="mt-6 flex flex-col gap-3">
            <div className="grid md:grid-cols-3 gap-3">
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

              {isVideo ? (
                <>
                  <Select
                    ariaLabel={t("preview.quality")}
                    value={qualities.length > 0 ? quality : "__best__"}
                    onChange={setQuality}
                    disabled={qualities.length === 0}
                    options={
                      qualities.length > 0
                        ? qualities.map((option) => ({
                            value: option,
                            label: option,
                          }))
                        : [{ value: "__best__", label: t("preview.bestQuality") }]
                    }
                    className="h-12 rounded-xl bg-surface border border-white/10 px-4 w-full text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  />

                  <Select
                    ariaLabel={t("preview.container")}
                    value={container}
                    onChange={(v) => setContainer(v as VideoContainer)}
                    options={VIDEO_CONTAINERS}
                    className="h-12 rounded-xl bg-surface border border-white/10 px-4 w-full text-sm"
                  />
                </>
              ) : (
                <Select
                  ariaLabel={t("preview.audioFormat")}
                  value={effectiveAudioFormat}
                  onChange={(v) => setAudioFormat(v as AudioFormat)}
                  options={AUDIO_FORMATS.map((option) => ({
                    value: option.value,
                    label: option.label,
                    disabled: option.lossless && !losslessAllowed,
                  }))}
                  className="h-12 rounded-xl bg-surface border border-white/10 px-4 w-full text-sm md:col-span-2"
                />
              )}
            </div>

            {showLosslessWarning && (
              <p className="flex items-center gap-2 text-xs text-zinc-400">
                <Info size={14} className="shrink-0" />
                {t("preview.losslessWarning")}
              </p>
            )}

            {!isVideo && effectiveAudioFormat === "wav" && (
              <p className="flex items-center gap-2 text-xs text-zinc-400">
                <Info size={14} className="shrink-0" />
                {t("preview.wavCoverWarning")}
              </p>
            )}

            {/* Subtitles (MKV only) + chapters + multi-audio: video-only, when available. */}
            {(showSubtitles || (isVideo && info.has_chapters) || showMultiAudio) && (
              <div className="flex flex-wrap items-center gap-3">
                {showSubtitles && (
                  <Select
                    ariaLabel={t("preview.subtitles")}
                    value={subtitle}
                    onChange={setSubtitle}
                    options={[
                      { value: SUBS_NONE, label: t("preview.subtitlesNone") },
                      { value: "all", label: t("preview.subtitlesAll") },
                      ...(info.subtitle_langs.length > 0
                        ? [
                            {
                              value: "__hdr_manual",
                              label: t("preview.subtitlesManual"),
                              header: true,
                            },
                            ...info.subtitle_langs.map((code) => ({
                              value: code,
                              label: code.toUpperCase(),
                            })),
                          ]
                        : []),
                      ...(info.auto_caption_langs.length > 0
                        ? [
                            {
                              value: "__hdr_auto",
                              label: t("preview.subtitlesAuto"),
                              header: true,
                            },
                            ...info.auto_caption_langs.map((code) => ({
                              value: code,
                              label: code.toUpperCase(),
                            })),
                          ]
                        : []),
                    ]}
                    className="h-11 min-w-[160px] flex-1 rounded-xl bg-surface border border-white/10 px-4 text-sm"
                  />
                )}
                {info.has_chapters && (
                  <Toggle
                    checked={embedChapters}
                    onChange={setEmbedChapters}
                    label={t("preview.chapters")}
                  />
                )}
                {showMultiAudio && (
                  <Toggle
                    checked={audioMultistreams}
                    onChange={setAudioMultistreams}
                    label={t("preview.multiAudio")}
                  />
                )}
              </div>
            )}

            <Button
              variant="gradient"
              onClick={() =>
                onDownload({
                  kind,
                  quality: isVideo ? quality : undefined,
                  container: isVideo ? container : undefined,
                  audio_format: isVideo ? undefined : effectiveAudioFormat,
                  embed_subs: showSubtitles ? embedSubs : undefined,
                  subtitle_lang:
                    showSubtitles && embedSubs ? subtitle : undefined,
                  embed_chapters: isVideo ? embedChapters : undefined,
                  audio_multistreams: showMultiAudio
                    ? audioMultistreams
                    : undefined,
                })
              }
              className="h-12 w-full"
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
