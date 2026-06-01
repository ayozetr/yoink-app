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
      caches: ["localStorage"],
      lookupLocalStorage: "yoink-lang",
    },
  });

export default i18n;
