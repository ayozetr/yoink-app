import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { FileText, X } from "lucide-react";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { Markdown } from "../../components/ui/Markdown";
import { useFocusTrap } from "../../lib/useFocusTrap";
import disclaimer from "../../../DISCLAIMER.md?raw";

interface TermsModalProps {
  onClose: () => void;
}

/**
 * Terms of Use & Disclaimer, shown over the Settings modal. The legal text is the
 * repo's `DISCLAIMER.md` (English only — the canonical version), rendered inline.
 */
export function TermsModal({ onClose }: TermsModalProps) {
  const { t } = useTranslation();
  const dialogRef = useFocusTrap<HTMLDivElement>();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      role="presentation"
      onClick={onClose}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4"
    >
      <GlassPanel
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="terms-title"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-2xl max-h-[calc(100vh-2rem)] overflow-y-auto p-6 !bg-[#16181f] outline-none"
      >
        <div className="mb-1 flex items-center justify-between">
          <h2
            id="terms-title"
            className="flex items-center gap-2 text-lg font-semibold"
          >
            <FileText size={18} className="text-violet-400" />
            {t("settings.terms")}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-400 transition hover:text-white"
            aria-label={t("sites.close")}
          >
            <X size={18} />
          </button>
        </div>
        <Markdown source={disclaimer} />
      </GlassPanel>
    </div>
  );
}
