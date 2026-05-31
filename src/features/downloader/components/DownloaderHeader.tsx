import { Download } from "lucide-react";

interface DownloaderHeaderProps {
  activeDownloads: number;
}

/** Page title plus the "active downloads" status pill. */
export function DownloaderHeader({ activeDownloads }: DownloaderHeaderProps) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Media Downloader</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Descarga vídeos y audios rápidamente
        </p>
      </div>

      <div className="flex items-center gap-2 px-4 py-2 rounded-xl border border-white/10 bg-white/5 backdrop-blur-md">
        <Download className="w-4 h-4 text-violet-400" />
        <span className="text-sm text-zinc-300">
          Descargas activas: {activeDownloads}
        </span>
      </div>
    </div>
  );
}
