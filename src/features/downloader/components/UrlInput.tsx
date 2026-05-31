import { Link2, Search } from "lucide-react";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { Button } from "../../../components/ui/Button";

interface UrlInputProps {
  value: string;
  onChange: (value: string) => void;
  onAnalyze: () => void;
}

/** URL field + "Analizar" action that triggers metadata extraction. */
export function UrlInput({ value, onChange, onAnalyze }: UrlInputProps) {
  return (
    <GlassPanel className="p-5">
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Link2 className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-500" />
          <input
            type="text"
            placeholder="Pega aquí la URL del vídeo..."
            value={value}
            onChange={(event) => onChange(event.target.value)}
            className="w-full h-14 pl-12 pr-4 rounded-2xl bg-surface border border-white/10 outline-none focus:border-violet-500 text-sm"
          />
        </div>

        <Button onClick={onAnalyze} className="h-14 px-6">
          <Search size={18} />
          Analizar
        </Button>
      </div>
    </GlassPanel>
  );
}
