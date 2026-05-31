import { useState } from "react";
import { Clock3, Download, ListVideo, Music4, Video } from "lucide-react";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { Button } from "../../../components/ui/Button";
import type {
  MediaKind,
  PlaylistEntry,
  PlaylistInfo,
} from "../../../types/download";
import type { DownloadSelection } from "./PreviewCard";

interface PlaylistCardProps {
  playlist: PlaylistInfo;
  onDownload: (entries: PlaylistEntry[], selection: DownloadSelection) => void;
  busy?: boolean;
}

// Playlist entries are listed flat (no per-item formats), so quality is a
// best-effort target shared by the whole batch.
const QUALITY_OPTIONS = ["1080p", "720p", "480p", "360p"];

/** Preview of an analyzed playlist: pick which items to download. */
export function PlaylistCard({ playlist, onDownload, busy }: PlaylistCardProps) {
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(playlist.entries.map((entry) => entry.id)),
  );
  const [kind, setKind] = useState<MediaKind>("video");
  const [quality, setQuality] = useState<string>(QUALITY_OPTIONS[0]);

  const isVideo = kind === "video";
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
    onDownload(chosen, { kind, quality: isVideo ? quality : undefined });
  };

  return (
    <GlassPanel className="p-5">
      <div className="flex items-center justify-between gap-3 mb-1">
        <span className="text-xs uppercase tracking-wider text-violet-400 flex items-center gap-2">
          <ListVideo size={14} />
          Playlist
        </span>
        <button
          type="button"
          onClick={toggleAll}
          className="text-xs text-zinc-400 hover:text-white transition"
        >
          {allSelected ? "Deseleccionar todo" : "Seleccionar todo"}
        </button>
      </div>

      <h2 className="text-xl font-semibold truncate">{playlist.title}</h2>
      <p className="text-sm text-zinc-400 mt-1">
        {playlist.uploader ? `${playlist.uploader} • ` : ""}
        {playlist.entry_count} vídeos
        {playlist.truncated && ` (mostrando los primeros ${playlist.entries.length})`}
      </p>

      {/* Controls */}
      <div className="grid md:grid-cols-3 gap-3 mt-4">
        <select
          value={kind}
          onChange={(event) => setKind(event.target.value as MediaKind)}
          className="h-12 rounded-xl bg-surface border border-white/10 px-4"
        >
          <option value="video">Vídeo (MP4)</option>
          <option value="audio">Audio (MP3)</option>
        </select>

        <select
          value={quality}
          onChange={(event) => setQuality(event.target.value)}
          disabled={!isVideo}
          className="h-12 rounded-xl bg-surface border border-white/10 px-4 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isVideo ? (
            QUALITY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))
          ) : (
            <option>Mejor calidad</option>
          )}
        </select>

        <Button
          variant="gradient"
          onClick={handleDownload}
          disabled={busy || selected.size === 0}
          className="h-12 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Download size={18} />
          Descargar ({selected.size})
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
              className="w-4 h-4 accent-violet-500 shrink-0"
            />
            <div className="w-14 h-9 rounded-md bg-gradient-to-br from-violet-500/40 to-blue-500/40 overflow-hidden flex items-center justify-center shrink-0">
              {entry.thumbnail_url ? (
                <img
                  src={entry.thumbnail_url}
                  alt={entry.title}
                  className="h-full w-full object-cover"
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
