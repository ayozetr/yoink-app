import { Clock3, Download, Video } from "lucide-react";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { Button } from "../../../components/ui/Button";
import type { VideoInfo } from "../../../types/download";

interface PreviewCardProps {
  info: VideoInfo;
  onDownload: () => void;
}

const FORMAT_OPTIONS = ["Vídeo (MP4)", "Audio (MP3)"];
const QUALITY_OPTIONS = ["1080p", "720p", "480p", "360p"];

/** Preview of the analyzed media: thumbnail, info and download controls. */
export function PreviewCard({ info, onDownload }: PreviewCardProps) {
  return (
    <GlassPanel className="p-5">
      <div className="flex gap-5">
        {/* Thumbnail */}
        <div className="w-[320px] h-[180px] rounded-2xl overflow-hidden relative bg-gradient-to-br from-violet-600/40 to-blue-600/40 flex items-center justify-center">
          {info.thumbnailUrl ? (
            <img
              src={info.thumbnailUrl}
              alt={info.title}
              className="absolute inset-0 h-full w-full object-cover"
            />
          ) : (
            <Video className="w-14 h-14 text-white/80" />
          )}
          <div className="absolute inset-0 bg-black/20" />
        </div>

        {/* Info + controls */}
        <div className="flex-1 flex flex-col justify-between">
          <div>
            <span className="text-xs uppercase tracking-wider text-violet-400">
              Vista previa
            </span>
            <h2 className="text-xl font-semibold mt-2">{info.title}</h2>
            <div className="flex items-center gap-2 mt-3 text-zinc-400">
              <Clock3 size={16} />
              <span className="text-sm">{info.duration}</span>
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-3 mt-6">
            <select className="h-12 rounded-xl bg-surface border border-white/10 px-4">
              {FORMAT_OPTIONS.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>

            <select className="h-12 rounded-xl bg-surface border border-white/10 px-4">
              {QUALITY_OPTIONS.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>

            <Button variant="gradient" onClick={onDownload} className="h-12">
              <Download size={18} />
              Descargar
            </Button>
          </div>
        </div>
      </div>
    </GlassPanel>
  );
}
