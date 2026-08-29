import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowUpCircle,
  Ban,
  CheckCircle2,
  Coffee,
  CornerDownRight,
  Download,
  FolderOpen,
  Globe,
  HelpCircle,
  Info,
  Keyboard,
  Loader2,
  Monitor,
  MousePointerClick,
  Music,
  Puzzle,
  Settings as SettingsIcon,
  Shield,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { Button } from "../../components/ui/Button";
import { Select } from "../../components/ui/Select";
import { Toggle } from "../../components/ui/Toggle";
import { SponsorBlockIcon } from "../../components/ui/SponsorBlockIcon";
import { BrowserIcon } from "../../components/ui/BrowserIcon";
import { AutotagSourceIcon } from "../../components/ui/AutotagSourceIcon";
import { WhaleIcon } from "../../components/ui/WhaleIcon";
import { FlagIcon } from "../../components/ui/FlagIcon";
import { TermsModal } from "./TermsModal";
import { LicensesModal } from "./LicensesModal";
import logoUrl from "../../assets/logo.png";
import { fetchYtdlpVersion, updateSettings } from "../../lib/api";
import { openExternal } from "../../lib/openExternal";
import { pickDirectory, pickFile } from "../../lib/pickDirectory";
import { useFocusTrap } from "../../lib/useFocusTrap";
import { isTauri } from "../../lib/desktop";
import { checkForUpdate, RELEASES_URL, type UpdateCheck } from "../../lib/updater";
import type { Update } from "@tauri-apps/plugin-updater";
import {
  SUPPORTED_LANGUAGES,
  changeLanguage as applyLanguage,
} from "../../i18n";
import type {
  AppSettings,
  AudioBitrate,
  AudioFormat,
  AutotagSource,
  MediaKind,
  SponsorblockAction,
  VersionInfo,
  VideoCodec,
  VideoContainer,
} from "../../types/download";
import { AUDIO_FORMATS, VIDEO_CONTAINERS } from "../downloader/formatOptions";

const LANG_STORAGE_KEY = "yoink-lang";

interface SettingsModalProps {
  settings: AppSettings;
  onClose: () => void;
  onSaved: (next: AppSettings) => void;
  /** Open the "what's new" popup (closes this modal first). */
  onShowWhatsNew: () => void;
  /** Download + install the update (closes this modal; App shows the progress). */
  onInstall: (update: Update) => void;
}

const QUALITY_OPTIONS = ["1440p", "1080p", "720p", "480p", "360p"];

// UI languages (besides "system") with a representative country flag (ISO code
// under /public/flags). pt → br (the locale is Brazilian), uk → ua (Ukraine),
// hi → in, zh → cn, ja → jp, ko → kr, en → gb.
const LANGUAGE_OPTIONS = [
  { value: "en", label: "English", flag: "gb" },
  { value: "es", label: "Español", flag: "es" },
  { value: "fr", label: "Français", flag: "fr" },
  { value: "de", label: "Deutsch", flag: "de" },
  { value: "it", label: "Italiano", flag: "it" },
  { value: "pt", label: "Português (BR)", flag: "br" },
  { value: "ru", label: "Русский", flag: "ru" },
  { value: "pl", label: "Polski", flag: "pl" },
  { value: "uk", label: "Українська", flag: "ua" },
  { value: "id", label: "Bahasa Indonesia", flag: "id" },
  { value: "hi", label: "हिन्दी", flag: "in" },
  { value: "zh", label: "简体中文", flag: "cn" },
  { value: "ja", label: "日本語", flag: "jp" },
  { value: "ko", label: "한국어", flag: "kr" },
] as const;
// Sentinel: name audio files after the auto-tag metadata ("Artist - Title").
// The backend downloads under %(title)s and renames once auto-tagging resolves
// the real metadata (backend AUTOTAG_FILENAME_TEMPLATE).
const AUTOTAG_TEMPLATE = "%(autotag)s";
const AUTOTAG_TEMPLATE_REV = "%(autotag_ta)s";
// Shown in the template dropdown in the same %(...)s style as the other presets
// (their real values are the sentinels above — the file is renamed to the tag).
const AUTOTAG_LABEL = "%(artist)s - %(title)s (auto-tag)";
const AUTOTAG_LABEL_REV = "%(title)s - %(artist)s (auto-tag)";
const TEMPLATE_PRESETS = [
  "%(title)s",
  "%(uploader)s - %(title)s",
  "%(upload_date)s - %(title)s",
  "%(title)s [%(id)s]",
  AUTOTAG_TEMPLATE,
  AUTOTAG_TEMPLATE_REV,
];

// Illustrative values so a yt-dlp template renders as a concrete sample filename.
// `title` is the raw YouTube title (with its "(Official Music Video)" cruft); the
// auto-tag presets clean it down to the song, so they use AUTOTAG_SAMPLE_TITLE.
const TEMPLATE_SAMPLE: Record<string, string> = {
  title: "Big Poppa (Official Music Video)",
  uploader: "The Notorious B.I.G.",
  upload_date: "20110906",
  id: "phaJXp_zMYM",
  playlist_index: "01",
  ext: "mp3",
};
const AUTOTAG_SAMPLE_TITLE = "Big Poppa";

/** Render a yt-dlp output template as an example filename (e.g. "Blinding Lights.mp3"). */
function templateExample(tpl: string): string {
  // The auto-tag templates aren't yt-dlp fields — show their "Artist - Title" shape
  // with the cleaned (tagged) title, not the raw YouTube one.
  if (tpl === AUTOTAG_TEMPLATE) {
    return `${TEMPLATE_SAMPLE.uploader} - ${AUTOTAG_SAMPLE_TITLE}.mp3`;
  }
  if (tpl === AUTOTAG_TEMPLATE_REV) {
    return `${AUTOTAG_SAMPLE_TITLE} - ${TEMPLATE_SAMPLE.uploader}.mp3`;
  }
  const name = (tpl || "%(title)s").replace(
    /%\(([a-z_]+)\)s/g,
    (_, key: string) => TEMPLATE_SAMPLE[key] ?? `%(${key})s`,
  );
  return `${name}.mp3`;
}
const INPUT_CLASS =
  "h-11 rounded-xl bg-surface border border-white/10 px-3 text-sm outline-none focus:border-violet-500";

/**
 * Browsers yt-dlp can read cookies from directly (same names on Linux &
 * Windows). Safari is macOS-only — added once a macOS build ships (see ROADMAP).
 * Whale (Naver's Chromium browser) is included since the app ships in Korean.
 */
const COOKIE_BROWSERS = [
  "brave",
  "chrome",
  "chromium",
  "edge",
  "firefox",
  "opera",
  "vivaldi",
  "whale",
] as const;

/** Left-rail categories for the settings modal (sidebar + content panel). */
const SECTIONS = [
  { id: "general", labelKey: "settings.catGeneral", icon: <Monitor size={16} /> },
  { id: "downloads", labelKey: "settings.secDownloads", icon: <Download size={16} /> },
  { id: "quality", labelKey: "settings.secQuality", icon: <SlidersHorizontal size={16} /> },
  { id: "processing", labelKey: "settings.secProcessing", icon: <Music size={16} /> },
  { id: "sponsorblock", labelKey: "settings.sponsorblock", icon: <Shield size={16} /> },
  { id: "network", labelKey: "settings.secNetwork", icon: <Globe size={16} /> },
  { id: "shortcuts", labelKey: "settings.catShortcuts", icon: <Keyboard size={16} /> },
  { id: "extension", labelKey: "settings.catExtension", icon: <Puzzle size={16} /> },
  { id: "about", labelKey: "settings.catAbout", icon: <Info size={16} /> },
] as const;

// Keyboard shortcuts shown (read-only) in the Shortcuts section. `mod` is the
// platform modifier (⌘ on macOS, Ctrl elsewhere); "⇧" is Shift.
const SHORTCUTS = [
  { labelKey: "settings.shortcutFocusUrl", keys: (mod: string) => [mod, "L"], desktopOnly: false },
  { labelKey: "settings.shortcutSettings", keys: (mod: string) => [mod, ","], desktopOnly: false },
  {
    labelKey: "settings.shortcutPasteAnalyze",
    keys: (mod: string) => [mod, "⇧", "V"],
    desktopOnly: false,
  },
  {
    // Global (desktop-only): the Tauri shell registers these when enabled.
    labelKey: "settings.shortcutGlobalPaste",
    keys: (mod: string) => [mod, "⇧", "Y"],
    desktopOnly: true,
  },
  {
    labelKey: "settings.shortcutGlobalToggle",
    keys: (mod: string) => [mod, "⇧", "O"],
    desktopOnly: true,
  },
  {
    labelKey: "settings.shortcutGlobalQuick",
    keys: (mod: string) => [mod, "⇧", "D"],
    desktopOnly: true,
  },
  {
    labelKey: "settings.shortcutGlobalFocusPaste",
    keys: (mod: string) => [mod, "⇧", "P"],
    desktopOnly: true,
  },
  {
    labelKey: "settings.shortcutGlobalCancel",
    keys: (mod: string) => [mod, "⇧", "X"],
    desktopOnly: true,
  },
  {
    labelKey: "settings.shortcutGlobalFolder",
    keys: (mod: string) => [mod, "⇧", "F"],
    desktopOnly: true,
  },
  { labelKey: "settings.shortcutCloseModal", keys: () => ["Esc"], desktopOnly: false },
] as const;
const IS_MAC =
  typeof navigator !== "undefined" && /mac/i.test(navigator.userAgent);
const SHORTCUT_MOD = IS_MAC ? "⌘" : "Ctrl";
type SectionId = (typeof SECTIONS)[number]["id"];

/** One shortcut row: its label + the key combo as <kbd> chips. */
function ShortcutRow({ shortcut }: { shortcut: (typeof SHORTCUTS)[number] }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-sm">
      <span className="min-w-0 truncate text-zinc-200">{t(shortcut.labelKey)}</span>
      <span className="flex shrink-0 items-center gap-1">
        {shortcut.keys(SHORTCUT_MOD).map((k, i) => (
          <kbd
            key={i}
            className="inline-flex min-w-[1.75rem] items-center justify-center rounded-md border border-white/15 bg-white/[0.06] px-1.5 py-0.5 font-sans text-xs text-zinc-300 shadow-sm"
          >
            {k}
          </kbd>
        ))}
      </span>
    </div>
  );
}

/** Modal to view and edit user settings (download dir, defaults, cookies). */
export function SettingsModal({
  settings,
  onClose,
  onSaved,
  onShowWhatsNew,
  onInstall,
}: SettingsModalProps) {
  const { t } = useTranslation();
  const dialogRef = useFocusTrap<HTMLDivElement>();
  const [form, setForm] = useState<AppSettings>(settings);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<UpdateCheck | null>(null);
  const [ytdlp, setYtdlp] = useState<VersionInfo | null>(null);
  // "system" = follow the OS/browser language; otherwise a forced choice.
  const [lang, setLang] = useState<string>(
    () => localStorage.getItem(LANG_STORAGE_KEY) ?? "system",
  );
  // Filename template: "custom" mode when the saved value isn't a known preset.
  const [templateCustom, setTemplateCustom] = useState(
    () => !TEMPLATE_PRESETS.includes(settings.filename_template),
  );
  // Which sidebar category is showing in the content panel.
  const [section, setSection] = useState<SectionId>("general");
  const [termsOpen, setTermsOpen] = useState(false);
  const [licensesOpen, setLicensesOpen] = useState(false);

  const pickFolder = async () => {
    const dir = await pickDirectory(form.download_dir);
    if (dir) set("download_dir", dir);
  };

  const pickCookiesFile = async () => {
    const file = await pickFile(form.cookies_file ?? undefined, [
      { name: "cookies.txt", extensions: ["txt"] },
    ]);
    if (file) set("cookies_file", file);
  };

  const changeLanguage = (value: string) => {
    setLang(value);
    if (value === "system") {
      localStorage.removeItem(LANG_STORAGE_KEY);
      // Follow the OS language if we support it, else fall back to English.
      const sys = navigator.language.split("-")[0];
      void applyLanguage(SUPPORTED_LANGUAGES.includes(sys) ? sys : "en");
    } else {
      localStorage.setItem(LANG_STORAGE_KEY, value); // persist the explicit choice
      void applyLanguage(value);
    }
  };

  const handleCheck = async () => {
    setChecking(true);
    setResult(null);
    setYtdlp(null);
    try {
      // Check the app and the bundled yt-dlp together (neither blocks the other).
      const [appResult, ytdlpResult] = await Promise.allSettled([
        checkForUpdate(),
        fetchYtdlpVersion(),
      ]);
      if (appResult.status === "fulfilled") setResult(appResult.value);
      if (ytdlpResult.status === "fulfilled") setYtdlp(ytdlpResult.value);
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
      // App.tsx applies the desktop (Tauri) behaviours reactively when `settings`
      // updates (covers both this save and the initial load).
      onSaved(saved);
      onClose();
    } catch {
      setError(t("settings.saveError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
    <div
      role="presentation"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
    >
      <GlassPanel
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className="flex w-full max-w-3xl h-[85vh] max-h-[620px] flex-col overflow-hidden !bg-[#16181f] p-0 outline-none"
      >
        <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
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

        <div className="flex min-h-0 flex-1">
          {/* Icon-only rail on a narrow window (collapses below sm so it doesn't
              eat the content width); full labels once there's room. */}
          <nav className="flex w-14 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-white/10 p-2 sm:w-44 sm:p-3">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setSection(s.id)}
                title={t(s.labelKey)}
                className={`flex items-center justify-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition sm:justify-start ${
                  section === s.id
                    ? "bg-violet-600/15 font-medium text-white"
                    : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
                }`}
              >
                <span className="shrink-0">{s.icon}</span>
                <span className="hidden truncate sm:inline">{t(s.labelKey)}</span>
              </button>
            ))}
          </nav>

          <div className="min-w-0 flex-1 overflow-y-auto px-6 py-5">
            <div className="flex min-h-full flex-col gap-4">
              {section === "general" && (
                <>
                  <Field label={t("settings.language")}>
                    <Select
                      ariaLabel={t("settings.language")}
                      value={lang}
                      onChange={changeLanguage}
                      options={[
                        {
                          value: "system",
                          label: t("settings.langSystem"),
                          icon: (
                            <Monitor
                              size={16}
                              className="shrink-0 text-zinc-400"
                            />
                          ),
                        },
                        ...LANGUAGE_OPTIONS.map((o) => ({
                          value: o.value,
                          label: o.label,
                          icon: <FlagIcon code={o.flag} />,
                        })),
                      ]}
                      className={`${INPUT_CLASS} w-full`}
                    />
                  </Field>
                  <Toggle
                    checked={form.check_updates}
                    onChange={(v) => set("check_updates", v)}
                    label={t("settings.autoCheckUpdates")}
                    className="w-full"
                  />
                  <Toggle
                    checked={form.notify_on_complete}
                    onChange={(v) => set("notify_on_complete", v)}
                    label={t("settings.notifyOnComplete")}
                    className="w-full"
                  />
                  {isTauri() && (
                    <>
                      <Toggle
                        checked={form.minimize_to_tray}
                        onChange={(v) => set("minimize_to_tray", v)}
                        label={t("settings.minimizeToTray")}
                        help={<MinimizeToTrayHelp />}
                        className="w-full"
                      />
                      <Toggle
                        checked={form.launch_at_startup}
                        onChange={(v) => set("launch_at_startup", v)}
                        label={t("settings.launchAtStartup")}
                        className="w-full"
                      />
                    </>
                  )}
                </>
              )}

              {section === "downloads" && (
                <>
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

          <Field label={t("settings.filenameTemplate")}>
            <Select
              ariaLabel={t("settings.filenameTemplate")}
              value={templateCustom ? "__custom__" : form.filename_template}
              onChange={(v) => {
                if (v === "__custom__") {
                  setTemplateCustom(true);
                } else {
                  setTemplateCustom(false);
                  set("filename_template", v);
                }
              }}
              options={[
                ...TEMPLATE_PRESETS.map((p) => ({
                  value: p,
                  label:
                    p === AUTOTAG_TEMPLATE
                      ? AUTOTAG_LABEL
                      : p === AUTOTAG_TEMPLATE_REV
                        ? AUTOTAG_LABEL_REV
                        : p,
                })),
                { value: "__custom__", label: t("settings.filenameCustom") },
              ]}
              className={`${INPUT_CLASS} w-full`}
            />
          </Field>
          {templateCustom && (
            <input
              type="text"
              aria-label={t("settings.filenameCustom")}
              value={form.filename_template}
              onChange={(e) => set("filename_template", e.target.value)}
              placeholder="%(title)s"
              className={`${INPUT_CLASS} w-full font-mono text-xs`}
            />
          )}
          <p className="-mt-1 flex items-center gap-1.5 truncate text-[11px] text-zinc-500">
            <CornerDownRight size={12} className="shrink-0" />
            <span className="truncate font-mono text-zinc-400">
              {templateExample(form.filename_template)}
            </span>
          </p>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={t("settings.defaultFormat")} className="col-span-2">
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
            <Field label={t("settings.defaultContainer")}>
              <Select
                ariaLabel={t("settings.defaultContainer")}
                value={form.default_container}
                onChange={(v) => set("default_container", v as VideoContainer)}
                options={VIDEO_CONTAINERS}
                className={`${INPUT_CLASS} w-full`}
              />
            </Field>
            <Field
              label={t("settings.defaultAudioFormat")}
              hint={<AudioFormatHelp />}
            >
              <Select
                ariaLabel={t("settings.defaultAudioFormat")}
                value={form.default_audio_format}
                onChange={(v) => set("default_audio_format", v as AudioFormat)}
                options={AUDIO_FORMATS.map((o) => ({
                  value: o.value,
                  label: o.label,
                }))}
                className={`${INPUT_CLASS} w-full`}
              />
            </Field>
          </div>

          <div className="flex flex-col gap-2">
            <Toggle
              checked={form.default_embed_subs}
              onChange={(v) => set("default_embed_subs", v)}
              label={t("settings.defaultEmbedSubs")}
              help={<EmbedSubsHelp />}
              className="w-full"
            />
            <Toggle
              checked={form.default_embed_chapters}
              onChange={(v) => set("default_embed_chapters", v)}
              label={t("settings.defaultEmbedChapters")}
              className="w-full"
            />
          </div>
                </>
              )}

              {section === "quality" && (
                <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={t("settings.defaultQuality")}>
              <Select
                ariaLabel={t("settings.defaultQuality")}
                value={form.default_quality}
                onChange={(v) => set("default_quality", v)}
                options={[
                  { value: "best", label: t("settings.qualityBest") },
                  ...QUALITY_OPTIONS.map((q) => ({ value: q, label: q })),
                ]}
                className={`${INPUT_CLASS} w-full`}
              />
            </Field>
            <Field label={t("settings.videoCodec")}>
              <Select
                ariaLabel={t("settings.videoCodec")}
                value={form.video_codec}
                onChange={(v) => set("video_codec", v as VideoCodec)}
                options={[
                  { value: "any", label: t("settings.videoCodecAny") },
                  { value: "h264", label: "H.264" },
                  { value: "vp9", label: "VP9" },
                  { value: "av1", label: "AV1" },
                ]}
                className={`${INPUT_CLASS} w-full`}
              />
            </Field>
            <Field label={t("settings.audioBitrate")}>
              <Select
                ariaLabel={t("settings.audioBitrate")}
                value={form.audio_bitrate}
                onChange={(v) => set("audio_bitrate", v as AudioBitrate)}
                options={[
                  { value: "best", label: t("settings.audioBitrateBest") },
                  { value: "320", label: "320 kbps" },
                  { value: "256", label: "256 kbps" },
                  { value: "192", label: "192 kbps" },
                  { value: "128", label: "128 kbps" },
                ]}
                className={`${INPUT_CLASS} w-full`}
              />
            </Field>
          </div>
                </>
              )}

              {section === "processing" && (
                <>
          <Field label={t("settings.autotagSource")}>
            <Select
              ariaLabel={t("settings.autotagSource")}
              value={form.autotag_source}
              onChange={(v) => set("autotag_source", v as AutotagSource)}
              options={[
                {
                  value: "auto",
                  label: t("settings.autotagAuto"),
                  icon: <Sparkles className="size-4" />,
                },
                {
                  value: "apple",
                  label: t("settings.autotagApple"),
                  icon: <AutotagSourceIcon source="apple" className="size-4" />,
                },
                {
                  value: "deezer",
                  label: t("settings.autotagDeezer"),
                  icon: <AutotagSourceIcon source="deezer" className="size-4" />,
                },
                {
                  value: "musicbrainz",
                  label: t("settings.autotagMusicbrainz"),
                  icon: (
                    <AutotagSourceIcon source="musicbrainz" className="size-4" />
                  ),
                },
              ]}
              className={`${INPUT_CLASS} w-full`}
            />
          </Field>
          <p className="text-[11px] italic text-zinc-400 -mt-1">
            {t(`settings.autotagHint_${form.autotag_source}`)}
          </p>

          <Toggle
            checked={form.normalize_audio}
            onChange={(v) => set("normalize_audio", v)}
            label={t("settings.normalizeAudio")}
            help={<NormalizeAudioHelp />}
            className="w-full"
          />

          <Toggle
            checked={form.nfo_sidecars}
            onChange={(v) => set("nfo_sidecars", v)}
            label={t("settings.nfoSidecars")}
            help={<NfoHelp />}
            className="w-full"
          />

          <Toggle
            checked={form.music_folders}
            onChange={(v) => set("music_folders", v)}
            label={t("settings.musicFolders")}
            help={<MusicFoldersHelp />}
            className="w-full"
          />

          <div className="flex flex-col gap-2">
            <Toggle
              checked={form.fetch_lyrics}
              onChange={(v) => set("fetch_lyrics", v)}
              label={t("settings.fetchLyrics")}
              help={<LyricsHelp />}
              className="w-full"
            />
            {form.fetch_lyrics && (
              <div className="border-l border-white/10 pl-3">
                <Toggle
                  checked={form.lyrics_lrc}
                  onChange={(v) => set("lyrics_lrc", v)}
                  label={t("settings.lyricsLrc")}
                  help={<LyricsLrcHelp />}
                  className="w-full"
                />
              </div>
            )}
          </div>
                </>
              )}

              {section === "sponsorblock" && (
                <>
          <div className="flex flex-col gap-2">
            <Toggle
              checked={form.sponsorblock_enabled}
              onChange={(v) => set("sponsorblock_enabled", v)}
              label={t("settings.sponsorblock")}
              icon={<SponsorBlockIcon className="size-4 shrink-0" />}
              help={<SponsorBlockHelp />}
              className="w-full"
            />
            {form.sponsorblock_enabled && (
              <>
                <Select
                  ariaLabel={t("settings.sponsorblockAction")}
                  value={form.sponsorblock_action}
                  onChange={(v) =>
                    set("sponsorblock_action", v as SponsorblockAction)
                  }
                  options={[
                    { value: "remove", label: t("settings.sponsorblockRemove") },
                    { value: "mark", label: t("settings.sponsorblockMark") },
                  ]}
                  className={`${INPUT_CLASS} w-full`}
                />
                <p className="text-[11px] italic text-zinc-400">
                  {t(`settings.sponsorblockHint_${form.sponsorblock_action}`)}
                </p>
              </>
            )}
          </div>
                </>
              )}

              {section === "network" && (
                <>
          <Field label={t("settings.rateLimit")}>
            <Select
              ariaLabel={t("settings.rateLimit")}
              value={form.rate_limit ?? ""}
              onChange={(v) => set("rate_limit", v === "" ? null : v)}
              options={[
                { value: "", label: t("settings.rateLimitNone") },
                { value: "5M", label: "5 MB/s" },
                { value: "10M", label: "10 MB/s" },
                { value: "20M", label: "20 MB/s" },
                { value: "35M", label: "35 MB/s" },
                { value: "50M", label: "50 MB/s" },
              ]}
              className={`${INPUT_CLASS} w-full`}
            />
          </Field>

          <p className="text-xs text-zinc-400 -mb-1">
            {t("settings.cookiesHint")}
          </p>

          <Field label={t("settings.cookiesBrowser")} hint={<BrowserCookiesHelp />}>
            <Select
              ariaLabel={t("settings.cookiesBrowser")}
              value={form.cookies_from_browser ?? ""}
              onChange={(v) => set("cookies_from_browser", v)}
              options={[
                {
                  value: "",
                  label: t("settings.cookiesBrowserNone"),
                  icon: <Ban className="size-4" />,
                },
                ...COOKIE_BROWSERS.map((b) => ({
                  value: b,
                  label: b.charAt(0).toUpperCase() + b.slice(1),
                  icon:
                    b === "whale" ? (
                      <WhaleIcon className="size-4" />
                    ) : (
                      <BrowserIcon browser={b} className="size-4" />
                    ),
                })),
              ]}
              className={`${INPUT_CLASS} w-full`}
            />
          </Field>
          <p className="text-[11px] italic text-zinc-400 -mt-1">
            {t("settings.cookiesBrowserNote")}
          </p>

          <Field label={t("settings.cookiesFile")} hint={<CookiesHelp />}>
            <div className="relative">
              <input
                type="text"
                aria-label={t("settings.cookiesFile")}
                value={form.cookies_file ?? ""}
                placeholder={t("settings.cookiesFilePlaceholder")}
                onChange={(e) => set("cookies_file", e.target.value)}
                className={`${INPUT_CLASS} w-full pr-11`}
              />
              <button
                type="button"
                onClick={pickCookiesFile}
                aria-label={t("settings.browse")}
                title={t("settings.browse")}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-zinc-400 transition hover:bg-white/10 hover:text-white"
              >
                <FolderOpen size={18} />
              </button>
            </div>
          </Field>

          <Field label={t("settings.proxy")} hint={<ProxyHelp />}>
            <input
              type="text"
              aria-label={t("settings.proxy")}
              value={form.proxy ?? ""}
              placeholder="socks5://127.0.0.1:1080"
              onChange={(e) => set("proxy", e.target.value || null)}
              className={`${INPUT_CLASS} w-full`}
            />
          </Field>

          <Field label={t("settings.poToken")} hint={<PoTokenHelp />}>
            <input
              type="text"
              aria-label={t("settings.poToken")}
              value={form.po_token ?? ""}
              placeholder={t("settings.poTokenPlaceholder")}
              onChange={(e) => set("po_token", e.target.value || null)}
              className={`${INPUT_CLASS} w-full`}
            />
          </Field>
                </>
              )}

              {section === "shortcuts" && (
                <div className="flex flex-col gap-0.5">
                  {SHORTCUTS.filter((s) => !s.desktopOnly).map((s) => (
                    <ShortcutRow key={s.labelKey} shortcut={s} />
                  ))}
                  {isTauri() && (
                    <>
                      <p className="mb-0.5 mt-3 px-3 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                        {t("settings.shortcutsGlobal")}
                      </p>
                      {SHORTCUTS.filter((s) => s.desktopOnly).map((s) => (
                        <ShortcutRow key={s.labelKey} shortcut={s} />
                      ))}
                      <Toggle
                        checked={form.disable_global_hotkeys}
                        onChange={(v) => set("disable_global_hotkeys", v)}
                        label={t("settings.disableGlobalHotkeys")}
                        help={<DisableGlobalHotkeysHelp />}
                        className="mt-1.5 w-full"
                      />
                    </>
                  )}
                  <p className="mt-2 px-3 text-xs text-zinc-500">
                    {t("settings.shortcutsNote")}
                  </p>
                </div>
              )}

              {section === "extension" && (
                <div className="flex flex-col gap-3">
                  <div className="flex flex-col items-center gap-2 pt-1 text-center">
                    <Puzzle size={30} className="text-violet-400" />
                    <p className="max-w-xs text-sm text-zinc-400">
                      {t("settings.extensionIntro")}
                    </p>
                  </div>
                  <div className="w-full divide-y divide-white/5 overflow-hidden rounded-xl border border-white/10 bg-white/[0.02]">
                    <div className="flex items-center justify-between gap-3 px-4 py-3">
                      <div className="flex items-center gap-3">
                        <BrowserIcon browser="firefox" className="size-5 text-zinc-200" />
                        <div className="text-sm font-medium">Firefox</div>
                      </div>
                      <a
                        href={EXT_FIREFOX_URL}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => {
                          e.preventDefault();
                          void openExternal(EXT_FIREFOX_URL);
                        }}
                        className="inline-flex items-center gap-1 rounded-lg border border-violet-500/30 bg-violet-600/20 px-2.5 py-1 text-xs text-violet-200 transition hover:bg-violet-600/30"
                      >
                        <Download size={13} /> {t("settings.extensionGet")}
                      </a>
                    </div>
                    <div className="flex items-center justify-between gap-3 px-4 py-3">
                      <div className="flex items-center gap-3">
                        <BrowserIcon browser="chrome" className="size-5 text-zinc-200" />
                        <div className="text-sm font-medium">Chrome</div>
                      </div>
                      <a
                        href={EXT_CHROME_URL}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => {
                          e.preventDefault();
                          void openExternal(EXT_CHROME_URL);
                        }}
                        className="inline-flex items-center gap-1 rounded-lg border border-violet-500/30 bg-violet-600/20 px-2.5 py-1 text-xs text-violet-200 transition hover:bg-violet-600/30"
                      >
                        <Download size={13} /> {t("settings.extensionGet")}
                      </a>
                    </div>
                  </div>
                  <a
                    href={EXT_MANUAL_URL}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => {
                      e.preventDefault();
                      void openExternal(EXT_MANUAL_URL);
                    }}
                    className="px-1 text-center text-xs text-zinc-500 transition hover:text-violet-300"
                  >
                    {t("settings.extensionManual")}
                  </a>
                  <div className="mt-1 flex items-start gap-2.5 rounded-xl border border-violet-500/15 bg-violet-500/[0.06] px-3.5 py-3">
                    <MousePointerClick
                      size={16}
                      className="mt-0.5 shrink-0 text-violet-400"
                    />
                    <p className="text-xs leading-relaxed text-zinc-300">
                      {t("settings.extensionUsage")
                        .split("Download with Yoink")
                        .flatMap((part, i) =>
                          i === 0
                            ? [part]
                            : [
                                <span
                                  key={i}
                                  className="font-medium text-violet-300"
                                >
                                  Download with Yoink
                                </span>,
                                part,
                              ],
                        )}
                    </p>
                  </div>
                </div>
              )}

              {section === "about" && (
                <>
        <div className="flex flex-col items-center gap-3 pt-1 text-center">
          <img
            src={logoUrl}
            alt="Yoink"
            className="size-16 rounded-[1.15rem] shadow-lg shadow-violet-950/50 ring-1 ring-white/10"
          />
          <div>
            <div className="text-lg font-semibold tracking-tight">Yoink</div>
            <div className="text-xs text-zinc-400">Media Downloader</div>
          </div>
        </div>

        <div className="w-full divide-y divide-white/5 overflow-hidden rounded-xl border border-white/10 bg-white/[0.02]">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <div>
              <div className="text-sm font-medium">{t("settings.version")}</div>
              <div className="font-mono text-xs text-zinc-400">
                v{__APP_VERSION__}
              </div>
            </div>
            <div className="flex items-center gap-2.5">
              {result?.status === "up-to-date" && (
                <span className="inline-flex items-center gap-1 text-xs text-emerald-400">
                  <CheckCircle2 size={13} /> {t("settings.upToDate")}
                </span>
              )}
              {result?.status === "error" && (
                <span className="text-xs text-zinc-400">
                  {t("settings.checkError")}
                </span>
              )}
              {result?.status === "tauri-unavailable" && (
                <span className="text-xs text-zinc-400">
                  {t("settings.checkDesktopOnly")}
                </span>
              )}
              {result?.status === "available" && result.autoInstallable ? (
                <button
                  type="button"
                  onClick={() => onInstall(result.update)}
                  className="inline-flex items-center gap-1 rounded-lg border border-violet-500/30 bg-violet-600/20 px-2.5 py-1 text-xs text-violet-200 transition hover:bg-violet-600/30"
                >
                  <ArrowUpCircle size={13} /> {t("settings.downloadInstall")}
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
                  className="inline-flex items-center gap-1 rounded-lg border border-violet-500/30 bg-violet-600/20 px-2.5 py-1 text-xs text-violet-200 transition hover:bg-violet-600/30"
                >
                  <ArrowUpCircle size={13} /> {t("settings.viewRelease")}
                </a>
              ) : (
                <button
                  type="button"
                  onClick={handleCheck}
                  disabled={checking}
                  className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2.5 py-1 text-xs text-zinc-300 transition hover:border-white/20 hover:text-white disabled:opacity-50"
                >
                  {checking && <Loader2 size={12} className="animate-spin" />}
                  {t("settings.checkUpdates")}
                </button>
              )}
            </div>
          </div>

          {ytdlp && !ytdlp.error && ytdlp.current !== "unknown" && (
            <div className="flex items-center justify-between gap-3 px-4 py-3">
              <div>
                <div className="text-sm font-medium">yt-dlp</div>
                <div className="font-mono text-xs text-zinc-400">
                  {ytdlp.current}
                </div>
              </div>
              {ytdlp.update_available && ytdlp.latest ? (
                <span className="text-xs text-violet-300">
                  {t("settings.updateAvailable", { version: ytdlp.latest })}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-xs text-emerald-400/80">
                  <CheckCircle2 size={12} /> {t("settings.upToDate")}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex w-full flex-col gap-0.5">
          <button
            type="button"
            onClick={onShowWhatsNew}
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-zinc-200 transition hover:bg-white/5"
          >
            <Sparkles size={16} className="shrink-0 text-violet-400" />
            {t("whatsNew.button")}
          </button>
          <a
            href="https://github.com/ayozetr"
            target="_blank"
            rel="noreferrer"
            onClick={(e) => {
              e.preventDefault();
              void openExternal("https://github.com/ayozetr");
            }}
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-zinc-200 transition hover:bg-white/5"
          >
            <GithubIcon className="size-4 shrink-0" />
            <span>
              {t("settings.developedBy")}{" "}
              <strong className="font-medium text-white">ayozetr</strong>
            </span>
          </a>
          <a
            href="https://ko-fi.com/ayozetr"
            target="_blank"
            rel="noreferrer"
            onClick={(e) => {
              e.preventDefault();
              void openExternal("https://ko-fi.com/ayozetr");
            }}
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-zinc-200 transition hover:bg-white/5 hover:text-violet-200"
          >
            <Coffee size={16} className="shrink-0 text-violet-400" />
            {t("settings.donate")}
          </a>
        </div>
        <div className="mt-auto flex flex-col items-start gap-1">
          <button
            type="button"
            onClick={() => setLicensesOpen(true)}
            className="self-start px-3 text-[11px] text-zinc-500 transition hover:text-zinc-300"
          >
            {t("settings.openSourceLicenses")}
          </button>
          <button
            type="button"
            onClick={() => setTermsOpen(true)}
            className="self-start px-3 text-[11px] text-zinc-500 transition hover:text-zinc-300"
          >
            {t("settings.terms")}
          </button>
        </div>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 border-t border-white/10 px-6 py-4">
          {error && <p className="text-sm text-red-400">{error}</p>}
          <div className="ml-auto flex gap-3">
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
        </div>
      </GlassPanel>
    </div>
    {termsOpen && <TermsModal onClose={() => setTermsOpen(false)} />}
    {licensesOpen && <LicensesModal onClose={() => setLicensesOpen(false)} />}
    </>
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
  className = "",
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
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

// "Send to Yoink" companion extension — the generic AMO path auto-localizes.
const EXT_FIREFOX_URL = "https://addons.mozilla.org/firefox/addon/send-to-yoink/";
// Chrome Web Store — the item id is permanent; the id-only path redirects to the
// slugged listing, so it stays valid regardless of the store's display slug.
const EXT_CHROME_URL =
  "https://chromewebstore.google.com/detail/ccbngfpojjboddajeialdgppooagdhkp";
// Manual-install builds: a rolling pre-release with stable, version-less asset
// URLs, so this link never changes across Yoink app releases.
const EXT_MANUAL_URL =
  "https://github.com/ayozetr/yoink-app/releases/tag/ext-latest";

/** A "?" button that reveals `children` in a popover, anchored with `fixed` so
 *  the modal's overflow can't clip it. */
function HelpPopover({
  children,
  label,
}: {
  children: ReactNode;
  label?: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const WIDTH = 288; // w-72

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
    // A scroll/resize moves the anchor button, so the fixed popover would float
    // at a stale spot — dismiss it (scrolling inside the popover itself is fine).
    const onScroll = (event: Event) => {
      if (popRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    };
    const dismiss = () => setOpen(false);
    // Capture phase: the modal panel calls stopPropagation() on click.
    window.addEventListener("click", onPointer, true);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", dismiss);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", onPointer, true);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", dismiss);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={label ?? t("settings.cookiesHelp")}
        title={label ?? t("settings.cookiesHelp")}
        className="inline-flex text-zinc-500 transition hover:text-zinc-200"
      >
        <HelpCircle size={13} />
      </button>
      {open && pos && (
        <div
          ref={popRef}
          data-popover="true"
          style={{ position: "fixed", top: pos.top, left: pos.left, width: WIDTH }}
          className="z-[200] rounded-lg border border-white/10 bg-[#1a1d27] p-3 text-xs leading-relaxed text-zinc-300 shadow-xl"
        >
          {children}
        </div>
      )}
    </>
  );
}

/** "?" help for the cookies.txt file field — how to generate it. */
function CookiesHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover>
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
    </HelpPopover>
  );
}

/** "?" help for the browser cookies field — caveats for reading them. */
function BrowserCookiesHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover>
      {t("settings.cookiesBrowserHelpIntro")}
      <ul className="mt-2 list-disc space-y-1 pl-4">
        <li>{t("settings.cookiesBrowserHelpClosed")}</li>
        <li>{t("settings.cookiesBrowserHelpLogin")}</li>
      </ul>
    </HelpPopover>
  );
}

/** "?" help for SponsorBlock — what it is and how it works (brief). */
function SponsorBlockHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.sponsorblockHelpTitle")}>
      {t("settings.sponsorblockHelp")}
    </HelpPopover>
  );
}

/** "?" help for the .nfo sidecars option — what an NFO file is for. */
function NfoHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.nfoSidecars")}>
      {t("settings.nfoSidecarsHelp")}
    </HelpPopover>
  );
}

/** "?" help for the music-folders option — the Artist/Album layout + folder nfo. */
function MusicFoldersHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.musicFolders")}>
      {t("settings.musicFoldersHelp")}
    </HelpPopover>
  );
}

/** "?" help for loudness normalization — what it does + the target level. */
function NormalizeAudioHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.normalizeAudio")}>
      {t("settings.normalizeAudioHint")}
    </HelpPopover>
  );
}

function MinimizeToTrayHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.minimizeToTray")}>
      {t("settings.minimizeToTrayHelp")}
    </HelpPopover>
  );
}

function DisableGlobalHotkeysHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.disableGlobalHotkeys")}>
      {t("settings.disableGlobalHotkeysHelp")}
    </HelpPopover>
  );
}


/** "?" help for the default audio format: FLAC/WAV availability caveat. */
function AudioFormatHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.defaultAudioFormat")}>
      {t("settings.defaultAudioFormatHint")}
    </HelpPopover>
  );
}

/** "?" help for embed-subtitles: only MKV can carry them cleanly. */
function EmbedSubsHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.defaultEmbedSubs")}>
      {t("settings.defaultEmbedSubsHint")}
    </HelpPopover>
  );
}

/** "?" help for the lyrics option — where lyrics come from + how they're stored. */
function LyricsHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.fetchLyrics")}>
      {t("settings.fetchLyricsHelp")}
    </HelpPopover>
  );
}

/** "?" help for the synced .lrc sidecar sub-option. */
function LyricsLrcHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.lyricsLrc")}>
      {t("settings.lyricsLrcHelp")}
    </HelpPopover>
  );
}

/** "?" help for the proxy field. */
function ProxyHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.proxy")}>{t("settings.proxyHelp")}</HelpPopover>
  );
}

function PoTokenHelp() {
  const { t } = useTranslation();
  return (
    <HelpPopover label={t("settings.poToken")}>{t("settings.poTokenHelp")}</HelpPopover>
  );
}
