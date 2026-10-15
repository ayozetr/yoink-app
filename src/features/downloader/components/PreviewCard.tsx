import { memo, useMemo, useState } from "react";
import {
  AlertCircle,
  BookmarkPlus,
  ChevronDown,
  Download,
  Glasses,
  Info,
  ListPlus,
  SlidersHorizontal,
  Video,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { Button } from "../../../components/ui/Button";
import { Select } from "../../../components/ui/Select";
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
import {
  loadPresets,
  newPresetId,
  savePresets,
  type DownloadPreset,
} from "../../../lib/presets";

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
  /** Estimated final size in bytes (for the backend pre-flight disk check). */
  estimated_size?: number;
  /** Override the output filename's title (single wrapped story/post item). */
  output_title?: string;
}

/** Sentinel value for the "no subtitles" entry in the language picker. */
const SUBS_NONE = "__none__";

/** Parse "ss", "mm:ss" or "hh:mm:ss" into seconds (undefined if blank/invalid). */
function parseTime(value: string): number | undefined {
  const t = value.trim();
  // Digits in 1–3 groups separated by ':' or '.': "ss", "mm:ss", "hh:mm:ss".
  // A '.' is accepted as the separator too — this is a clock field, so a typed
  // "12.20" means 12:20 (people mistype the colon). A regex avoids Number()
  // coercion accepting "1:", "::", "0x10", "1e3", etc.
  if (!/^\d+([:.]\d+){0,2}$/.test(t)) return undefined;
  return t.split(/[.:]/).reduce((acc, p) => acc * 60 + Number(p), 0);
}

interface PreviewCardProps {
  info: VideoInfo;
  onDownload: (selection: DownloadSelection) => void;
  /** Add the analyzed source to the download queue (Inicio → Cola). */
  onAddToQueue?: () => void;
  defaultKind?: MediaKind;
  defaultQuality?: string;
  /** Seed the subtitle picker to "embed all" by default (persisted setting). */
  defaultEmbedSubs?: boolean;
  /** Seed the chapters toggle on by default (persisted setting). */
  defaultEmbedChapters?: boolean;
  /** Disable the Download button while another engine (the queue) is busy. */
  locked?: boolean;
}

// Pill-styled compact select used for the primary format controls.
const PILL_SELECT =
  "h-9 rounded-full border border-line/10 bg-surface-2 px-4 text-sm";

// Mini uppercase label for an advanced-options line (Formato / Procesado / …).
const ADV_LABEL =
  "w-20 shrink-0 text-[11px] font-semibold uppercase tracking-[0.14em] text-fg-faint";

/** Compact, flat on/off switch with its label inline — used in the advanced row. */
function AdvSwitch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-2 text-sm text-fg"
    >
      <span
        className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${checked ? "bg-accent" : "bg-surface-hover"}`}
      >
        <span
          className={`inline-block size-3.5 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-[18px]" : "translate-x-1"}`}
        />
      </span>
      {label}
    </button>
  );
}

/** Preview of the analyzed media: thumbnail, info and download controls. */
export const PreviewCard = memo(function PreviewCard({
  info,
  onDownload,
  onAddToQueue,
  defaultKind,
  defaultQuality,
  defaultEmbedSubs,
  defaultEmbedChapters,
  locked = false,
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
  // Subtitles are opt-in, but the user can persist an "embed by default" choice
  // that seeds the picker to "all" (it only takes effect once a container that
  // can carry subtitles, i.e. MKV, is selected).
  const [subtitle, setSubtitle] = useState<string>(
    defaultEmbedSubs ? "all" : SUBS_NONE,
  );
  const [embedChapters, setEmbedChapters] = useState(
    defaultEmbedChapters ?? false,
  );
  const [audioMultistreams, setAudioMultistreams] = useState(false);
  const [trimStart, setTrimStart] = useState("");
  const [trimEnd, setTrimEnd] = useState("");
  // Secondary controls (presets/subs/chapters/multi-audio/VR/trim) collapse under
  // an "Advanced options" toggle so the pills + Download stay simple and above the
  // fold. Auto-opened when VR is detected, since that needs the user to confirm.
  const [advancedOpen, setAdvancedOpen] = useState(info.is_vr);
  // VR tagging: seed from the backend's heuristic detection; the user can
  // toggle it and pick the stereo/projection layout. A previously remembered
  // choice for this uploader wins over the heuristic's guess.
  const [isVr, setIsVr] = useState(info.is_vr);
  const [vrLayout, setVrLayout] = useState<VRLayout>(
    () => rememberedLayout(info.uploader) ?? info.vr_layout,
  );
  // Saved format presets (local), applied to the selectors in one click.
  const [presets, setPresets] = useState<DownloadPreset[]>(loadPresets);
  const [namingPreset, setNamingPreset] = useState(false);
  const [presetName, setPresetName] = useState("");

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
  const estimatedBytes = useMemo(
    () =>
      estimatedSizeBytes(
        info,
        kind,
        isVideo ? quality : undefined,
        isVideo ? undefined : effectiveAudioFormat,
      ),
    [info, kind, isVideo, quality, effectiveAudioFormat],
  );
  const estimatedSize = formatBytes(estimatedBytes);

  const trimStartSec = parseTime(trimStart);
  const trimEndSec = parseTime(trimEnd);
  // Invalid when a given end isn't past the (effective) start — also catches a
  // lone end of 0, which would otherwise be an empty (0,0) range. Computed from
  // the values, not panel state, so the range is validated even when collapsed.
  const trimError = trimEndSec != null && trimEndSec <= (trimStartSec ?? 0);
  // A non-empty field that doesn't parse (e.g. "1a", "1:2:3:4") would otherwise be
  // silently ignored — the clip would run to the end. Flag it so the field turns
  // red and the Download button is blocked, instead of downloading the wrong range.
  const trimStartInvalid = trimStart.trim() !== "" && trimStartSec === undefined;
  const trimEndInvalid = trimEnd.trim() !== "" && trimEndSec === undefined;
  const trimInvalid = trimStartInvalid || trimEndInvalid;

  // Apply a saved preset to the selectors (best-effort: quality/kind are only
  // set when this media can offer them).
  const applyPreset = (p: DownloadPreset) => {
    if (kinds.some((k) => k.kind === p.kind)) setKind(p.kind);
    if (p.quality && qualities.includes(p.quality)) setQuality(p.quality);
    if (p.container) setContainer(p.container);
    if (p.audioFormat) setAudioFormat(p.audioFormat);
    setSubtitle(p.embedSubs ? "all" : SUBS_NONE);
    setEmbedChapters(!!p.embedChapters);
  };

  const saveCurrentPreset = () => {
    const name = presetName.trim();
    if (!name) return;
    const next = [
      ...presets,
      {
        id: newPresetId(),
        name,
        kind,
        quality: isVideo ? quality : undefined,
        container: isVideo ? container : undefined,
        audioFormat: isVideo ? undefined : audioFormat,
        embedSubs,
        embedChapters,
      },
    ];
    setPresets(next);
    savePresets(next);
    setNamingPreset(false);
    setPresetName("");
  };

  const deletePreset = (id: string) => {
    const next = presets.filter((p) => p.id !== id);
    setPresets(next);
    savePresets(next);
  };

  const handleDownload = () => {
    // Remember the layout choice for this studio so the next download from the
    // same uploader defaults to it.
    if (isVideo && isVr) rememberLayout(info.uploader, vrLayout);
    onDownload({
      kind,
      quality: isVideo ? quality : undefined,
      container: isVideo ? container : undefined,
      audio_format: isVideo ? undefined : effectiveAudioFormat,
      embed_subs: showSubtitles ? embedSubs : undefined,
      subtitle_lang: showSubtitles && embedSubs ? subtitle : undefined,
      embed_chapters: isVideo ? embedChapters : undefined,
      audio_multistreams: showMultiAudio ? audioMultistreams : undefined,
      trim_start: !trimError && !trimInvalid ? trimStartSec : undefined,
      trim_end: !trimError && !trimInvalid ? trimEndSec : undefined,
      is_vr: isVideo ? isVr : undefined,
      vr_layout: isVideo && isVr ? vrLayout : undefined,
      // Only when not trimming — the estimate is for the full video, so a small
      // clip of a big video shouldn't be blocked on size.
      estimated_size:
        trimStartSec == null && trimEndSec == null
          ? (estimatedBytes ?? undefined)
          : undefined,
    });
  };

  return (
    <GlassPanel className="p-5">
      <div className="flex flex-col gap-4">
        {/* Media row — a small, aspect-safe thumbnail (object-contain shows the
            whole image: 16:9 video, square covers and vertical reels alike)
            beside the title, which carries the visual weight. */}
        <div className="flex items-center gap-4">
          <div className="relative flex aspect-video w-32 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-surface-2 sm:w-40">
            {info.thumbnail_url ? (
              <Thumbnail
                src={info.thumbnail_url}
                alt={info.title}
                referer={info.webpage_url}
                className="absolute inset-0 h-full w-full object-contain"
                fallback={<Video className="size-9 text-fg-faint" />}
              />
            ) : (
              <Video className="size-9 text-fg-faint" />
            )}
            {info.duration_string && (
              <span className="absolute bottom-1 right-1 rounded bg-black/75 px-1.5 py-0.5 text-[10px] font-medium text-white">
                {info.duration_string}
              </span>
            )}
          </div>

          <div className="min-w-0 flex-1">
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-fg-faint">
              {t("preview.label")}
            </span>
            <h2 className="mt-1.5 font-display text-2xl font-normal leading-[1.14] text-balance">
              {info.title}
            </h2>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-fg-dim">
              {info.uploader && <span className="truncate">{info.uploader}</span>}
              {info.uploader && isVideo && qualities.length > 0 && (
                <span className="text-fg-faint">•</span>
              )}
              {isVideo && qualities.length > 0 && (
                <span>{t("preview.qualityAvailable", { quality: qualities[0] })}</span>
              )}
              {info.is_vr && (
                <span className="flex items-center gap-1.5 rounded-full bg-accent/15 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-accent-soft ring-1 ring-accent/30">
                  <Glasses size={14} />
                  {t("preview.vrBadge")}
                </span>
              )}
            </div>
          </div>
        </div>

          {!info.has_audio && (
            <div className="flex items-center gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-300 ring-1 ring-amber-500/25">
              <AlertCircle size={16} className="shrink-0" />
              {t("preview.noAudio")}
            </div>
          )}

          {/* Actions — the one choice (video/audio) and the download, together in
              one row; quality/format and the rest live under "Opciones" below. */}
          <div className="flex flex-wrap items-center gap-3">
            {kinds.length > 1 && (
              <div className="inline-flex gap-1 rounded-full border border-line/10 bg-surface-2 p-1">
                {kinds.map((option) => (
                  <button
                    key={option.kind}
                    type="button"
                    onClick={() => setKind(option.kind)}
                    aria-pressed={kind === option.kind}
                    className={`rounded-full px-5 py-2 text-sm font-medium transition ${
                      kind === option.kind
                        ? "bg-accent text-white"
                        : "text-fg-dim hover:text-fg"
                    }`}
                  >
                    {option.kind === "video"
                      ? t("preview.video")
                      : t("preview.audio")}
                  </button>
                ))}
              </div>
            )}

            <Button
              variant="gradient"
              disabled={locked || trimError || trimInvalid}
              title={locked ? t("common.busy") : undefined}
              onClick={handleDownload}
              className="h-12 min-w-[200px] flex-1 text-base disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Download size={20} />
              {t("preview.download")}
              <span className="font-normal text-white/75">
                {"· "}
                {isVideo
                  ? `${qualities.length > 0 ? quality : t("preview.bestQuality")} · ${container.toUpperCase()}`
                  : effectiveAudioFormat.toUpperCase()}
                {estimatedSize ? ` · ≈ ${estimatedSize}` : ""}
              </span>
            </Button>
          </div>

          {showLosslessWarning && (
            <p className="flex items-center gap-2 text-xs text-fg-dim">
              <Info size={14} className="shrink-0" />
              {t("preview.losslessWarning")}
            </p>
          )}
          {!isVideo && effectiveAudioFormat === "wav" && (
            <p className="flex items-center gap-2 text-xs text-fg-dim">
              <Info size={14} className="shrink-0" />
              {t("preview.wavCoverWarning")}
            </p>
          )}

          {/* Quiet secondary row: queue it, or reveal the rest. */}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            {onAddToQueue && (
              <button
                type="button"
                onClick={onAddToQueue}
                disabled={locked}
                className="flex items-center gap-2 text-sm text-fg-dim transition hover:text-fg disabled:opacity-50"
              >
                <ListPlus size={16} />
                {t("preview.addToQueue")}
              </button>
            )}
            <button
              type="button"
              onClick={() => setAdvancedOpen((v) => !v)}
              aria-expanded={advancedOpen}
              className="flex items-center gap-2 text-sm text-fg-dim transition hover:text-fg"
            >
              <SlidersHorizontal size={15} />
              {t("preview.advanced")}
              {(trimError || trimInvalid) && !advancedOpen && (
                <AlertCircle size={14} className="text-red-400" />
              )}
              <ChevronDown
                size={15}
                className={`transition-transform ${advancedOpen ? "rotate-180" : ""}`}
              />
            </button>
          </div>

          {advancedOpen && (
            <div className="flex flex-col gap-5 border-t border-line/10 pt-4">
              {/* Formato */}
              <div className="flex flex-wrap items-center gap-2.5">
                <span className={ADV_LABEL}>{t("preview.format")}</span>
                {isVideo ? (
                  <>
                    <Select
                      ariaLabel={t("preview.quality")}
                      value={qualities.length > 0 ? quality : "__best__"}
                      onChange={setQuality}
                      disabled={qualities.length === 0}
                      options={
                        qualities.length > 0
                          ? qualities.map((o) => ({ value: o, label: o }))
                          : [{ value: "__best__", label: t("preview.bestQuality") }]
                      }
                      className={`${PILL_SELECT} disabled:opacity-50 disabled:cursor-not-allowed`}
                    />
                    <Select
                      ariaLabel={t("preview.container")}
                      value={container}
                      onChange={(v) => setContainer(v as VideoContainer)}
                      options={VIDEO_CONTAINERS}
                      className={PILL_SELECT}
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
                    className={PILL_SELECT}
                  />
                )}
              </div>

              {/* Presets — apply with a click, or save the current selection. */}
              <div className="flex flex-wrap items-center gap-2.5">
                <span className={ADV_LABEL}>{t("preset.plural")}</span>
                {presets.map((p) => (
                  <span
                    key={p.id}
                    className="flex items-center gap-1 rounded-lg border border-line/10 bg-surface py-1 pl-2.5 pr-1 text-xs"
                  >
                    <button
                      type="button"
                      onClick={() => applyPreset(p)}
                      className="text-fg transition hover:text-accent-soft"
                    >
                      {p.name}
                    </button>
                    <button
                      type="button"
                      onClick={() => deletePreset(p.id)}
                      aria-label={t("preset.delete")}
                      className="text-fg-faint transition hover:text-red-400"
                    >
                      <X size={12} />
                    </button>
                  </span>
                ))}
                {namingPreset ? (
                  <span className="flex items-center gap-1">
                    <input
                      autoFocus
                      type="text"
                      value={presetName}
                      onChange={(e) => setPresetName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveCurrentPreset();
                        if (e.key === "Escape") {
                          setNamingPreset(false);
                          setPresetName("");
                        }
                      }}
                      placeholder={t("preset.namePlaceholder")}
                      aria-label={t("preset.namePlaceholder")}
                      className="h-7 w-32 rounded-lg border border-line/10 bg-surface px-2 text-xs outline-none focus:border-accent"
                    />
                    <button
                      type="button"
                      onClick={saveCurrentPreset}
                      disabled={!presetName.trim()}
                      className="rounded-lg border border-accent/40 bg-accent/15 px-2 py-1 text-xs text-fg transition hover:bg-accent/25 disabled:opacity-40"
                    >
                      {t("preset.save")}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setNamingPreset(false);
                        setPresetName("");
                      }}
                      aria-label={t("preset.cancel")}
                      className="text-fg-faint transition hover:text-fg"
                    >
                      <X size={14} />
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setNamingPreset(true);
                      setPresetName("");
                    }}
                    className="flex items-center gap-1 rounded-lg border border-dashed border-line/15 px-2.5 py-1 text-xs text-fg-dim transition hover:border-line/20 hover:text-fg"
                  >
                    <BookmarkPlus size={13} />
                    {t("preset.saveCurrent")}
                  </button>
                )}
              </div>

              {/* Procesado — VR / subtitles / chapters / multi-audio (video). */}
              {isVideo &&
                (info.is_vr ||
                  showSubtitles ||
                  info.has_chapters ||
                  showMultiAudio) && (
                  <div className="flex flex-wrap items-start gap-x-5 gap-y-3">
                    <span className={`${ADV_LABEL} pt-1.5`}>
                      {t("settings.secProcessing")}
                    </span>
                    <div className="flex flex-1 flex-wrap items-center gap-x-5 gap-y-3">
                      {info.is_vr && (
                        <>
                          <AdvSwitch
                            checked={isVr}
                            onChange={setIsVr}
                            label={t("preview.vr")}
                          />
                          {isVr && (
                            <Select
                              ariaLabel={t("preview.vrLayout")}
                              value={vrLayout}
                              onChange={(v) => setVrLayout(v as VRLayout)}
                              options={VR_LAYOUTS.map((o) => ({
                                value: o.value,
                                label:
                                  o.value === info.vr_layout
                                    ? `${o.label} (${t("preview.vrDetected")})`
                                    : o.label,
                              }))}
                              className={PILL_SELECT}
                            />
                          )}
                        </>
                      )}
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
                          className={PILL_SELECT}
                        />
                      )}
                      {info.has_chapters && (
                        <AdvSwitch
                          checked={embedChapters}
                          onChange={setEmbedChapters}
                          label={t("preview.chapters")}
                        />
                      )}
                      {showMultiAudio && (
                        <AdvSwitch
                          checked={audioMultistreams}
                          onChange={setAudioMultistreams}
                          label={t("preview.multiAudio")}
                        />
                      )}
                      {isVr && (
                        <p className="flex w-full items-center gap-2 text-xs text-fg-faint">
                          <Info size={14} className="shrink-0" />
                          {t("preview.vrHint")}
                        </p>
                      )}
                    </div>
                  </div>
                )}

              {/* Recorte */}
              <div className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className={ADV_LABEL}>{t("preview.trim")}</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    aria-label={t("preview.trimStart")}
                    placeholder={t("preview.trimStart")}
                    value={trimStart}
                    onChange={(e) => setTrimStart(e.target.value)}
                    className={`h-9 w-32 rounded-full border bg-surface-2 px-4 text-sm outline-none focus:border-accent ${
                      trimStartInvalid ? "border-red-500/60" : "border-line/10"
                    }`}
                  />
                  <span className="text-fg-faint">→</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    aria-label={t("preview.trimEnd")}
                    placeholder={t("preview.trimEnd")}
                    value={trimEnd}
                    onChange={(e) => setTrimEnd(e.target.value)}
                    className={`h-9 w-32 rounded-full border bg-surface-2 px-4 text-sm outline-none focus:border-accent ${
                      trimEndInvalid ? "border-red-500/60" : "border-line/10"
                    }`}
                  />
                </div>
                {(trimError || trimInvalid) && (
                  <p className="flex items-center gap-2 text-xs text-red-300">
                    <Info size={14} className="shrink-0" />
                    {trimInvalid
                      ? t("preview.trimInvalid")
                      : t("preview.trimError")}
                  </p>
                )}
              </div>
            </div>
          )}

      </div>
    </GlassPanel>
  );
});
