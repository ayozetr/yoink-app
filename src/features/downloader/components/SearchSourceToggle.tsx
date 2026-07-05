import { Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SearchSource } from "../../../lib/api";
import { SEARCH_SOURCES, SOURCE_NAMES } from "../../../lib/searchSource";
import { SearchSourceIcon } from "./SearchSourceIcon";

interface SearchSourceToggleProps {
  value: SearchSource;
  onChange: (source: SearchSource) => void;
}

/** Segmented control to pick which platform the URL-field typeahead searches. */
export function SearchSourceToggle({ value, onChange }: SearchSourceToggleProps) {
  const { t } = useTranslation();
  return (
    <div
      role="group"
      aria-label={t("url.searchSource")}
      className="inline-flex items-center rounded-xl border border-white/10 bg-white/[0.06] p-1"
    >
      <Search
        className="mx-1.5 size-4 shrink-0 text-zinc-500"
        aria-hidden="true"
      />
      {SEARCH_SOURCES.map((source) => (
        <button
          key={source}
          type="button"
          aria-pressed={value === source}
          aria-label={SOURCE_NAMES[source]}
          title={SOURCE_NAMES[source]}
          onClick={() => onChange(source)}
          className={`rounded-lg px-2.5 py-1.5 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-500 ${
            value === source
              ? "bg-violet-600 text-white"
              : "text-zinc-400 hover:text-white"
          }`}
        >
          <SearchSourceIcon source={source} className="size-4" />
        </button>
      ))}
    </div>
  );
}
