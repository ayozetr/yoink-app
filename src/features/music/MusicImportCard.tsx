import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Loader2,
  Music4,
  SkipForward,
  Square,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { Button } from "../../components/ui/Button";
import { Select } from "../../components/ui/Select";
import { ProgressBar } from "../../components/ui/ProgressBar";
import { Thumbnail } from "../../components/ui/Thumbnail";
import { applyAudioTags, matchMusic } from "../../lib/api";
import { startDownload, type DownloadHandle } from "../../lib/downloadSocket";
import {
  acquireDownloadLock,
  releaseDownloadLock,
  useDownloadLock,
} from "../../lib/downloadLock";
import { AUDIO_FORMATS, DEFAULT_AUDIO_FORMAT } from "../downloader/formatOptions";
import type { AudioFormat, DownloadProgressEvent } from "../../types/download";
import { MUSIC_SOURCE_NAMES, type MusicImportInfo } from "../../types/music";

type RowStatus = "pending" | "active" | "done" | "error" | "skipped";

interface MusicImportCardProps {
  info: MusicImportInfo;
  defaultAudioFormat?: AudioFormat;
  /** Refresh history/stats as tracks complete. */
  onDownloadFinished?: () => void;
}

/** Import a music-service URL: resolve → match each track on YouTube → download + tag.
 *
 * The audio is never taken from the source — only its metadata. Each track is
 * matched to a YouTube video (spotDL-ported ranking), downloaded as audio, and
 * tagged with the exact source fields. Runs sequentially like the queue. */
export function MusicImportCard({
  info,
  defaultAudioFormat,
  onDownloadFinished,
}: MusicImportCardProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(info.tracks.map((_, i) => i)),
  );
  const [audioFormat, setAudioFormat] = useState<AudioFormat>(
    // FLAC/WAV would upscale a lossy YouTube source, so cap to a lossy default.
    defaultAudioFormat && !["flac", "wav"].includes(defaultAudioFormat)
      ? defaultAudioFormat
      : DEFAULT_AUDIO_FORMAT,
  );
  const [rows, setRows] = useState<Record<number, RowStatus>>({});
  const [running, setRunning] = useState(false);
  const [runTotal, setRunTotal] = useState(0);
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  // The full live progress event (percent + speed + ETA + status) so the bar
  // shows the same detail as a normal download, not just a bare percentage.
  const [progress, setProgress] = useState<DownloadProgressEvent | null>(null);

  const runningRef = useRef(false);
  const handleRef = useRef<DownloadHandle | null>(null);
  const orderRef = useRef<number[]>([]);
  const posRef = useRef(0);
  const fmtRef = useRef(audioFormat);
  useEffect(() => {
    fmtRef.current = audioFormat;
  });
  // Shared download lock: another engine downloading blocks Start here so the
  // music import can't run a second concurrent download.
  const lockOwner = useDownloadLock();
  const lockedByOther = lockOwner !== null && lockOwner !== "music";

  // Cancel a live socket + free the lock if the card unmounts mid-import (it is
  // remounted per source URL via its key, so this fires on every new analysis).
  // Clearing runningRef is essential: the import loop has awaits (matchMusic /
  // applyAudioTags) whose continuations outlive the socket and would otherwise
  // keep spawning lock-free downloads after unmount — every survivor is gated by
  // a runningRef check, so flipping it false stops them.
  useEffect(
    () => () => {
      runningRef.current = false;
      handleRef.current?.cancel();
      releaseDownloadLock("music");
    },
    [],
  );

  const allSelected = selected.size === info.tracks.length;
  const setRow = (i: number, status: RowStatus) =>
    setRows((prev) => ({ ...prev, [i]: status }));

  const toggle = (i: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(info.tracks.map((_, i) => i)));

  const finish = () => {
    runningRef.current = false;
    releaseDownloadLock("music");
    setRunning(false);
    setActiveIdx(null);
    setProgress(null);
    handleRef.current = null;
    // A track left mid-flight (e.g. Stop) would otherwise keep its row spinning
    // forever — drop any "active" status back to neutral.
    setRows((prev) => {
      const next: Record<number, RowStatus> = {};
      for (const [k, v] of Object.entries(prev)) {
        if (v !== "active") next[Number(k)] = v;
      }
      return next;
    });
    onDownloadFinished?.();
  };

  const advance = () => {
    posRef.current += 1;
    onDownloadFinished?.();
    if (runningRef.current) void processNext();
  };

  const processNext = async () => {
    if (!runningRef.current) return;
    if (posRef.current >= orderRef.current.length) {
      finish();
      return;
    }
    const idx = orderRef.current[posRef.current];
    const track = info.tracks[idx];
    setActiveIdx(idx);
    setProgress(null);
    setRow(idx, "active");

    // 1. Find the best YouTube match for this track.
    let url: string | null;
    try {
      url = await matchMusic(track);
    } catch {
      url = null;
    }
    if (!runningRef.current) return;
    if (!url) {
      setRow(idx, "skipped"); // nothing cleared the match thresholds
      advance();
      return;
    }

    // 2. Download it as audio, then 3. tag it with the source metadata.
    let settled = false;
    handleRef.current = startDownload(
      { url, kind: "audio", audio_format: fmtRef.current },
      {
        onEvent: (event) => {
          if (settled) return;
          if (event.type === "progress") {
            setProgress(event);
            return;
          }
          settled = true;
          handleRef.current = null;
          if (event.type === "completed") {
            void applyAudioTags({
              path: event.filepath,
              title: track.title,
              artist: track.artists,
              album: track.album,
              year: track.year,
              cover_url: track.cover_url,
            })
              .catch(() => undefined) // tagging is best-effort
              .finally(() => {
                setRow(idx, "done");
                advance();
              });
          } else {
            setRow(idx, "error");
            advance();
          }
        },
        onClose: () => {
          if (settled) return;
          settled = true;
          handleRef.current = null;
          setRow(idx, "error");
          advance();
        },
      },
    );
  };

  const start = () => {
    if (runningRef.current || selected.size === 0) return;
    // Refuse to start while another engine downloads (the button is also
    // disabled; this guards the render-vs-click race).
    if (!acquireDownloadLock("music")) return;
    orderRef.current = [...selected].sort((a, b) => a - b);
    posRef.current = 0;
    setRows({});
    setRunTotal(orderRef.current.length);
    runningRef.current = true;
    setRunning(true);
    void processNext();
  };

  const stop = () => {
    runningRef.current = false;
    handleRef.current?.cancel();
    finish();
  };

  const fmtMs = (ms: number | null) => {
    if (!ms) return "";
    const s = Math.round(ms / 1000);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };

  const doneCount = Object.values(rows).filter((s) => s === "done").length;

  // Mirror DownloadProgressCard's live readout (label + percent + speed/ETA) so
  // an imported track shows the same detail as any other download.
  const percent = progress?.percent ?? 0;
  const isProcessing = progress?.status === "processing";
  const progressLabel = isProcessing
    ? t("progress.processing")
    : t("progress.downloading");
  const progressDetail = isProcessing
    ? t("progress.merging")
    : [progress?.speed, progress?.eta && `${t("progress.eta")} ${progress.eta}`]
        .filter(Boolean)
        .join(" • ");

  // One unified card: a big square cover + source metadata header (like a
  // preview) for everything, with the track selection list below for
  // albums/playlists.
  const isSingle = info.type === "track";
  const first = info.tracks[0];
  const status0 = rows[0];
  // Header artist line: playlist owner / album artist / track artist.
  const headerArtist = info.subtitle ?? "";
  const headerMeta = isSingle
    ? [first?.album, first?.year, fmtMs(first?.duration_ms ?? null)]
        .filter(Boolean)
        .join(" · ")
    : `${t("music.songs", { count: info.tracks.length })}${
        info.truncated ? ` ${t("music.truncated")}` : ""
      }`;

  return (
    <GlassPanel className="p-5">
      <span className="flex items-center gap-2 text-xs uppercase tracking-wider text-violet-400">
        <Music4 size={14} />
        {t("music.label", { source: MUSIC_SOURCE_NAMES[info.source] })}
      </span>

      <div className="mt-3 flex flex-col gap-5 sm:flex-row">
        {/* Square cover */}
        <div className="flex aspect-square w-full max-w-[200px] shrink-0 items-center justify-center self-center overflow-hidden rounded-2xl bg-gradient-to-br from-violet-600/40 to-blue-600/40 sm:w-[180px] sm:self-start">
          {info.cover_url ? (
            <Thumbnail
              src={info.cover_url}
              alt={info.name}
              className="h-full w-full object-cover"
              fallback={<Music4 size={48} className="text-white/70" />}
            />
          ) : (
            <Music4 size={48} className="text-white/70" />
          )}
        </div>

        {/* Info + controls */}
        <div className="flex min-w-0 flex-1 flex-col justify-between gap-4">
          <div>
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-2xl font-semibold leading-tight">{info.name}</h2>
              {!isSingle && !running && (
                <button
                  type="button"
                  onClick={toggleAll}
                  className="mt-1 shrink-0 text-xs text-zinc-400 hover:text-white transition"
                >
                  {allSelected ? t("playlist.deselectAll") : t("playlist.selectAll")}
                </button>
              )}
            </div>
            {headerArtist && (
              <p className="mt-1 truncate text-zinc-300">{headerArtist}</p>
            )}
            {headerMeta && <p className="mt-1 text-sm text-zinc-400">{headerMeta}</p>}
            <p className="mt-3 flex items-center gap-2 text-xs text-zinc-400">
              <AlertCircle size={14} className="shrink-0" />
              {t("music.hint")}
            </p>
          </div>

          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <Select
                ariaLabel={t("preview.audioFormat")}
                value={audioFormat}
                onChange={(v) => setAudioFormat(v as AudioFormat)}
                options={AUDIO_FORMATS.filter((o) => !o.lossless).map((o) => ({
                  value: o.value,
                  label: o.label,
                }))}
                className="h-12 min-w-[140px] rounded-xl bg-surface border border-white/10 px-4 text-sm"
              />
              {running ? (
                <button
                  type="button"
                  onClick={stop}
                  className="h-12 px-6 flex items-center gap-2 rounded-2xl border border-white/10 bg-surface text-sm transition hover:bg-surface-hover"
                >
                  <Square size={16} />
                  {t("queue.stop")}
                </button>
              ) : isSingle && status0 === "done" ? (
                <span className="flex h-12 items-center gap-2 text-sm text-violet-300">
                  <CheckCircle2 size={18} />
                  {t("music.done")}
                </span>
              ) : (
                <Button
                  variant="gradient"
                  onClick={start}
                  disabled={selected.size === 0 || lockedByOther}
                  title={lockedByOther ? t("common.busy") : undefined}
                  className="h-12 flex-1 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Download size={18} />
                  {isSingle
                    ? t("music.download")
                    : t("music.import", { count: selected.size })}
                </Button>
              )}
            </div>

            {running && (
              <div className="flex flex-col gap-1.5">
                {!isSingle && (
                  <div className="flex items-center justify-between text-xs text-zinc-400">
                    <span className="truncate">
                      {activeIdx != null ? info.tracks[activeIdx].title : ""}
                    </span>
                    <span className="shrink-0">
                      {doneCount}/{runTotal}
                    </span>
                  </div>
                )}
                <div className="flex items-center justify-between gap-3 text-xs">
                  <span
                    aria-live="polite"
                    className="flex items-center gap-2 text-zinc-300"
                  >
                    <Loader2 size={13} className="animate-spin text-violet-400" />
                    {progressLabel}
                  </span>
                  <span className="shrink-0 font-medium text-violet-400">
                    {Math.round(percent)}%{progressDetail && ` • ${progressDetail}`}
                  </span>
                </div>
                <ProgressBar percent={percent} />
              </div>
            )}

            {isSingle && (status0 === "error" || status0 === "skipped") && (
              <p className="flex items-center gap-2 text-xs text-red-400">
                <AlertCircle size={14} className="shrink-0" />
                {t("music.noMatch")}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Track selection — albums/playlists only */}
      {info.tracks.length > 1 && (
        <div className="flex flex-col gap-1.5 mt-5 max-h-[320px] overflow-auto pr-1">
          {info.tracks.map((track, i) => {
            const status = rows[i];
            return (
              <label
                key={`${track.source_url}-${i}`}
                role="checkbox"
                aria-checked={selected.has(i)}
                tabIndex={running ? -1 : 0}
                onKeyDown={(e) => {
                  if ((e.key === " " || e.key === "Enter") && !running) {
                    e.preventDefault();
                    toggle(i);
                  }
                }}
                className="flex items-center gap-3 rounded-xl border border-white/10 bg-surface/60 hover:bg-surface-hover transition p-2.5 cursor-pointer focus-visible:!outline-none focus-visible:bg-surface-hover focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-500/70"
              >
                <input
                  type="checkbox"
                  checked={selected.has(i)}
                  disabled={running}
                  onChange={() => toggle(i)}
                  tabIndex={-1}
                  aria-hidden="true"
                  className="size-4 accent-violet-500 shrink-0 outline-none disabled:opacity-40"
                />
                <span className="flex-1 min-w-0">
                  <span className="block truncate text-sm">{track.title}</span>
                  <span className="block truncate text-xs text-zinc-400">
                    {track.artists}
                  </span>
                </span>
                {status === "active" && (
                  <Loader2 size={15} className="shrink-0 animate-spin text-violet-400" />
                )}
                {status === "done" && (
                  <CheckCircle2 size={15} className="shrink-0 text-violet-400" />
                )}
                {status === "error" && (
                  <AlertCircle size={15} className="shrink-0 text-red-400" />
                )}
                {status === "skipped" && (
                  <SkipForward size={15} className="shrink-0 text-zinc-500" />
                )}
                {!status && track.duration_ms && (
                  <span className="shrink-0 text-xs text-zinc-400">
                    {fmtMs(track.duration_ms)}
                  </span>
                )}
              </label>
            );
          })}
        </div>
      )}
    </GlassPanel>
  );
}
