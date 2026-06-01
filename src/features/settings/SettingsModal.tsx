import { useState } from "react";
import type { ReactNode } from "react";
import {
  ArrowUpCircle,
  CheckCircle2,
  Loader2,
  Settings as SettingsIcon,
  X,
} from "lucide-react";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { Button } from "../../components/ui/Button";
import { checkForUpdates, updateSettings } from "../../lib/api";
import { openExternal } from "../../lib/openExternal";
import type { AppSettings, MediaKind, VersionInfo } from "../../types/download";

interface SettingsModalProps {
  settings: AppSettings;
  onClose: () => void;
  onSaved: (next: AppSettings) => void;
}

const QUALITY_OPTIONS = ["1080p", "720p", "480p", "360p"];
const INPUT_CLASS =
  "h-11 rounded-xl bg-surface border border-white/10 px-3 text-sm outline-none focus:border-violet-500";

/** Modal to view and edit user settings (download dir, defaults, cookies). */
export function SettingsModal({ settings, onClose, onSaved }: SettingsModalProps) {
  const [form, setForm] = useState<AppSettings>(settings);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [version, setVersion] = useState<VersionInfo | null>(null);

  const handleCheck = async () => {
    setChecking(true);
    try {
      setVersion(await checkForUpdates());
    } catch {
      setVersion({
        current: __APP_VERSION__,
        latest: null,
        update_available: false,
        release_url: null,
        error: "No se pudo comprobar (¿backend apagado?).",
      });
    } finally {
      setChecking(false);
    }
  };

  const set = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const saved = await updateSettings({
        ...form,
        cookies_from_browser: form.cookies_from_browser || null,
        cookies_file: form.cookies_file || null,
      });
      onSaved(saved);
      onClose();
    } catch {
      setError("No se pudieron guardar los ajustes.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      role="presentation"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
    >
      <GlassPanel
        role="dialog"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-lg max-h-[calc(100vh-2rem)] overflow-y-auto p-6 !bg-[#16181f]"
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <SettingsIcon size={18} className="text-violet-400" />
            Ajustes
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-400 hover:text-white transition"
            aria-label="Cerrar"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-4">
          <Field label="Carpeta de descargas">
            <input
              type="text"
              value={form.download_dir}
              onChange={(e) => set("download_dir", e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Formato por defecto">
              <select
                value={form.default_kind}
                onChange={(e) => set("default_kind", e.target.value as MediaKind)}
                className={INPUT_CLASS}
              >
                <option value="video">Vídeo (MP4)</option>
                <option value="audio">Audio (MP3)</option>
              </select>
            </Field>
            <Field label="Calidad por defecto">
              <select
                value={form.default_quality}
                onChange={(e) => set("default_quality", e.target.value)}
                className={INPUT_CLASS}
              >
                {QUALITY_OPTIONS.map((q) => (
                  <option key={q} value={q}>
                    {q}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <div className="pt-1 border-t border-white/10" />
          <p className="text-xs text-zinc-500 -mb-1">
            Cookies (solo para contenido que requiere sesión; no para contenido
            público)
          </p>

          <Field label="Navegador para cookies (p. ej. firefox, chrome)">
            <input
              type="text"
              value={form.cookies_from_browser ?? ""}
              placeholder="vacío = desactivado"
              onChange={(e) => set("cookies_from_browser", e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label="Archivo cookies.txt (alternativa al navegador)">
            <input
              type="text"
              value={form.cookies_file ?? ""}
              placeholder="/ruta/cookies.txt"
              onChange={(e) => set("cookies_file", e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
        </div>

        {error && <p className="text-sm text-red-400 mt-4">{error}</p>}

        <div className="flex justify-end gap-3 mt-6">
          <button
            type="button"
            onClick={onClose}
            className="px-4 h-11 rounded-2xl text-sm text-zinc-300 hover:text-white transition"
          >
            Cancelar
          </button>
          <Button
            variant="gradient"
            onClick={handleSave}
            disabled={saving}
            className="px-5 h-11 disabled:opacity-50"
          >
            {saving && <Loader2 size={16} className="animate-spin" />}
            Guardar
          </Button>
        </div>

        <a
          href="https://github.com/ayozetr"
          target="_blank"
          rel="noreferrer"
          onClick={(e) => {
            e.preventDefault();
            void openExternal("https://github.com/ayozetr");
          }}
          className="mt-6 flex items-center justify-center gap-1.5 border-y border-white/10 px-2 py-2.5 text-[11px] text-zinc-500 transition-colors hover:text-zinc-300"
        >
          <GithubIcon className="h-3 w-3" />
          <span>
            Desarrollado por{" "}
            <strong className="font-semibold text-zinc-300">ayozetr</strong>
          </span>
        </a>

        <div className="mt-4 flex items-center justify-between gap-3">
          <div className="text-sm">
            <span className="text-zinc-400">Versión: </span>
            <span className="font-medium">v{__APP_VERSION__}</span>
            {version && !version.error && version.update_available && (
              <span className="ml-2 text-violet-300">
                · {version.latest} disponible
              </span>
            )}
            {version && !version.error && !version.update_available && (
              <span className="ml-2 inline-flex items-center gap-1 text-emerald-400">
                <CheckCircle2 size={13} /> al día
              </span>
            )}
            {version?.error && (
              <span className="ml-2 text-zinc-500">· {version.error}</span>
            )}
          </div>

          {version?.update_available && version.release_url ? (
            <a
              href={version.release_url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => {
                e.preventDefault();
                if (version.release_url) void openExternal(version.release_url);
              }}
              className="flex items-center gap-1.5 text-sm text-violet-300 hover:text-violet-200 transition"
            >
              <ArrowUpCircle size={15} />
              Actualizar
            </a>
          ) : (
            <button
              type="button"
              onClick={handleCheck}
              disabled={checking}
              className="flex items-center gap-1.5 text-sm text-zinc-300 hover:text-white transition disabled:opacity-50"
            >
              {checking && <Loader2 size={14} className="animate-spin" />}
              Comprobar actualizaciones
            </button>
          )}
        </div>
      </GlassPanel>
    </div>
  );
}

/** GitHub mark (inline SVG — avoids depending on a brand icon in lucide). */
function GithubIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      className={className}
    >
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-zinc-400">{label}</span>
      {children}
    </label>
  );
}
