import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import { en } from "./locales/en";
// Type-only: enforces that every lazy locale has the full English key set.
import type {} from "./localeCompleteness";

/** Locale codes available in the language selector, in display order. */
export const SUPPORTED_LANGUAGES: string[] = [
  "en", "es", "fr", "de", "it", "pt", "ru", "pl", "uk", "id", "hi", "zh", "ja", "ko",
];

// Lazy importers: each non-English locale is split into its own chunk and only
// fetched when it becomes the active language (English is bundled as the
// always-available fallback). Keeps the initial bundle small despite 14 locales.
const localeLoaders = import.meta.glob("./locales/*.ts");

async function loadLocale(lng: string): Promise<void> {
  if (lng === "en" || i18n.hasResourceBundle(lng, "translation")) return;
  const loader = localeLoaders[`./locales/${lng}.ts`];
  if (!loader) return;
  const mod = (await loader()) as Record<string, unknown>;
  const bundle = (mod[lng] ?? Object.values(mod)[0]) as Record<string, unknown>;
  i18n.addResourceBundle(lng, "translation", bundle, true, true);
}

/** Initial language: the saved choice, else the OS language if supported, else English. */
function detectInitialLanguage(): string {
  try {
    const saved = localStorage.getItem("yoink-lang");
    if (saved && SUPPORTED_LANGUAGES.includes(saved)) return saved;
  } catch {
    // localStorage unavailable — fall through to navigator.
  }
  const nav = (typeof navigator !== "undefined" ? navigator.language : "en").split(
    "-",
  )[0];
  return SUPPORTED_LANGUAGES.includes(nav) ? nav : "en";
}

const initialLanguage = detectInitialLanguage();

await i18n.use(initReactI18next).init({
  resources: { en: { translation: en } },
  lng: initialLanguage,
  fallbackLng: "en",
  supportedLngs: SUPPORTED_LANGUAGES,
  interpolation: { escapeValue: false },
});
// Load the active language's chunk before the app renders (no English flash).
await loadLocale(initialLanguage);

/** Switch language, fetching its chunk first if it isn't loaded yet. */
export async function changeLanguage(lng: string): Promise<void> {
  await loadLocale(lng);
  await i18n.changeLanguage(lng);
}

// Keep <html lang> in sync with the active language (a11y / screen readers).
const syncHtmlLang = (lng: string) => {
  if (typeof document !== "undefined") {
    document.documentElement.lang = lng.split("-")[0];
  }
};
i18n.on("languageChanged", syncHtmlLang);
syncHtmlLang(i18n.language || "en");

export default i18n;
