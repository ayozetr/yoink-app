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

/** A bare http(s) URL or a spaceless domain/path — anything else is a search. */
function looksLikeUrl(s: string): boolean {
  const t = s.trim();
  if (/^https?:\/\//i.test(t)) return true;
  return !t.includes(" ") && /\.[a-z]{2,}(\/|$|\?)/i.test(t);
}

function isSearchQuery(s: string): boolean {
  return s.trim().length > 0 && !looksLikeUrl(s);
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
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const query = value.trim();
  const isSearch = isSearchQuery(value);
  const disabled = loading || query.length === 0;

  // Debounced live search. setState happens only inside the timer/promise (never
  // synchronously in the effect body), so it doesn't trip cascading renders.
  useEffect(() => {
    abortRef.current?.abort();
    if (!isSearch) return;
    const controller = new AbortController();
    abortRef.current = controller;
    const timer = setTimeout(() => {
      void searchYoutube(query, controller.signal)
        .then((r) => {
          if (!controller.signal.aborted) {
            setResults(r);
            setSearching(false);
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setResults([]);
            setSearching(false);
          }
        });
    }, 400);
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

  // Drive the dropdown from the edit event (not an effect): open + show the
  // spinner as soon as the user types a query; clear when it's a URL/empty.
  const handleChange = (next: string) => {
    onChange(next);
    const willSearch = isSearchQuery(next);
    setOpen(willSearch);
    setSearching(willSearch);
    if (!willSearch) setResults([]);
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

  // Enter / the button: analyze a URL, or pick the top hit when searching.
  const submit = () => {
    if (isSearch) {
      if (results[0]) choose(results[0]);
    } else if (!disabled) {
      onAnalyze();
    }
  };

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
            aria-label={t("url.placeholder")}
            placeholder={t("url.placeholder")}
            value={value}
            onChange={(event) => handleChange(event.target.value)}
            onFocusCapture={() => {
              if (isSearch) setOpen(true);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") submit();
              if (event.key === "Escape") setOpen(false);
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

          {open && isSearch && (
            <div className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-30 max-h-96 overflow-y-auto rounded-2xl border border-white/10 bg-[#16181f] shadow-xl">
              {searching && results.length === 0 ? (
                <div className="flex items-center gap-2 px-4 py-3 text-sm text-zinc-400">
                  <Loader2 size={16} className="animate-spin" />
                  {t("url.searching")}
                </div>
              ) : results.length === 0 ? (
                <div className="px-4 py-3 text-sm text-zinc-400">
                  {t("url.noResults")}
                </div>
              ) : (
                results.map((entry) => (
                  <button
                    key={entry.id || entry.url}
                    type="button"
                    onClick={() => choose(entry)}
                    className="flex w-full items-center gap-3 px-3 py-2 text-left transition hover:bg-white/5"
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
                      {entry.uploader && (
                        <span className="block truncate text-xs text-zinc-500">
                          {entry.uploader}
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
