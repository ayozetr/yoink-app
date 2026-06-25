import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

interface CopyButtonProps {
  /** Text copied to the clipboard on click. */
  text: string;
  /** Accessible label / tooltip (defaults to "Copy"). */
  label?: string;
  className?: string;
}

/** A tiny "copy to clipboard" icon button with a brief check confirmation. */
export function CopyButton({ text, label, className = "" }: CopyButtonProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable — ignore.
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      title={label ?? t("common.copy")}
      aria-label={label ?? t("common.copy")}
      className={`shrink-0 rounded-md p-1 text-zinc-400 transition hover:bg-white/10 hover:text-white ${className}`}
    >
      {copied ? (
        <Check size={13} className="text-emerald-400" />
      ) : (
        <Copy size={13} />
      )}
    </button>
  );
}
