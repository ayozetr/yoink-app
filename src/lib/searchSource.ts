import type { SearchSource } from "./api";

// Searchable platforms for the URL-field typeahead, their display names, and the
// persisted choice (shared so the header toggle and the URL field agree).
export const SEARCH_SOURCES: SearchSource[] = ["youtube", "soundcloud"];
export const SOURCE_NAMES: Record<SearchSource, string> = {
  youtube: "YouTube",
  soundcloud: "SoundCloud",
};
const SOURCE_KEY = "yoink-search-source";

export function loadSearchSource(): SearchSource {
  try {
    return localStorage.getItem(SOURCE_KEY) === "soundcloud"
      ? "soundcloud"
      : "youtube";
  } catch {
    return "youtube";
  }
}

export function persistSearchSource(source: SearchSource): void {
  try {
    localStorage.setItem(SOURCE_KEY, source);
  } catch {
    // localStorage unavailable — the choice just won't persist.
  }
}
