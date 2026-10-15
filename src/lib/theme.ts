import { useCallback, useEffect, useState } from "react";

/**
 * App theme preference: "system" follows the OS, "dark"/"light" force a look.
 * The palette lives as CSS custom properties in index.css: the dark values are
 * the defaults on `:root`, and the light values apply under
 * `html[data-theme="light"]`. So applying a theme is just setting (light) or
 * clearing (dark) that attribute — "system" resolves to one of those from
 * `prefers-color-scheme` and re-resolves when the OS switches.
 *
 * The choice is persisted per-viewer under the `yoink-theme` localStorage key.
 * A missing/invalid key means "system".
 */
export type ThemePref = "system" | "dark" | "light";

const STORAGE_KEY = "yoink-theme";

/** Whether the OS currently prefers a light appearance (safe if unsupported). */
function systemPrefersLight(): boolean {
  try {
    return window.matchMedia("(prefers-color-scheme: light)").matches;
  } catch {
    return false;
  }
}

/** Resolve a preference to the concrete look to paint. */
function resolve(pref: ThemePref): "dark" | "light" {
  if (pref === "system") return systemPrefersLight() ? "light" : "dark";
  return pref;
}

/** Read the persisted preference, defaulting to "system". Safe if storage is blocked. */
export function loadThemePref(): ThemePref {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "light" || v === "dark" || v === "system" ? v : "system";
  } catch {
    return "system";
  }
}

/** Reflect the preference onto <html> (light sets the attribute; dark clears it). */
export function applyTheme(pref: ThemePref): void {
  const root = document.documentElement;
  if (resolve(pref) === "light") root.setAttribute("data-theme", "light");
  else root.removeAttribute("data-theme");
}

/** Persist the preference (best-effort — storage may be unavailable). */
function persistTheme(pref: ThemePref): void {
  try {
    localStorage.setItem(STORAGE_KEY, pref);
  } catch {
    // Private window / blocked storage — the choice just won't survive a reload.
  }
}

/** Stateful theme hook: current preference + a setter, applied to the document. */
export function useTheme(): {
  theme: ThemePref;
  setTheme: (t: ThemePref) => void;
} {
  const [theme, setThemeState] = useState<ThemePref>(loadThemePref);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // While on "system", re-apply when the OS appearance flips.
  useEffect(() => {
    if (theme !== "system") return;
    let mq: MediaQueryList;
    try {
      mq = window.matchMedia("(prefers-color-scheme: light)");
    } catch {
      return;
    }
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback((next: ThemePref) => {
    setThemeState(next);
    persistTheme(next);
  }, []);

  return { theme, setTheme };
}
