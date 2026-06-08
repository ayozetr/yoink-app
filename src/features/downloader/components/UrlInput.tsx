import { ClipboardPaste, Link2, Loader2, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
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

// Stable ids wiring the combobox input to its listbox + options (ARIA).
const LISTBOX_ID = "yoink-url-listbox";
const optionId = (i: number) => `yoink-url-option-${i}`;

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
  // Index of the option with real focus, for aria-selected (managed-focus combobox).
  const [activeIdx, setActiveIdx] = useState(-1);
  const boxRef = useRef<HTMLDivElement>(null);
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

  // Focus the URL field on mount — the primary action is "paste a link".
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

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

  // Close the dropdown when clicking outside the field.
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onPointer);
    return () => window.removeEventListener("mousedown", onPointer);
  }, [open]);

  // Drive the dropdown from the edit event (not an effect): show cached results
  // instantly or the spinner, and clear stale results when the query changes so
  // a result from a previous search can't be clicked.
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
            ref={inputRef}
            id="yoink-url-input"
            type="text"
            role="combobox"
            aria-label={t("url.placeholder")}
            aria-autocomplete="list"
            aria-expanded={showDropdown}
            aria-controls={showDropdown ? LISTBOX_ID : undefined}
            placeholder={t("url.placeholder")}
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
              ref={listRef}
              id={LISTBOX_ID}
              role="listbox"
              aria-label={t("url.placeholder")}
              className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-30 max-h-96 overflow-y-auto rounded-2xl border border-white/10 bg-[#1a1d27] p-1 shadow-xl"
            >
              {searching && results.length === 0 ? (
                <div className="flex items-center gap-2 px-3 py-3 text-sm text-zinc-400">
                  <Loader2 size={16} className="animate-spin" />
                  {t("url.searching")}
                </div>
              ) : error && results.length === 0 ? (
                <div className="px-3 py-3 text-sm text-red-300">
                  {t("url.searchError")}
                </div>
              ) : results.length === 0 ? (
                <div className="px-3 py-3 text-sm text-zinc-400">
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
                    className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition hover:bg-white/5 focus:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-500"
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
