import { ChevronDown, ClipboardPaste, Loader2, Search } from "lucide-react";
import { lazy, memo, Suspense, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../../../components/ui/Button";
import { Thumbnail } from "../../../components/ui/Thumbnail";
import { searchYoutube, type SearchSource } from "../../../lib/api";
import { SEARCH_SOURCES, SOURCE_NAMES } from "../../../lib/searchSource";
import { SearchSourceIcon } from "./SearchSourceIcon";
import type { PlaylistEntry } from "../../../types/download";

const SupportedSitesModal = lazy(() =>
  import("./SupportedSitesModal").then((m) => ({
    default: m.SupportedSitesModal,
  })),
);

interface UrlInputProps {
  value: string;
  onChange: (value: string) => void;
  onAnalyze: () => void;
  /** Picking a search result: analyze that video directly. */
  onSelectResult: (entry: PlaylistEntry) => void;
  /** Platform the typeahead searches (selected in the field's source picker). */
  searchSource: SearchSource;
  onSearchSourceChange: (source: SearchSource) => void;
  loading?: boolean;
}

const MIN_CHARS = 3;
const DEBOUNCE_MS = 400;

// Stable ids wiring the combobox input to its listbox + options (ARIA).
const LISTBOX_ID = "yoink-url-listbox";
const optionId = (i: number) => `yoink-url-option-${i}`;

// Small LRU cache of query -> results so re-typing or re-visiting a query
// doesn't relaunch yt-dlp (~1s each). Entries carry a TTL so a query whose
// results have since changed isn't served stale for the whole session.
const cache = new Map<string, { results: PlaylistEntry[]; expires: number }>();
const CACHE_MAX = 25;
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 min

function cacheGet(q: string): PlaylistEntry[] | undefined {
  const hit = cache.get(q);
  if (!hit) return undefined;
  if (hit.expires <= Date.now()) {
    cache.delete(q); // expired — force a fresh search
    return undefined;
  }
  cache.delete(q);
  cache.set(q, hit); // bump to most-recently-used
  return hit.results;
}

function cacheSet(q: string, r: PlaylistEntry[]): void {
  cache.delete(q);
  cache.set(q, { results: r, expires: Date.now() + CACHE_TTL_MS });
  if (cache.size > CACHE_MAX) {
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) cache.delete(oldest);
  }
}

const viewsFmt = new Intl.NumberFormat(undefined, {
  notation: "compact",
  maximumFractionDigits: 1,
});

/** A bare http(s) URL, a spaceless domain/path, or an IPv4 — else it's a search. */
function looksLikeUrl(s: string): boolean {
  const t = s.trim();
  if (/^https?:\/\//i.test(t)) return true;
  if (t.includes(" ")) return false;
  return (
    /\.[a-z]{2,}(\/|$|\?|:)/i.test(t) || /^\d{1,3}(\.\d{1,3}){3}(:|\/|$)/.test(t)
  );
}

function isSearchQuery(s: string): boolean {
  return s.trim().length >= MIN_CHARS && !looksLikeUrl(s);
}

/** URL field with an in-field source picker (YouTube/SoundCloud) and live search:
 *  type a query → pick a result; paste a URL → analyze. */
export const UrlInput = memo(function UrlInput({
  value,
  onChange,
  onAnalyze,
  onSelectResult,
  searchSource,
  onSearchSourceChange,
  loading,
}: UrlInputProps) {
  const { t } = useTranslation();
  const [results, setResults] = useState<PlaylistEntry[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  // The in-field source dropdown (YouTube / SoundCloud).
  const [sourceMenuOpen, setSourceMenuOpen] = useState(false);
  const [showSites, setShowSites] = useState(false);
  // Tracks the active search platform to detect a flip (from the source picker).
  const [prevSource, setPrevSource] = useState(searchSource);
  // Index of the option with real focus, for aria-selected (managed-focus combobox).
  const [activeIdx, setActiveIdx] = useState(-1);
  const boxRef = useRef<HTMLDivElement>(null);
  const sourceRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // The result buttons, in order — for moving real focus with the arrow keys.
  const optionEls = () =>
    Array.from(
      listRef.current?.querySelectorAll<HTMLButtonElement>('[role="option"]') ??
        [],
    );

  const query = value.trim();
  const isSearch = isSearchQuery(value);
  const disabled = loading || query.length === 0;
  const showDropdown = open && isSearch;
  // Cache key is per-source so YouTube and SoundCloud hits never collide.
  const ckey = (q: string) => `${searchSource} ${q}`;

  // The platform changed (source picker): adjust the dropdown during render.
  if (searchSource !== prevSource) {
    setPrevSource(searchSource);
    if (isSearch) {
      const cached = cacheGet(ckey(query));
      setResults(cached ?? []);
      setSearching(!cached);
      setError(false);
      setOpen(true);
    }
  }

  // Focus the URL field on mount — the primary action is "paste a link".
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Debounced live search.
  useEffect(() => {
    const key = ckey(query);
    if (!isSearch || cacheGet(key) !== undefined) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void searchYoutube(query, searchSource, controller.signal)
        .then((r) => {
          if (controller.signal.aborted) return;
          cacheSet(key, r);
          setResults(r);
          setSearching(false);
        })
        .catch(() => {
          if (controller.signal.aborted) return;
          setResults([]);
          setSearching(false);
          setError(true);
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, isSearch, searchSource]);

  // Close the result dropdown when clicking outside the field.
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onPointer);
    return () => window.removeEventListener("mousedown", onPointer);
  }, [open]);

  // Close the source menu when clicking outside it.
  useEffect(() => {
    if (!sourceMenuOpen) return;
    const onPointer = (event: MouseEvent) => {
      if (!sourceRef.current?.contains(event.target as Node))
        setSourceMenuOpen(false);
    };
    window.addEventListener("mousedown", onPointer);
    return () => window.removeEventListener("mousedown", onPointer);
  }, [sourceMenuOpen]);

  const handleChange = (next: string) => {
    onChange(next);
    setError(false);
    if (!isSearchQuery(next)) {
      setOpen(false);
      setResults([]);
      setSearching(false);
      return;
    }
    setOpen(true);
    const nextQ = next.trim();
    if (nextQ === query) return; // only whitespace changed; effect won't re-run
    const cached = cacheGet(ckey(nextQ));
    if (cached) {
      setResults(cached);
      setSearching(false);
    } else {
      setResults([]);
      setSearching(true);
    }
  };

  const handlePaste = async () => {
    try {
      const text = (await navigator.clipboard.readText()).trim();
      if (text) handleChange(text);
    } catch {
      // Clipboard unavailable or permission denied — ignore silently.
    }
  };

  const choose = (entry: PlaylistEntry) => {
    setOpen(false);
    onSelectResult(entry);
  };

  // Enter / the button on a URL analyzes it; on a search it takes the first hit.
  const submit = () => {
    if (isSearch) {
      if (results[0]) choose(results[0]);
    } else if (!disabled) {
      onAnalyze();
    }
  };

  const meta = (entry: PlaylistEntry): string =>
    [
      entry.uploader,
      entry.view_count != null
        ? t("url.views", { n: viewsFmt.format(entry.view_count) })
        : null,
    ]
      .filter(Boolean)
      .join(" · ");

  const placeholder = t("url.placeholder");

  return (
    <>
      <div>
        <div className="flex gap-3">
          <div ref={boxRef} className="relative flex-1">
            {/* One field: a source picker + the URL/search input + paste. */}
            <div className="url-field flex h-14 items-center gap-1.5 rounded-2xl border border-line/10 bg-surface pl-1.5 pr-2 transition focus-within:border-accent">
              {/* Source picker (YouTube / SoundCloud) */}
              <div ref={sourceRef} className="relative shrink-0">
                <button
                  type="button"
                  onClick={() => setSourceMenuOpen((v) => !v)}
                  aria-haspopup="listbox"
                  aria-expanded={sourceMenuOpen}
                  aria-label={t("url.searchSource")}
                  className="flex h-11 items-center gap-2 rounded-xl px-3 text-sm font-medium text-fg transition hover:bg-surface-hover focus-visible:bg-surface-hover"
                >
                  <SearchSourceIcon source={searchSource} className="size-4" />
                  <span className="hidden sm:inline">
                    {SOURCE_NAMES[searchSource]}
                  </span>
                  <ChevronDown
                    size={14}
                    className={`text-fg-dim transition-transform ${sourceMenuOpen ? "rotate-180" : ""}`}
                  />
                </button>
                {sourceMenuOpen && (
                  <div
                    role="listbox"
                    aria-label={t("url.searchSource")}
                    className="absolute left-0 top-[calc(100%+0.75rem)] z-40 w-44 rounded-xl border border-line/10 bg-surface p-1 shadow-xl"
                  >
                    {SEARCH_SOURCES.map((s) => (
                      <button
                        key={s}
                        type="button"
                        role="option"
                        aria-selected={s === searchSource}
                        onClick={() => {
                          onSearchSourceChange(s);
                          setSourceMenuOpen(false);
                          inputRef.current?.focus();
                        }}
                        className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition ${
                          s === searchSource
                            ? "bg-accent/15 text-fg"
                            : "text-fg-dim hover:bg-surface-hover hover:text-fg"
                        }`}
                      >
                        <SearchSourceIcon source={s} className="size-4" />
                        {SOURCE_NAMES[s]}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="h-6 w-px shrink-0 bg-line/10" />

              <input
                ref={inputRef}
                id="yoink-url-input"
                type="text"
                role="combobox"
                aria-label={placeholder}
                aria-autocomplete="list"
                aria-expanded={showDropdown}
                aria-controls={showDropdown ? LISTBOX_ID : undefined}
                placeholder={placeholder}
                value={value}
                onChange={(event) => handleChange(event.target.value)}
                onFocusCapture={() => {
                  setActiveIdx(-1);
                  if (isSearch) setOpen(true);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    setOpen(false);
                    return;
                  }
                  if (event.key === "ArrowDown" && showDropdown && results.length) {
                    event.preventDefault();
                    optionEls()[0]?.focus();
                    return;
                  }
                  if (event.key === "Enter") submit();
                }}
                className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-fg-faint"
              />

              <button
                type="button"
                onClick={handlePaste}
                aria-label={t("url.paste")}
                title={t("url.paste")}
                className="shrink-0 rounded-lg p-1.5 text-fg-dim transition hover:bg-surface-hover hover:text-fg focus-visible:bg-surface-hover focus-visible:text-fg"
              >
                <ClipboardPaste size={18} />
              </button>
            </div>

            {showDropdown && (
              <div
                ref={listRef}
                id={LISTBOX_ID}
                role="listbox"
                aria-label={placeholder}
                className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-30 max-h-96 overflow-y-auto rounded-2xl border border-line/10 bg-surface p-1 shadow-xl"
              >
                {searching && results.length === 0 ? (
                  <div className="flex items-center gap-2 px-3 py-3 text-sm text-fg-dim">
                    <Loader2 size={16} className="animate-spin" />
                    {t("url.searching", { source: SOURCE_NAMES[searchSource] })}
                  </div>
                ) : error && results.length === 0 ? (
                  <div className="px-3 py-3 text-sm text-red-300">
                    {t("url.searchError")}
                  </div>
                ) : results.length === 0 ? (
                  <div className="px-3 py-3 text-sm text-fg-dim">
                    {t("url.noResults")}
                  </div>
                ) : (
                  results.map((entry, i) => (
                    <button
                      key={entry.id || entry.url}
                      id={optionId(i)}
                      role="option"
                      aria-selected={activeIdx === i}
                      type="button"
                      onClick={() => choose(entry)}
                      onFocus={() => setActiveIdx(i)}
                      onKeyDown={(event) => {
                        const els = optionEls();
                        if (event.key === "ArrowDown") {
                          event.preventDefault();
                          (els[i + 1] ?? els[i])?.focus();
                        } else if (event.key === "ArrowUp") {
                          event.preventDefault();
                          if (i === 0) inputRef.current?.focus();
                          else els[i - 1]?.focus();
                        } else if (event.key === "Escape") {
                          setOpen(false);
                          inputRef.current?.focus();
                        }
                      }}
                      className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition hover:bg-surface-hover focus:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent"
                    >
                      <div className="relative h-10 w-[72px] shrink-0 overflow-hidden rounded-md bg-black/40">
                        {entry.thumbnail_url && (
                          <Thumbnail
                            src={entry.thumbnail_url}
                            alt={entry.title}
                            className="h-full w-full object-cover"
                            fallback={null}
                          />
                        )}
                        {entry.duration_string && (
                          <span className="absolute bottom-0.5 right-0.5 rounded bg-black/80 px-1 text-[10px] text-white">
                            {entry.duration_string}
                          </span>
                        )}
                      </div>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm">
                          {entry.title}
                        </span>
                        {meta(entry) && (
                          <span className="block truncate text-xs text-fg-dim">
                            {meta(entry)}
                          </span>
                        )}
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          <Button
            onClick={submit}
            disabled={disabled}
            className="h-14 px-6 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Search size={18} />
            )}
            {loading ? t("url.analyzing") : t("url.analyze")}
          </Button>
        </div>

        {/* Supported sites — a quiet link under the field. */}
        <div className="mt-2.5 flex justify-end">
          <button
            type="button"
            onClick={() => setShowSites(true)}
            className="text-xs text-fg-faint underline-offset-2 transition hover:text-fg-dim hover:underline"
          >
            {t("sites.title")}
          </button>
        </div>
      </div>

      {showSites && (
        <Suspense fallback={null}>
          <SupportedSitesModal onClose={() => setShowSites(false)} />
        </Suspense>
      )}
    </>
  );
});
