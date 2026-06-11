import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Check,
  ChevronDown,
  Loader2,
  Music4,
  Search,
} from "lucide-react";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { Button } from "../../components/ui/Button";
import { Thumbnail } from "../../components/ui/Thumbnail";
import {
  ApiError,
  applyAudioTags,
  identifyAudio,
  searchAudio,
} from "../../lib/api";
import type { TagCandidate } from "../../types/autotag";
import { guessFromFilename } from "./filename";

interface AutoTagPanelProps {
  /** Absolute path of the downloaded audio file to tag. */
  path: string;
  /** Basename shown in the header. */
  filename?: string;
  /** Hide the panel (user dismissed it, or tagging finished). */
  onDismiss: () => void;
  /** Called after tags are written, so the history (cover art) can refresh. */
  onApplied?: () => void;
  /** Open + identify immediately on mount (e.g. re-tagging from history). */
  autoOpen?: boolean;
}

const INPUT =
  "w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm " +
  "text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-violet-500/50";

type Stage = "loading" | "review" | "applying" | "done" | "error";

/**
 * Inline audio auto-tagging card shown in the main column after an audio
 * download. It looks the file up in the Apple Music catalogue on mount, lists
 * the matching versions to pick from, lets the user edit any field or search
 * manually, and writes the tags + cover only when they hit "Apply" — they can
 * also just ignore or dismiss it.
 */
export function AutoTagPanel({
  path,
  filename,
  onDismiss,
  onApplied,
  autoOpen,
}: AutoTagPanelProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(!!autoOpen);
  const [stage, setStage] = useState<Stage>("loading");
  const [error, setError] = useState<string | null>(null);
  const startedRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  // One controller for the panel's lifetime; cancels in-flight lookups on unmount.
  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    return () => controller.abort();
  }, []);

  const [results, setResults] = useState<TagCandidate[]>([]);
  const [selected, setSelected] = useState(-1);

  // Editable fields (reflect the selected version, but freely editable).
  const [title, setTitle] = useState("");
  const [artist, setArtist] = useState("");
  const [album, setAlbum] = useState("");
  const [year, setYear] = useState("");
  const [coverUrl, setCoverUrl] = useState<string | null>(null);

  // Manual catalogue search.
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchArtist, setSearchArtist] = useState("");
  const [searchTitle, setSearchTitle] = useState("");
  const [searching, setSearching] = useState(false);

  const selectVersion = useCallback((c: TagCandidate, index: number) => {
    setSelected(index);
    setTitle(c.title);
    setArtist(c.artist);
    setAlbum(c.album ?? "");
    setYear(c.year ?? "");
    setCoverUrl(c.cover_url);
  }, []);

  const showResults = useCallback(
    (list: TagCandidate[]) => {
      setResults(list);
      if (list.length > 0) selectVersion(list[0], 0);
    },
    [selectVersion],
  );

  // Look up the catalogue the first time the card is opened (not on mount, so
  // we don't hit Apple Music unless the user actually wants to tag).
  const runIdentify = useCallback(() => {
    // Capture the signal of the controller in use: under StrictMode the panel
    // mounts twice and the first controller is aborted, so we must check *this*
    // request's signal (not abortRef.current, which now points at the new one).
    const signal = abortRef.current?.signal;
    identifyAudio(path, signal)
      .then((data) => {
        if (signal?.aborted) return;
        if (data.results.length > 0) {
          showResults(data.results);
        } else {
          const guess = guessFromFilename(filename);
          setArtist(guess.artist);
          setTitle(guess.title);
          setSearchArtist(guess.artist);
          setSearchTitle(guess.title);
          setSearchOpen(true);
          setError(t("autotag.noMatch"));
        }
        setStage("review");
      })
      .catch((cause) => {
        if (signal?.aborted) return;
        setError(cause instanceof ApiError ? cause.message : t("autotag.error"));
        setStage("error");
      });
  }, [path, filename, t, showResults]);

  // Opened directly (re-tagging from history) → identify right away. No
  // startedRef gate here: under StrictMode the first mount's request is aborted,
  // so the second mount must be allowed to re-run it. (signal-capture in
  // runIdentify keeps the aborted first request from showing an error.)
  useEffect(() => {
    if (autoOpen) {
      startedRef.current = true; // a later manual toggle won't re-identify
      runIdentify();
    }
  }, [autoOpen, runIdentify]);

  const toggleOpen = () => {
    if (!open && !startedRef.current) {
      startedRef.current = true;
      runIdentify();
    }
    setOpen((v) => !v);
  };

  const runSearch = async () => {
    if (!searchTitle.trim()) return;
    setSearching(true);
    try {
      const data = await searchAudio(
        searchArtist.trim(),
        searchTitle.trim(),
        abortRef.current?.signal,
      );
      if (abortRef.current?.signal.aborted) return;
      if (data.results.length > 0) {
        showResults(data.results);
        setError(null);
      } else {
        setError(t("autotag.noResults"));
      }
    } catch (cause) {
      if (abortRef.current?.signal.aborted) return;
      setError(cause instanceof ApiError ? cause.message : t("autotag.error"));
    } finally {
      setSearching(false);
    }
  };

  const onApply = async () => {
    setStage("applying");
    const sel = selected >= 0 ? results[selected] : null;
    try {
      await applyAudioTags({
        path,
        title: title.trim() || null,
        artist: artist.trim() || null,
        album: album.trim() || null,
        year: year.trim() || null,
        track_number: sel?.track_number ?? null,
        cover_url: coverUrl,
      });
      setStage("done");
      onApplied?.();
      window.setTimeout(onDismiss, 1500);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("autotag.error"));
      setStage("review");
    }
  };

  const reviewing = stage === "review" || stage === "applying";

  return (
    <GlassPanel className="p-5">
      {autoOpen ? (
        // Re-tagging from history: the panel is fixed open (no collapse toggle).
        <div className="flex w-full items-center text-sm font-semibold text-zinc-200">
          <span className="flex items-center gap-2">
            <Music4 size={16} className="text-violet-400" />
            {t("autotag.title")}
          </span>
        </div>
      ) : (
        <button
          type="button"
          onClick={toggleOpen}
          aria-expanded={open}
          className="flex w-full items-center justify-between text-sm font-semibold text-zinc-200 hover:text-white transition"
        >
          <span className="flex items-center gap-2">
            <Music4 size={16} className="text-violet-400" />
            {t("autotag.title")}
          </span>
          <ChevronDown
            size={18}
            className={`text-zinc-400 transition-transform ${open ? "rotate-180" : ""}`}
          />
        </button>
      )}

      {open && (
        <div className="mt-3">
          {filename && (
            <p className="text-xs text-zinc-400 mb-3 truncate">{filename}</p>
          )}

      {stage === "loading" && (
        <div className="py-6 flex items-center gap-3 text-zinc-400">
          <Loader2 size={20} className="animate-spin text-violet-400" />
          <span className="text-sm">{t("autotag.identifying")}</span>
        </div>
      )}

      {stage === "error" && (
        <div className="py-3 flex items-center gap-3 text-red-300">
          <AlertCircle size={18} className="shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {stage === "done" && (
        <div className="py-4 flex items-center gap-3 text-emerald-300">
          <Check size={20} className="shrink-0" />
          <span className="text-sm">{t("autotag.applied")}</span>
        </div>
      )}

      {reviewing && (
        <>
          {error && <p className="text-xs text-amber-400/90 mb-3">{error}</p>}

          <div className="flex gap-4 items-end">
            <div className="w-[124px] h-[124px] rounded-xl overflow-hidden bg-white/5 shrink-0 flex items-center justify-center">
              {coverUrl ? (
                <Thumbnail
                  key={coverUrl}
                  src={coverUrl}
                  alt={album}
                  className="h-full w-full object-cover"
                  fallback={<Music4 className="size-7 text-white/40" />}
                />
              ) : (
                <Music4 className="size-7 text-white/40" />
              )}
            </div>
            <div className="flex-1 space-y-2 min-w-0">
              <label className="block">
                <span className="text-xs text-zinc-400">
                  {t("autotag.fieldTitle")}
                </span>
                <input
                  className={INPUT}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label className="block">
                <span className="text-xs text-zinc-400">
                  {t("autotag.fieldArtist")}
                </span>
                <input
                  className={INPUT}
                  value={artist}
                  onChange={(e) => setArtist(e.target.value)}
                />
              </label>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-[1fr_5rem] gap-2">
            <label className="block min-w-0">
              <span className="text-xs text-zinc-400">
                {t("autotag.fieldAlbum")}
              </span>
              <input
                className={INPUT}
                value={album}
                onChange={(e) => setAlbum(e.target.value)}
              />
            </label>
            <label className="block">
              <span className="text-xs text-zinc-400">
                {t("autotag.fieldYear")}
              </span>
              <input
                className={INPUT}
                value={year}
                onChange={(e) => setYear(e.target.value)}
              />
            </label>
          </div>

          {results.length > 1 && (
            <div className="mt-4">
              <span className="text-xs text-zinc-400">
                {t("autotag.versions")}
              </span>
              <div className="mt-1 space-y-1 max-h-44 overflow-y-auto">
                {results.map((r, i) => (
                  <button
                    type="button"
                    key={`${r.title}-${r.album}-${i}`}
                    onClick={() => selectVersion(r, i)}
                    className={`flex w-full items-center gap-3 rounded-lg border px-2 py-1.5 text-left transition ${
                      i === selected
                        ? "border-violet-500/50 bg-violet-600/15"
                        : "border-white/5 hover:bg-white/5"
                    }`}
                  >
                    <div className="w-9 h-9 rounded bg-white/5 overflow-hidden shrink-0">
                      {r.cover_url && (
                        <Thumbnail
                          key={r.cover_url}
                          src={r.cover_url}
                          alt={r.album ?? ""}
                          className="h-full w-full object-cover"
                          fallback={<span />}
                        />
                      )}
                    </div>
                    <span className="min-w-0 text-xs">
                      <span className="block truncate text-zinc-200">
                        {r.album ?? r.title}
                      </span>
                      <span className="block truncate text-zinc-400">
                        {r.year ?? ""}
                        {r.track_number ? ` · #${r.track_number}` : ""}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={() => setSearchOpen((v) => !v)}
            className="mt-3 text-xs text-violet-400 hover:text-violet-300 flex items-center gap-1"
          >
            <Search size={12} /> {t("autotag.searchToggle")}
          </button>

          {searchOpen && (
            <div className="mt-2 grid grid-cols-[1fr_1fr_auto] gap-2">
              <input
                className={INPUT}
                aria-label={t("autotag.fieldArtist")}
                placeholder={t("autotag.fieldArtist")}
                value={searchArtist}
                onChange={(e) => setSearchArtist(e.target.value)}
              />
              <input
                className={INPUT}
                aria-label={t("autotag.fieldTitle")}
                placeholder={t("autotag.fieldTitle")}
                value={searchTitle}
                onChange={(e) => setSearchTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void runSearch()}
              />
              <button
                type="button"
                onClick={() => void runSearch()}
                disabled={searching || !searchTitle.trim()}
                className="flex items-center justify-center rounded-xl border border-white/10 px-3 text-zinc-200 hover:bg-white/10 transition disabled:opacity-50"
                aria-label={t("autotag.searchAction")}
              >
                {searching ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Search size={16} />
                )}
              </button>
            </div>
          )}

          <div className="mt-5 flex justify-end gap-3">
            <button
              type="button"
              onClick={onDismiss}
              disabled={stage === "applying"}
              className="text-sm text-zinc-300 hover:text-white transition disabled:opacity-50"
            >
              {t("autotag.dismiss")}
            </button>
            <Button
              variant="gradient"
              onClick={() => void onApply()}
              disabled={stage === "applying" || !title.trim()}
              className="px-4 py-2 text-sm disabled:opacity-50"
            >
              {stage === "applying" ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Check size={16} />
              )}
              {t("autotag.apply")}
            </Button>
          </div>
        </>
      )}
        </div>
      )}
    </GlassPanel>
  );
}
