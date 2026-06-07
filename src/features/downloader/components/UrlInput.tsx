import { ClipboardPaste, Link2, Loader2, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { GlassPanel } from "../../../components/ui/GlassPanel";
import { Button } from "../../../components/ui/Button";
import { Thumbnail } from "../../../components/ui/Thumbnail";
import { searchYoutube } from "../../../lib/api";
import type { PlaylistEntry } from "../../../types/download";

interface UrlInputProps {
  value: string;
  onChange: (value: string) => void;
  onAnalyze: () => void;
  /** Picking a search result: analyze that video directly. */
  onSelectResult: (entry: PlaylistEntry) => void;
  loading?: boolean;
}

const MIN_CHARS = 3;
const DEBOUNCE_MS = 400;

// Small LRU cache of query -> results so re-typing or re-visiting a query
// doesn't relaunch yt-dlp (~1s each).
const cache = new Map<string, PlaylistEntry[]>();
const CACHE_MAX = 25;

function cacheGet(q: string): PlaylistEntry[] | undefined {
  const hit = cache.get(q);
  if (hit) {
    cache.delete(q);
    cache.set(q, hit); // bump to most-recently-used
  }
  return hit;
}

function cacheSet(q: string, r: PlaylistEntry[]): void {
  cache.delete(q);
  cache.set(q, r);
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

/** URL field with live YouTube search: type a query → pick a result to analyze. */
export function UrlInput({
  value,
  onChange,
  onAnalyze,
  onSelectResult,
  loading,
}: UrlInputProps) {
  const { t } = useTranslation();
  const [results, setResults] = useState<PlaylistEntry[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const boxRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);

  const query = value.trim();
  const isSearch = isSearchQuery(value);
  const disabled = loading || query.length === 0;
  const showDropdown = open && isSearch;

  // Debounced live search. setState happens only inside the timer/promise (never
  // synchronously in the effect body), so it can't trip cascading renders. A
  // cached query is already shown by handleChange, so the effect skips the fetch.
  useEffect(() => {
    if (!isSearch || cache.has(query)) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void searchYoutube(query, controller.signal)
        .then((r) => {
          if (controller.signal.aborted) return;
          cacheSet(query, r);
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
  }, [query, isSearch]);

  // Keep the keyboard-highlighted option scrolled into view.
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  // Close the dropdown when clicking outside the field.
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onPointer);
    return () => window.removeEventListener("mousedown", onPointer);
  }, [open]);

  // Drive the dropdown from the edit event (not an effect): reset selection,
  // show cached results instantly or the spinner, and clear stale results when
  // the query changes so a result from a previous search can't be clicked.
  const handleChange = (next: string) => {
    onChange(next);
    setActiveIndex(-1);
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
    const cached = cacheGet(nextQ);
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
    setActiveIndex(-1);
    onSelectResult(entry);
  };

  // Enter / the button: analyze a URL, or pick the highlighted (or top) hit.
  const submit = () => {
    if (isSearch) {
      const pick = activeIndex >= 0 ? results[activeIndex] : results[0];
      if (pick && open) choose(pick);
    } else if (!disabled) {
      onAnalyze();
    }
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setOpen(false);
      setActiveIndex(-1);
      return;
    }
    if (showDropdown && results.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, results.length - 1));
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((i) => (i <= 0 ? results.length - 1 : i - 1));
        return;
      }
    }
    if (event.key === "Enter") submit();
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

  return (
    <GlassPanel className="p-5">
      <div className="flex gap-3">
        <div ref={boxRef} className="relative flex-1">
          {isSearch ? (
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 size-5 text-zinc-500" />
          ) : (
            <Link2 className="absolute left-4 top-1/2 -translate-y-1/2 size-5 text-zinc-500" />
          )}
          <input
            type="text"
            role="combobox"
            aria-expanded={showDropdown}
            aria-controls="yt-search-listbox"
            aria-autocomplete="list"
            aria-activedescendant={
              showDropdown && activeIndex >= 0
                ? `yt-search-opt-${activeIndex}`
                : undefined
            }
            aria-label={t("url.placeholder")}
            placeholder={t("url.placeholder")}
            value={value}
            onChange={(event) => handleChange(event.target.value)}
            onFocusCapture={() => {
              if (isSearch) setOpen(true);
            }}
            onKeyDown={onKeyDown}
            className="w-full h-14 pl-12 pr-12 rounded-2xl bg-surface border border-white/10 outline-none focus:border-violet-500 text-sm"
          />
          <button
            type="button"
            onClick={handlePaste}
            aria-label={t("url.paste")}
            title={t("url.paste")}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-zinc-400 transition hover:bg-white/10 hover:text-white"
          >
            <ClipboardPaste size={18} />
          </button>

          {showDropdown && (
            <div
              id="yt-search-listbox"
              role="listbox"
              className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-30 max-h-96 overflow-y-auto rounded-2xl border border-white/10 bg-[#1a1d27] shadow-xl"
            >
              {searching && results.length === 0 ? (
                <div className="flex items-center gap-2 px-4 py-3 text-sm text-zinc-400">
                  <Loader2 size={16} className="animate-spin" />
                  {t("url.searching")}
                </div>
              ) : error && results.length === 0 ? (
                <div className="px-4 py-3 text-sm text-red-300">
                  {t("url.searchError")}
                </div>
              ) : results.length === 0 ? (
                <div className="px-4 py-3 text-sm text-zinc-400">
                  {t("url.noResults")}
                </div>
              ) : (
                results.map((entry, i) => (
                  <button
                    key={entry.id || entry.url}
                    ref={i === activeIndex ? activeRef : undefined}
                    id={`yt-search-opt-${i}`}
                    role="option"
                    aria-selected={i === activeIndex}
                    type="button"
                    tabIndex={-1}
                    onClick={() => choose(entry)}
                    onMouseMove={() => setActiveIndex(i)}
                    className={`flex w-full items-center gap-3 px-3 py-2 text-left transition ${
                      i === activeIndex ? "bg-white/10" : "hover:bg-white/5"
                    }`}
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
                      <span className="block truncate text-sm">{entry.title}</span>
                      {meta(entry) && (
                        <span className="block truncate text-xs text-zinc-500">
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
    </GlassPanel>
  );
}
