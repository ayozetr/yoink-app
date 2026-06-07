import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import { en } from "./locales/en";
import { es } from "./locales/es";

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      es: { translation: es },
    },
    fallbackLng: "en",
    supportedLngs: ["en", "es"],
    load: "languageOnly", // map "es-ES" -> "es"
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
