import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  Clock3,
  Download,
  Glasses,
  Info,
  ListVideo,
  Music4,
  Search,
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
  PlaylistEntry,
  PlaylistInfo,
  VideoContainer,
  VRLayout,
} from "../../../types/download";
import {
  AUDIO_FORMATS,
  DEFAULT_AUDIO_FORMAT,
  DEFAULT_CONTAINER,
  formatDuration,
  VIDEO_CONTAINERS,
  VR_LAYOUTS,
} from "../formatOptions";
import { rememberLayout, rememberedLayout } from "../../../lib/vrPrefs";
import type { DownloadSelection } from "./PreviewCard";

interface PlaylistCardProps {
  playlist: PlaylistInfo;
  onDownload: (entries: PlaylistEntry[], selection: DownloadSelection) => void;
  busy?: boolean;
  defaultKind?: MediaKind;
  defaultQuality?: string;
  /** The analyzed URL — a YouTube Music playlist downloads audio only and hides
   * the video/audio selector (like the keyless music import). */
  sourceUrl?: string;
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

/** Parse a backend clock string ("M:SS" / "H:MM:SS") into seconds (0 if absent). */
function clockToSeconds(clock: string | null | undefined): number {
  if (!clock) return 0;
  const parts = clock.split(":").map((p) => Number.parseInt(p, 10));
  if (parts.some(Number.isNaN)) return 0;
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

/** YouTube's auto-generated music lists — radio mixes (RD…) and album playlists
 * (OLAK…) — are music-intent, so they default to an audio download. */
function isMusicPlaylist(playlist: PlaylistInfo): boolean {
  return /^(RD|OLAK)/.test(playlist.id);
}

/** Preview of an analyzed playlist: pick which items to download. */
export function PlaylistCard({
  playlist,
  onDownload,
  busy,
  defaultKind,
  defaultQuality,
  sourceUrl,
}: PlaylistCardProps) {
  const { t, i18n } = useTranslation();
  // A YouTube Music playlist is music: download audio only, no video/audio picker.
  const audioOnly = /music\.youtube\.com/i.test(sourceUrl ?? "");
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(playlist.entries.map((entry) => entry.url)),
  );
  // Re-analyzing a mutable playlist (radio mixes RD…, Watch Later) reuses this
  // component (the id key is unchanged), so reset the selection to all entries
  // whenever the entry list itself changes — React's "adjust state during
  // render" pattern (track the entries we've seen), not an effect.
  const [seenEntries, setSeenEntries] = useState(playlist.entries);
  if (seenEntries !== playlist.entries) {
    setSeenEntries(playlist.entries);
    setSelected(new Set(playlist.entries.map((entry) => entry.url)));
  }
  // Free-text filter over the entry list (titles); selection persists across it.
  const [filter, setFilter] = useState("");
  // The cover is a square whose side tracks the info column's own height, so its
  // bottom lines up with the format selector whatever the title/meta length. The
  // column is `self-start` so its measured height is the content's (not the row's).
  const infoColRef = useRef<HTMLDivElement>(null);
  const [coverSize, setCoverSize] = useState<number>();
  useEffect(() => {
    const el = infoColRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setCoverSize(el.offsetHeight));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  // Last checkbox toggled, for shift-click range selection (by id, so it survives
  // a changing filter view).
  const lastIdRef = useRef<string | null>(null);
  const [kind, setKind] = useState<MediaKind>(
    audioOnly || isMusicPlaylist(playlist) ? "audio" : (defaultKind ?? "video"),
  );
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
  // VR: tag the whole batch. Seeded from the playlist-level heuristic; a
  // remembered choice for this channel wins.
  const [isVr, setIsVr] = useState(playlist.is_vr);
  const [vrLayout, setVrLayout] = useState<VRLayout>(
    () => rememberedLayout(playlist.uploader) ?? playlist.vr_layout,
  );

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
  // Entries shown after the title filter (selection itself is unaffected by it).
  const query = filter.trim().toLowerCase();
  const visible = useMemo(
    () =>
      query
        ? playlist.entries.filter((e) => e.title.toLowerCase().includes(query))
        : playlist.entries,
    [playlist.entries, query],
  );
  const allVisibleSelected =
    visible.length > 0 && visible.every((e) => selected.has(e.url));
  // Total duration of the current selection (some flat entries may lack one).
  const selectedDuration = playlist.entries.reduce(
    (acc, entry) =>
      selected.has(entry.url) ? acc + clockToSeconds(entry.duration_string) : acc,
    0,
  );

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    const ids = visible.map((e) => e.url);
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) ids.forEach((id) => next.delete(id));
      else ids.forEach((id) => next.add(id));
      return next;
    });
  };

  // Click a row: a plain click toggles it; Shift+click extends/clears the range
  // from the last-clicked row (over the currently-visible list).
  const clickEntry = (entry: PlaylistEntry, index: number, shiftKey: boolean) => {
    const lastIdx = lastIdRef.current
      ? visible.findIndex((e) => e.url === lastIdRef.current)
      : -1;
    if (shiftKey && lastIdx >= 0 && lastIdx !== index) {
      const lo = Math.min(lastIdx, index);
      const hi = Math.max(lastIdx, index);
      const target = !selected.has(entry.url); // match the clicked item's new state
      setSelected((prev) => {
        const next = new Set(prev);
        for (let i = lo; i <= hi; i++) {
          if (target) next.add(visible[i].url);
          else next.delete(visible[i].url);
        }
        return next;
      });
    } else {
      toggle(entry.url);
    }
    lastIdRef.current = entry.url;
  };

  const handleDownload = () => {
    const chosen = playlist.entries.filter((entry) => selected.has(entry.url));
    if (chosen.length === 0) return;
    const tagVr = isVideo && playlist.is_vr && isVr;
    if (tagVr) rememberLayout(playlist.uploader, vrLayout);
    onDownload(chosen, {
      kind,
      quality: isVideo ? quality : undefined,
      container: isVideo ? container : undefined,
      audio_format: isVideo ? undefined : effectiveAudioFormat,
      embed_subs: showSubtitles ? embedSubs : undefined,
      subtitle_lang: showSubtitles && embedSubs ? subtitle : undefined,
      embed_chapters: isVideo ? embedChapters : undefined,
      audio_multistreams: showMultiAudio ? audioMultistreams : undefined,
      is_vr: tagVr ? true : undefined,
      vr_layout: tagVr ? vrLayout : undefined,
    });
  };

  return (
    <GlassPanel className="p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <span className="text-xs uppercase tracking-wider text-violet-400 flex items-center gap-2">
          <ListVideo size={14} />
          {t("playlist.label")}
        </span>
        <button
          type="button"
          onClick={toggleAll}
          className="text-xs text-zinc-400 hover:text-white transition"
        >
          {allVisibleSelected ? t("playlist.deselectAll") : t("playlist.selectAll")}
        </button>
      </div>

      <div className="flex flex-col gap-5 sm:flex-row">
        {/* Big square cover — same look as the music-import header. */}
        <div
          style={{ "--cover-h": `${coverSize ?? 180}px` } as CSSProperties}
          className="flex aspect-square w-full max-w-[200px] shrink-0 items-center justify-center self-center overflow-hidden rounded-2xl bg-gradient-to-br from-violet-500/40 to-blue-500/40 sm:aspect-auto sm:h-[var(--cover-h)] sm:w-[var(--cover-h)] sm:max-w-none sm:self-start">
          {playlist.thumbnail_url ? (
            <Thumbnail
              src={playlist.thumbnail_url}
              alt={playlist.title}
              className="h-full w-full object-cover"
              fallback={<ListVideo size={48} className="text-white/70" />}
            />
          ) : (
            <ListVideo size={48} className="text-white/70" />
          )}
        </div>

        {/* Info + controls */}
        <div ref={infoColRef} className="flex min-w-0 flex-1 flex-col gap-4 sm:self-start">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate text-2xl font-semibold leading-tight">
                {playlist.title}
              </h2>
              {playlist.is_vr && (
                <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-violet-500/15 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-violet-300 ring-1 ring-violet-500/30">
                  <Glasses size={14} />
                  {t("preview.vrBadge")}
                </span>
              )}
            </div>
            <p className="text-sm text-zinc-400 mt-1">
              {playlist.uploader ? `${playlist.uploader} • ` : ""}
              {audioOnly
                ? t("music.songs", { count: playlist.entry_count })
                : t("playlist.videos", { count: playlist.entry_count })}
              {playlist.truncated &&
                ` ${t("playlist.showingFirst", { count: playlist.entries.length })}`}
            </p>
          </div>

          {/* Controls */}
          <div className="flex flex-col gap-3">
            <div className="grid md:grid-cols-3 gap-3">
              {!audioOnly && (
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
              )}

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
                  className={`h-12 rounded-xl bg-surface border border-white/10 px-4 w-full text-sm ${
                    audioOnly ? "md:col-span-3" : "md:col-span-2"
                  }`}
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

            {/* VR — tag the whole batch (shown only when detected as immersive). */}
            {isVideo && playlist.is_vr && (
              <div className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-3">
                  <Toggle checked={isVr} onChange={setIsVr} label={t("preview.vr")} />
                  {isVr && (
                    <Select
                      ariaLabel={t("preview.vrLayout")}
                      value={vrLayout}
                      onChange={(v) => setVrLayout(v as VRLayout)}
                      options={VR_LAYOUTS.map((o) => ({
                        value: o.value,
                        label:
                          o.value === playlist.vr_layout
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

            <p className="flex items-center gap-1.5 text-xs text-zinc-400">
              <Clock3 size={12} className="shrink-0" />
              {selected.size === 0 || selectedDuration > 0
                ? t("playlist.selectionSummary", {
                    count: selected.size,
                    duration: formatDuration(selectedDuration, i18n.language),
                  })
                : t("playlist.selectionCount", { count: selected.size })}
            </p>

            <Button
              variant="gradient"
              onClick={handleDownload}
              disabled={busy || selected.size === 0}
              title={busy ? t("common.busy") : undefined}
              className="h-12 w-full disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Download size={18} />
              {t("playlist.download", { count: selected.size })}
            </Button>
          </div>
        </div>
      </div>

      {/* Entries — a filter (for long lists) + the selectable rows. */}
      {playlist.entries.length > 8 && (
        <div className="relative mt-5">
          <Search
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
          />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("playlist.filter")}
            aria-label={t("playlist.filter")}
            className="h-10 w-full rounded-xl border border-white/10 bg-surface pl-9 pr-3 text-sm outline-none focus:border-violet-500"
          />
        </div>
      )}

      <div
        className={`flex flex-col gap-1.5 max-h-[320px] overflow-auto pr-1 ${
          playlist.entries.length > 8 ? "mt-3" : "mt-5"
        }`}
      >
        {visible.length === 0 ? (
          <p className="py-6 text-center text-sm text-zinc-500">
            {t("playlist.noMatches")}
          </p>
        ) : (
          visible.map((entry, i) => (
            <div
              key={entry.url}
              role="checkbox"
              aria-checked={selected.has(entry.url)}
              tabIndex={0}
              onClick={(e) => clickEntry(entry, i, e.shiftKey)}
              onKeyDown={(e) => {
                if (e.key === " " || e.key === "Enter") {
                  e.preventDefault();
                  clickEntry(entry, i, e.shiftKey);
                }
              }}
              className="flex select-none items-center gap-3 rounded-xl border border-white/10 bg-surface/60 p-2.5 transition hover:bg-surface-hover cursor-pointer focus-visible:!outline-none focus-visible:bg-surface-hover focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-500/70"
            >
              <input
                type="checkbox"
                checked={selected.has(entry.url)}
                readOnly
                tabIndex={-1}
                aria-hidden="true"
                className="size-4 accent-violet-500 shrink-0 pointer-events-none"
              />
              <div className="w-14 h-9 rounded-md bg-gradient-to-br from-violet-500/40 to-blue-500/40 overflow-hidden flex items-center justify-center shrink-0">
                {entry.thumbnail_url ? (
                  <Thumbnail
                    src={entry.thumbnail_url}
                    alt={entry.title}
                    referer={entry.url}
                    loading="lazy"
                    className="h-full w-full object-cover"
                    fallback={
                      kind === "audio" ? <Music4 size={14} /> : <Video size={14} />
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
            </div>
          ))
        )}
      </div>
    </GlassPanel>
  );
}
