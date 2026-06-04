import { ClipboardPaste, Link2, Loader2, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const disabled = loading || value.trim().length === 0;

  const handlePaste = async () => {
    try {
      const text = (await navigator.clipboard.readText()).trim();
      if (text) onChange(text);
    } catch {
      // Clipboard unavailable or permission denied — ignore silently.
    }
  };

  return (
    <GlassPanel className="p-5">
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Link2 className="absolute left-4 top-1/2 -translate-y-1/2 size-5 text-zinc-500" />
          <input
            type="text"
            aria-label={t("url.placeholder")}
            placeholder={t("url.placeholder")}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !disabled) onAnalyze();
            }}
            className="w-full h-14 pl-12 pr-12 rounded-2xl bg-surface border border-white/10 outline-none focus:border-violet-500 text-sm"
          />
          <button
            type="button"
            onClick={handlePaste}
            aria-label={t("url.paste")}
            title={t("url.paste")}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-zinc-400 transition hover:bg-white/10 hover:text-white"
          >
            <ClipboardPaste size={18} />
          </button>
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
          {loading ? t("url.analyzing") : t("url.analyze")}
        </Button>
      </div>
    </GlassPanel>
  );
}
