import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import { en } from "./locales/en";
import { es } from "./locales/es";
import { fr } from "./locales/fr";
import { de } from "./locales/de";
import { it } from "./locales/it";
import { pt } from "./locales/pt";
import { zh } from "./locales/zh";
import { ja } from "./locales/ja";
import { ko } from "./locales/ko";
import { ru } from "./locales/ru";
import { pl } from "./locales/pl";
import { uk } from "./locales/uk";
import { id } from "./locales/id";
import { hi } from "./locales/hi";

// English is the reference shape; every other locale must provide the same keys
// (a missing key is a compile error here, not a silent fall-through at runtime).
// Widen the `as const` string literals to plain `string` so any translation is
// accepted as a value, while the key structure must still match exactly.
type Stringify<T> = {
  [K in keyof T]: T[K] extends string ? string : Stringify<T[K]>;
};
type Translation = Stringify<typeof en>;
const resources: Record<string, { translation: Translation }> = {
  en: { translation: en },
  es: { translation: es },
  fr: { translation: fr },
  de: { translation: de },
  it: { translation: it },
  pt: { translation: pt },
  zh: { translation: zh },
  ja: { translation: ja },
  ko: { translation: ko },
  ru: { translation: ru },
  pl: { translation: pl },
  uk: { translation: uk },
  id: { translation: id },
  hi: { translation: hi },
};

/** Locale codes available in the language selector, in display order. */
export const SUPPORTED_LANGUAGES = Object.keys(resources);

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: "en",
    supportedLngs: SUPPORTED_LANGUAGES,
    load: "languageOnly", // map "es-ES" -> "es", "pt-BR" -> "pt", …
    nonExplicitSupportedLngs: true,
    interpolation: { escapeValue: false },
    detection: {
      // Use the saved choice, else the system/browser language.
      order: ["localStorage", "navigator"],
      // Don't auto-cache the detected language: no saved key means "System"
      // (follow the OS), which is the default on first run. The Settings
      // selector persists an explicit choice itself.
      caches: [],
      lookupLocalStorage: "yoink-lang",
    },
  });

// Keep <html lang> in sync with the active language (a11y / screen readers).
const syncHtmlLang = (lng: string) => {
  if (typeof document !== "undefined") {
    document.documentElement.lang = lng.split("-")[0];
  }
};
i18n.on("languageChanged", syncHtmlLang);
syncHtmlLang(i18n.language || "en");

export default i18n;
