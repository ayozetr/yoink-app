import { useEffect, useRef, useState } from "react";
import { Check, FileType } from "lucide-react";
import { useTranslation } from "react-i18next";
import { updateSettings } from "../../../lib/api";
import type { AppSettings } from "../../../types/download";

interface FilenameTemplateMenuProps {
  settings: AppSettings;
  onSaved: (settings: AppSettings) => void;
}

/** Safe, common yt-dlp name templates offered as one-tap presets. */
const PRESETS = [
  "%(title)s",
  "%(uploader)s - %(title)s",
  "%(upload_date)s - %(title)s",
  "%(title)s [%(id)s]",
] as const;

/** Sample field values so the preview shows a real-looking filename. */
const SAMPLE: Record<string, string> = {
  "%(title)s": "My Awesome Video",
  "%(uploader)s": "Cool Channel",
  "%(upload_date)s": "20260607",
  "%(id)s": "dQw4w9WgXcQ",
};

function previewName(template: string): string {
  let out = template.trim() || "%(title)s";
  for (const [key, value] of Object.entries(SAMPLE)) {
    out = out.split(key).join(value);
  }
  return `${out}.mp4`;
}

/**
 * A button (shown beside the "active downloads" pill) that opens a popover to
 * choose how downloaded files are named. Persists to settings via the API.
 */
export function FilenameTemplateMenu({
  settings,
  onSaved,
}: FilenameTemplateMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [template, setTemplate] = useState(settings.filename_template);
  const [saving, setSaving] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const save = async () => {
    const clean = template.trim() || "%(title)s";
    setSaving(true);
    try {
      const saved = await updateSettings({
        ...settings,
        filename_template: clean,
      });
      onSaved(saved);
      setOpen(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => {
          // Re-seed the field from the saved value each time we open.
          if (!open) setTemplate(settings.filename_template);
          setOpen((v) => !v);
        }}
        aria-expanded={open}
        aria-label={t("template.label")}
        title={t("template.label")}
        className="p-2.5 rounded-xl border border-white/10 bg-white/[0.06] text-zinc-300 hover:text-white hover:bg-white/10 transition"
      >
        <FileType className="size-4" />
      </button>

      {open && (
        <div className="absolute right-0 z-30 mt-2 w-80 rounded-xl border border-white/10 bg-[#1a1d27] p-4 shadow-xl">
          <p className="text-sm font-medium text-white">
            {t("template.title")}
          </p>
          <p className="mt-1 text-xs text-zinc-400">{t("template.help")}</p>

          <div className="mt-3 flex flex-col gap-1.5">
            {PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => setTemplate(preset)}
                className={`flex items-center justify-between rounded-lg border px-3 py-2 text-left text-xs transition ${
                  template.trim() === preset
                    ? "border-violet-500/50 bg-violet-600/10 text-white"
                    : "border-white/10 bg-surface text-zinc-300 hover:border-white/20"
                }`}
              >
                <span className="font-mono">{preset}</span>
                {template.trim() === preset && (
                  <Check size={14} className="text-violet-300" />
                )}
              </button>
            ))}
          </div>

          <input
            type="text"
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            aria-label={t("template.custom")}
            placeholder="%(title)s"
            className="mt-2 w-full rounded-lg bg-surface border border-white/10 px-3 py-2 font-mono text-xs outline-none focus:border-violet-500"
          />

          <p className="mt-3 text-xs text-zinc-500">
            {t("template.preview")}:{" "}
            <span className="font-mono text-zinc-300">
              {previewName(template)}
            </span>
          </p>

          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="mt-3 w-full rounded-lg bg-violet-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-violet-500 disabled:opacity-50"
          >
            {t("template.save")}
          </button>
        </div>
      )}
    </div>
  );
}
