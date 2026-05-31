import { Link2, Loader2, Search } from "lucide-react";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { Button } from "../../../components/ui/Button";

interface UrlInputProps {
  value: string;
  onChange: (value: string) => void;
  onAnalyze: () => void;
  loading?: boolean;
}

/** URL field + "Analizar" action that triggers metadata extraction. */
export function UrlInput({ value, onChange, onAnalyze, loading }: UrlInputProps) {
  const disabled = loading || value.trim().length === 0;

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
            onKeyDown={(event) => {
              if (event.key === "Enter" && !disabled) onAnalyze();
            }}
            className="w-full h-14 pl-12 pr-4 rounded-2xl bg-surface border border-white/10 outline-none focus:border-violet-500 text-sm"
          />
        </div>

        <Button
          onClick={onAnalyze}
          disabled={disabled}
          className="h-14 px-6 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <Loader2 size={18} className="animate-spin" />
          ) : (
            <Search size={18} />
          )}
          {loading ? "Analizando..." : "Analizar"}
        </Button>
      </div>
    </GlassPanel>
  );
}
