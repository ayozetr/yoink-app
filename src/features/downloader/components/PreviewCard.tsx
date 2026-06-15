import { useMemo, useState } from "react";
import {
  ChevronDown,
  Clock3,
  Download,
  Glasses,
  Info,
  Scissors,
  SlidersHorizontal,
  User,
  Video,
} from "lucide-react";
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
  VRLayout,
} from "../../../types/download";
import {
  AUDIO_FORMATS,
  DEFAULT_AUDIO_FORMAT,
  DEFAULT_CONTAINER,
  VIDEO_CONTAINERS,
  VR_LAYOUTS,
  availableKinds,
  estimatedSizeBytes,
  videoQualities,
} from "../formatOptions";
import { formatBytes } from "../../../lib/format";
import { rememberLayout, rememberedLayout } from "../../../lib/vrPrefs";

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
  /** Clip start/end in seconds — download only that range. */
  trim_start?: number;
  trim_end?: number;
  /** Tag the output as immersive VR. Only set for video downloads. */
  is_vr?: boolean;
  /** Stereo/projection layout to tag with when is_vr is set. */
  vr_layout?: VRLayout;
}

/** Sentinel value for the "no subtitles" entry in the language picker. */
const SUBS_NONE = "__none__";

/** Parse "ss", "mm:ss" or "hh:mm:ss" into seconds (undefined if blank/invalid). */
function parseTime(value: string): number | undefined {
  const t = value.trim();
  // Strictly digits in 1–3 colon-separated groups: "ss", "mm:ss", "hh:mm:ss".
  // A regex avoids Number() coercion accepting "1:", "::", "0x10", "1e3", etc.
  if (!/^\d+(:\d+){0,2}$/.test(t)) return undefined;
  return t.split(":").reduce((acc, p) => acc * 60 + Number(p), 0);
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
  const [container, setContainer] = useState<VideoContainer>(DEFAULT_CONTAINER);
  const [audioFormat, setAudioFormat] = useState<AudioFormat>(
    DEFAULT_AUDIO_FORMAT,
  );
  // "None" by default: subtitles are opt-in.
  const [subtitle, setSubtitle] = useState<string>(SUBS_NONE);
  const [embedChapters, setEmbedChapters] = useState(false);
  const [audioMultistreams, setAudioMultistreams] = useState(false);
  const [trimOpen, setTrimOpen] = useState(false);
  const [trimStart, setTrimStart] = useState("");
  const [trimEnd, setTrimEnd] = useState("");
  // Secondary controls (subs/chapters/multi-audio/VR/trim) collapse under an
  // "Advanced options" toggle so the format grid + Download stay above the fold.
  // Auto-opened when VR is detected, since that needs the user to confirm.
  const [advancedOpen, setAdvancedOpen] = useState(info.is_vr);
  // VR tagging: seed from the backend's heuristic detection; the user can
  // toggle it and pick the stereo/projection layout. A previously remembered
  // choice for this uploader wins over the heuristic's guess.
  const [isVr, setIsVr] = useState(info.is_vr);
  const [vrLayout, setVrLayout] = useState<VRLayout>(
    () => rememberedLayout(info.uploader) ?? info.vr_layout,
  );

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

  // Rough download-size estimate for the current selection (null if unknown).
  const estimatedSize = useMemo(
    () =>
      formatBytes(
        estimatedSizeBytes(
          info,
          kind,
          isVideo ? quality : undefined,
          isVideo ? undefined : effectiveAudioFormat,
        ),
      ),
    [info, kind, isVideo, quality, effectiveAudioFormat],
  );

  const trimStartSec = parseTime(trimStart);
  const trimEndSec = parseTime(trimEnd);
  // Invalid when a given end isn't past the (effective) start — also catches a
  // lone end of 0, which would otherwise be an empty (0,0) range.
  const trimError =
    trimOpen && trimEndSec != null && trimEndSec <= (trimStartSec ?? 0);

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
              {info.is_vr && (
                <span className="flex items-center gap-1.5 rounded-full bg-violet-500/15 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-violet-300 ring-1 ring-violet-500/30">
                  <Glasses size={14} />
                  {t("preview.vrBadge")}
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

            <button
              type="button"
              onClick={() => setAdvancedOpen((v) => !v)}
              aria-expanded={advancedOpen}
              className="flex h-11 w-fit items-center gap-2 rounded-xl border border-white/10 bg-surface px-4 text-sm text-zinc-300 transition hover:border-white/20"
            >
              <SlidersHorizontal size={16} />
              {t("preview.advanced")}
              <ChevronDown
                size={15}
                className={`text-zinc-400 transition-transform ${advancedOpen ? "rotate-180" : ""}`}
              />
            </button>

            {/* Subtitles (MKV only) + chapters + multi-audio: video-only, when available. */}
            {advancedOpen &&
              (showSubtitles || (isVideo && info.has_chapters) || showMultiAudio) && (
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

            {/* VR — shown only when detected as immersive. Lets the user confirm
                (or turn off a false positive) and pick the stereo/projection
                layout. Hidden for plain video so it can't be tagged by mistake. */}
            {advancedOpen && isVideo && info.is_vr && (
              <div className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-3">
                  <Toggle
                    checked={isVr}
                    onChange={setIsVr}
                    label={t("preview.vr")}
                  />
                  {isVr && (
                    <Select
                      ariaLabel={t("preview.vrLayout")}
                      value={vrLayout}
                      onChange={(v) => setVrLayout(v as VRLayout)}
                      // All layouts stay selectable (we can't reliably tell the
                      // exact one from metadata); the heuristic's guess is just
                      // flagged as "(detected)" and preselected.
                      options={VR_LAYOUTS.map((o) => ({
                        value: o.value,
                        label:
                          o.value === info.vr_layout
                            ? `${o.label} (${t("preview.vrDetected")})`
                            : o.label,
                      }))}
                      className="h-11 min-w-[170px] rounded-xl bg-surface border border-white/10 px-4 text-sm"
                    />
                  )}
                </div>
                {isVr && (
                  <p className="flex items-center gap-2 text-xs text-zinc-400">
                    <Info size={14} className="shrink-0" />
                    {t("preview.vrHint")}
                  </p>
                )}
              </div>
            )}

            {/* Trim / clip — scissors button + (when open) inline start/end inputs. */}
            {advancedOpen && (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setTrimOpen((v) => !v)}
                  aria-expanded={trimOpen}
                  className={`flex h-11 w-fit shrink-0 items-center gap-2 rounded-xl border px-4 text-sm transition ${
                    trimOpen
                      ? "border-violet-500/50 bg-violet-600/10 text-white"
                      : "border-white/10 bg-surface text-zinc-300 hover:border-white/20"
                  }`}
                >
                  <Scissors size={16} />
                  {t("preview.trim")}
                </button>
                {trimOpen && (
                  <>
                    <input
                      type="text"
                      inputMode="numeric"
                      aria-label={t("preview.trimStart")}
                      placeholder={t("preview.trimStart")}
                      value={trimStart}
                      onChange={(e) => setTrimStart(e.target.value)}
                      className="h-11 w-28 rounded-xl bg-surface border border-white/10 px-3 text-sm outline-none focus:border-violet-500"
                    />
                    <span className="text-zinc-500">→</span>
                    <input
                      type="text"
                      inputMode="numeric"
                      aria-label={t("preview.trimEnd")}
                      placeholder={t("preview.trimEnd")}
                      value={trimEnd}
                      onChange={(e) => setTrimEnd(e.target.value)}
                      className="h-11 w-28 rounded-xl bg-surface border border-white/10 px-3 text-sm outline-none focus:border-violet-500"
                    />
                    <span className="text-xs text-zinc-400">
                      {t("preview.trimHint")}
                    </span>
                  </>
                )}
              </div>
              {trimError && (
                <p className="flex items-center gap-2 text-xs text-red-300">
                  <Info size={14} className="shrink-0" />
                  {t("preview.trimError")}
                </p>
              )}
            </div>
            )}

            <Button
              variant="gradient"
              disabled={trimError}
              onClick={() => {
                // Remember the layout choice for this studio so the next
                // download from the same uploader defaults to it.
                if (isVideo && isVr) rememberLayout(info.uploader, vrLayout);
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
                  trim_start: trimOpen && !trimError ? trimStartSec : undefined,
                  trim_end: trimOpen && !trimError ? trimEndSec : undefined,
                  is_vr: isVideo ? isVr : undefined,
                  vr_layout: isVideo && isVr ? vrLayout : undefined,
                });
              }}
              className="h-12 w-full disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Download size={18} />
              {t("preview.download")}
              {estimatedSize && (
                <span className="text-white/70">· ≈ {estimatedSize}</span>
              )}
            </Button>
          </div>
        </div>
      </div>
    </GlassPanel>
  );
}
