import { useState } from "react";
import { Clock3, Download, Info, ListVideo, Music4, Video } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { Button } from "../../../components/ui/Button";
import { Select } from "../../../components/ui/Select";
import { Thumbnail } from "../../../components/ui/Thumbnail";
import type {
  AudioFormat,
  MediaKind,
  PlaylistEntry,
  PlaylistInfo,
  VideoContainer,
} from "../../../types/download";
import {
  AUDIO_FORMATS,
  DEFAULT_AUDIO_FORMAT,
  DEFAULT_CONTAINER,
  VIDEO_CONTAINERS,
} from "../formatOptions";
import type { DownloadSelection } from "./PreviewCard";

interface PlaylistCardProps {
  playlist: PlaylistInfo;
  onDownload: (entries: PlaylistEntry[], selection: DownloadSelection) => void;
  busy?: boolean;
  defaultKind?: MediaKind;
  defaultQuality?: string;
}

// Playlist entries are listed flat (no per-item formats), so quality is a
// best-effort target shared by the whole batch.
const QUALITY_OPTIONS = ["1080p", "720p", "480p", "360p"];

// A flat playlist exposes no per-item subtitle info, so we offer a generic set
// of common languages applied to the whole batch (yt-dlp skips any that are
// missing for a given item).
const SUBTITLE_LANGS = ["en", "es"];
/** Sentinel value for the "no subtitles" entry in the language picker. */
const SUBS_NONE = "__none__";

/** Preview of an analyzed playlist: pick which items to download. */
export function PlaylistCard({
  playlist,
  onDownload,
  busy,
  defaultKind,
  defaultQuality,
}: PlaylistCardProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(playlist.entries.map((entry) => entry.id)),
  );
  const [kind, setKind] = useState<MediaKind>(defaultKind ?? "video");
  const [quality, setQuality] = useState<string>(
    defaultQuality && QUALITY_OPTIONS.includes(defaultQuality)
      ? defaultQuality
      : QUALITY_OPTIONS[0],
  );
  const [container, setContainer] = useState<VideoContainer>(DEFAULT_CONTAINER);
  const [audioFormat, setAudioFormat] = useState<AudioFormat>(
    DEFAULT_AUDIO_FORMAT,
  );
  const [subtitle, setSubtitle] = useState<string>(SUBS_NONE);
  const [embedChapters, setEmbedChapters] = useState(false);
  const [audioMultistreams, setAudioMultistreams] = useState(false);

  const isVideo = kind === "video";
  const embedSubs = subtitle !== SUBS_NONE;
  // Subtitles embed cleanly only into MKV, so offer the picker for MKV only.
  const showSubtitles = isVideo && container === "mkv";
  // A flat playlist has no per-item audio_langs, so gate the toggle on MKV only.
  const showMultiAudio = isVideo && container === "mkv";
  // Probed from the first entry (assumes a homogeneous playlist): gate FLAC/WAV
  // like a single video.
  const losslessAllowed = playlist.source_lossless;
  const effectiveAudioFormat: AudioFormat =
    !losslessAllowed &&
    AUDIO_FORMATS.find((o) => o.value === audioFormat)?.lossless
      ? DEFAULT_AUDIO_FORMAT
      : audioFormat;
  const showLosslessWarning = !isVideo && !losslessAllowed;
  const allSelected = selected.size === playlist.entries.length;

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected(
      allSelected ? new Set() : new Set(playlist.entries.map((e) => e.id)),
    );
  };

  const handleDownload = () => {
    const chosen = playlist.entries.filter((entry) => selected.has(entry.id));
    if (chosen.length === 0) return;
    onDownload(chosen, {
      kind,
      quality: isVideo ? quality : undefined,
      container: isVideo ? container : undefined,
      audio_format: isVideo ? undefined : effectiveAudioFormat,
      embed_subs: showSubtitles ? embedSubs : undefined,
      subtitle_lang: showSubtitles && embedSubs ? subtitle : undefined,
      embed_chapters: isVideo ? embedChapters : undefined,
      audio_multistreams: showMultiAudio ? audioMultistreams : undefined,
    });
  };

  return (
    <GlassPanel className="p-5">
      <div className="flex items-center justify-between gap-3 mb-1">
        <span className="text-xs uppercase tracking-wider text-violet-400 flex items-center gap-2">
          <ListVideo size={14} />
          {t("playlist.label")}
        </span>
        <button
          type="button"
          onClick={toggleAll}
          className="text-xs text-zinc-400 hover:text-white transition"
        >
          {allSelected ? t("playlist.deselectAll") : t("playlist.selectAll")}
        </button>
      </div>

      <h2 className="text-xl font-semibold truncate">{playlist.title}</h2>
      <p className="text-sm text-zinc-400 mt-1">
        {playlist.uploader ? `${playlist.uploader} • ` : ""}
        {t("playlist.videos", { count: playlist.entry_count })}
        {playlist.truncated &&
          ` ${t("playlist.showingFirst", { count: playlist.entries.length })}`}
      </p>

      {/* Controls */}
      <div className="mt-4 flex flex-col gap-3">
        <div className="grid md:grid-cols-3 gap-3">
          <Select
            ariaLabel={t("preview.format")}
            value={kind}
            onChange={(v) => setKind(v as MediaKind)}
            options={[
              { value: "video", label: t("preview.video") },
              { value: "audio", label: t("preview.audio") },
            ]}
            className="h-12 rounded-xl bg-surface border border-white/10 px-4 w-full text-sm"
          />

          {isVideo ? (
            <>
              <Select
                ariaLabel={t("preview.quality")}
                value={quality}
                onChange={setQuality}
                options={QUALITY_OPTIONS.map((option) => ({
                  value: option,
                  label: option,
                }))}
                className="h-12 rounded-xl bg-surface border border-white/10 px-4 w-full text-sm"
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

        {/* Subtitles + chapters, applied to the whole batch. Video-only. */}
        {isVideo && (
          <div className="flex flex-wrap items-center gap-3">
            {showSubtitles && (
              <Select
                ariaLabel={t("preview.subtitles")}
                value={subtitle}
                onChange={setSubtitle}
                options={[
                  { value: SUBS_NONE, label: t("preview.subtitlesNone") },
                  { value: "all", label: t("preview.subtitlesAll") },
                  ...SUBTITLE_LANGS.map((code) => ({
                    value: code,
                    label: code.toUpperCase(),
                  })),
                ]}
                className="h-11 min-w-[160px] flex-1 rounded-xl bg-surface border border-white/10 px-4 text-sm"
              />
            )}
            <label className="flex h-11 cursor-pointer items-center gap-2.5 rounded-xl border border-white/10 bg-surface px-4 text-sm">
              <input
                type="checkbox"
                checked={embedChapters}
                onChange={(e) => setEmbedChapters(e.target.checked)}
                className="size-4 accent-violet-500 shrink-0"
              />
              {t("preview.chapters")}
            </label>
            {showMultiAudio && (
              <label className="flex h-11 cursor-pointer items-center gap-2.5 rounded-xl border border-white/10 bg-surface px-4 text-sm">
                <input
                  type="checkbox"
                  checked={audioMultistreams}
                  onChange={(e) => setAudioMultistreams(e.target.checked)}
                  className="size-4 accent-violet-500 shrink-0"
                />
                {t("preview.multiAudio")}
              </label>
            )}
          </div>
        )}

        <Button
          variant="gradient"
          onClick={handleDownload}
          disabled={busy || selected.size === 0}
          className="h-12 w-full disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Download size={18} />
          {t("playlist.download", { count: selected.size })}
        </Button>
      </div>

      {/* Entries */}
      <div className="flex flex-col gap-1.5 mt-4 max-h-[320px] overflow-auto pr-1">
        {playlist.entries.map((entry) => (
          <label
            key={entry.id}
            className="flex items-center gap-3 rounded-xl border border-white/10 bg-surface/60 hover:bg-surface-hover transition p-2.5 cursor-pointer"
          >
            <input
              type="checkbox"
              checked={selected.has(entry.id)}
              onChange={() => toggle(entry.id)}
              className="size-4 accent-violet-500 shrink-0"
            />
            <div className="w-14 h-9 rounded-md bg-gradient-to-br from-violet-500/40 to-blue-500/40 overflow-hidden flex items-center justify-center shrink-0">
              {entry.thumbnail_url ? (
                <Thumbnail
                  src={entry.thumbnail_url}
                  alt={entry.title}
                  referer={entry.url}
                  className="h-full w-full object-cover"
                  fallback={
                    kind === "audio" ? (
                      <Music4 size={14} />
                    ) : (
                      <Video size={14} />
                    )
                  }
                />
              ) : kind === "audio" ? (
                <Music4 size={14} />
              ) : (
                <Video size={14} />
              )}
            </div>
            <span className="flex-1 min-w-0 text-sm truncate">{entry.title}</span>
            {entry.duration_string && (
              <span className="flex items-center gap-1 text-xs text-zinc-400 shrink-0">
                <Clock3 size={12} />
                {entry.duration_string}
              </span>
            )}
          </label>
        ))}
      </div>
    </GlassPanel>
  );
}
