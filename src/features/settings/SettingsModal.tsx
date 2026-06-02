import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowUpCircle,
  CheckCircle2,
  Coffee,
  FolderOpen,
  HelpCircle,
  Loader2,
  Settings as SettingsIcon,
  X,
} from "lucide-react";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { Button } from "../../components/ui/Button";
import { Select } from "../../components/ui/Select";
import { updateSettings } from "../../lib/api";
import { openExternal } from "../../lib/openExternal";
import { pickDirectory } from "../../lib/pickDirectory";
import {
  checkForUpdate,
  installUpdate,
  RELEASES_URL,
  type UpdateCheck,
} from "../../lib/updater";
import i18n from "../../i18n";
import type { AppSettings, MediaKind } from "../../types/download";

const LANG_STORAGE_KEY = "yoink-lang";

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
  const { t } = useTranslation();
  const [form, setForm] = useState<AppSettings>(settings);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<UpdateCheck | null>(null);
  const [installing, setInstalling] = useState(false);
  // "system" = follow the OS/browser language; otherwise a forced choice.
  const [lang, setLang] = useState<string>(
    () => localStorage.getItem(LANG_STORAGE_KEY) ?? "system",
  );

  const pickFolder = async () => {
    const dir = await pickDirectory(form.download_dir);
    if (dir) set("download_dir", dir);
  };

  const changeLanguage = (value: string) => {
    setLang(value);
    if (value === "system") {
      localStorage.removeItem(LANG_STORAGE_KEY);
      void i18n.changeLanguage(navigator.language.startsWith("es") ? "es" : "en");
    } else {
      void i18n.changeLanguage(value); // the detector caches it in localStorage
    }
  };

  const handleCheck = async () => {
    setChecking(true);
    setResult(null);
    try {
      setResult(await checkForUpdate());
    } finally {
      setChecking(false);
    }
  };

  const handleInstall = async () => {
    if (result?.status !== "available") return;
    setInstalling(true);
    try {
      await installUpdate(result.update);
      // installUpdate relaunches the app; control won't return on success.
    } catch {
      setInstalling(false);
      setResult({ status: "error" });
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
      setError(t("settings.saveError"));
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
            {t("settings.title")}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-400 hover:text-white transition"
            aria-label={t("settings.close")}
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-4">
          <Field label={t("settings.downloadDir")}>
            <div className="relative">
              <input
                type="text"
                aria-label={t("settings.downloadDir")}
                value={form.download_dir}
                onChange={(e) => set("download_dir", e.target.value)}
                className={`${INPUT_CLASS} w-full pr-11`}
              />
              <button
                type="button"
                onClick={pickFolder}
                aria-label={t("settings.browse")}
                title={t("settings.browse")}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-zinc-400 transition hover:bg-white/10 hover:text-white"
              >
                <FolderOpen size={18} />
              </button>
            </div>
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label={t("settings.defaultFormat")}>
              <Select
                ariaLabel={t("settings.defaultFormat")}
                value={form.default_kind}
                onChange={(v) => set("default_kind", v as MediaKind)}
                options={[
                  { value: "video", label: t("settings.video") },
                  { value: "audio", label: t("settings.audio") },
                ]}
                className={`${INPUT_CLASS} w-full`}
              />
            </Field>
            <Field label={t("settings.defaultQuality")}>
              <Select
                ariaLabel={t("settings.defaultQuality")}
                value={form.default_quality}
                onChange={(v) => set("default_quality", v)}
                options={QUALITY_OPTIONS.map((q) => ({ value: q, label: q }))}
                className={`${INPUT_CLASS} w-full`}
              />
            </Field>
          </div>

          <Field label={t("settings.language")}>
            <Select
              ariaLabel={t("settings.language")}
              value={lang}
              onChange={changeLanguage}
              options={[
                { value: "system", label: t("settings.langSystem") },
                { value: "es", label: "Español" },
                { value: "en", label: "English" },
              ]}
              className={`${INPUT_CLASS} w-full`}
            />
          </Field>

          <div className="pt-1 border-t border-white/10" />
          <p className="text-xs text-zinc-500 -mb-1">
            {t("settings.cookiesHint")}
          </p>

          <Field label={t("settings.cookiesBrowser")}>
            <input
              type="text"
              aria-label={t("settings.cookiesBrowser")}
              value={form.cookies_from_browser ?? ""}
              placeholder={t("settings.cookiesBrowserPlaceholder")}
              onChange={(e) => set("cookies_from_browser", e.target.value)}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label={t("settings.cookiesFile")} hint={<CookiesHelp />}>
            <input
              type="text"
              aria-label={t("settings.cookiesFile")}
              value={form.cookies_file ?? ""}
              placeholder={t("settings.cookiesFilePlaceholder")}
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
            {t("settings.cancel")}
          </button>
          <Button
            variant="gradient"
            onClick={handleSave}
            disabled={saving}
            className="px-5 h-11 disabled:opacity-50"
          >
            {saving && <Loader2 size={16} className="animate-spin" />}
            {t("settings.save")}
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
          <GithubIcon className="size-3" />
          <span>
            {t("settings.developedBy")}{" "}
            <strong className="font-semibold text-zinc-300">ayozetr</strong>
          </span>
        </a>

        <div className="mt-4 flex items-center justify-between gap-3">
          <div className="text-sm">
            <span className="text-zinc-400">{t("settings.version")}</span>
            <span className="font-medium ml-1.5">v{__APP_VERSION__}</span>
            {result?.status === "available" && (
              <span className="ml-2 text-violet-300">
                · {t("settings.updateAvailable", { version: result.version })}
              </span>
            )}
            {result?.status === "up-to-date" && (
              <span className="ml-2 inline-flex items-center gap-1 text-emerald-400">
                <CheckCircle2 size={13} /> {t("settings.upToDate")}
              </span>
            )}
            {result?.status === "error" && (
              <span className="ml-2 text-zinc-500">
                · {t("settings.checkError")}
              </span>
            )}
            {result?.status === "tauri-unavailable" && (
              <span className="ml-2 text-zinc-500">
                · {t("settings.checkDesktopOnly")}
              </span>
            )}
          </div>

          {result?.status === "available" && result.autoInstallable ? (
            <button
              type="button"
              onClick={handleInstall}
              disabled={installing}
              className="flex items-center gap-1.5 text-sm text-violet-300 hover:text-violet-200 transition disabled:opacity-50"
            >
              {installing ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <ArrowUpCircle size={15} />
              )}
              {installing
                ? t("settings.installing")
                : t("settings.downloadInstall")}
            </button>
          ) : result?.status === "available" ? (
            <a
              href={RELEASES_URL}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => {
                e.preventDefault();
                void openExternal(RELEASES_URL);
              }}
              className="flex items-center gap-1.5 text-sm text-violet-300 hover:text-violet-200 transition"
            >
              <ArrowUpCircle size={15} />
              {t("settings.viewRelease")}
            </a>
          ) : (
            <button
              type="button"
              onClick={handleCheck}
              disabled={checking}
              className="flex items-center gap-1.5 text-sm text-zinc-300 hover:text-white transition disabled:opacity-50"
            >
              {checking && <Loader2 size={14} className="animate-spin" />}
              {t("settings.checkUpdates")}
            </button>
          )}
        </div>

        <a
          href="https://ko-fi.com/ayozetr"
          target="_blank"
          rel="noreferrer"
          onClick={(e) => {
            e.preventDefault();
            void openExternal("https://ko-fi.com/ayozetr");
          }}
          className="mt-3 flex items-center justify-center gap-1.5 text-[11px] text-zinc-500 transition-colors hover:text-violet-300"
        >
          <Coffee size={12} />
          {t("settings.donate")}
        </a>
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

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1.5 text-xs text-zinc-400">
        {label}
        {hint}
      </span>
      {children}
    </div>
  );
}

const COOKIES_EXT_CHROMIUM =
  "https://chromewebstore.google.com/detail/cclelndahbckbenkjhflpdbgdldlbecc?utm_source=item-share-cb";
const COOKIES_EXT_FIREFOX =
  "https://addons.mozilla.org/es-ES/firefox/addon/get-cookies-txt-locally/";

/** A "?" button that reveals how to generate a cookies.txt with the browser extension. */
function CookiesHelp() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const WIDTH = 288; // w-72

  // Anchor the popover with `fixed` so the modal's overflow can't clip it.
  useLayoutEffect(() => {
    if (!open || !btnRef.current) return;
    const r = btnRef.current.getBoundingClientRect();
    const left = Math.min(r.left, window.innerWidth - WIDTH - 12);
    setPos({ top: r.bottom + 6, left: Math.max(12, left) });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node;
      if (btnRef.current?.contains(target) || popRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    // Capture phase: the modal panel calls stopPropagation() on click.
    window.addEventListener("click", onPointer, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", onPointer, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={t("settings.cookiesHelp")}
        title={t("settings.cookiesHelp")}
        className="inline-flex text-zinc-500 transition hover:text-zinc-200"
      >
        <HelpCircle size={13} />
      </button>
      {open && pos && (
        <div
          ref={popRef}
          style={{ position: "fixed", top: pos.top, left: pos.left, width: WIDTH }}
          className="z-[200] rounded-lg border border-white/10 bg-[#1a1d27] p-3 text-xs leading-relaxed text-zinc-300 shadow-xl"
        >
          {t("settings.cookiesHelpText")}
          <div className="mt-2 flex flex-col gap-1">
            <button
              type="button"
              onClick={() => void openExternal(COOKIES_EXT_CHROMIUM)}
              className="text-left text-violet-300 transition hover:text-violet-200 hover:underline"
            >
              {t("settings.cookiesHelpChromium")}
            </button>
            <button
              type="button"
              onClick={() => void openExternal(COOKIES_EXT_FIREFOX)}
              className="text-left text-violet-300 transition hover:text-violet-200 hover:underline"
            >
              {t("settings.cookiesHelpFirefox")}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
