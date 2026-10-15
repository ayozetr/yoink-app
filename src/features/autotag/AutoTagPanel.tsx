import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Check,
  ChevronDown,
  Loader2,
  Music4,
  Search,
  X,
} from "lucide-react";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { Button } from "../../components/ui/Button";
import { Thumbnail } from "../../components/ui/Thumbnail";
import {
  ApiError,
  applyAudioTags,
  identifyAudio,
  previewLyrics,
  searchAudio,
} from "../../lib/api";
import { useFocusTrap } from "../../lib/useFocusTrap";
import type { LyricsResult, TagCandidate } from "../../types/autotag";
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
  /** Extra classes for the root panel (e.g. a solid bg when shown in a modal). */
  panelClassName?: string;
  /** Whether "fetch lyrics" is enabled (Settings). When off, the lyrics preview
   *  is neither looked up nor shown. */
  fetchLyrics?: boolean;
}

const INPUT =
  "w-full min-w-0 rounded-xl border border-line/10 bg-surface px-3 py-2 text-sm " +
  "text-fg placeholder:text-fg-faint focus:outline-none focus:border-accent/40";

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
  panelClassName = "",
  fetchLyrics = false,
}: AutoTagPanelProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(!!autoOpen);
  const [stage, setStage] = useState<Stage>("loading");
  const [error, setError] = useState<string | null>(null);
  const startedRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const searchingRef = useRef(false);
  const dismissTimerRef = useRef<number | null>(null);
  // Clear the post-apply auto-dismiss timer on unmount, so it can't fire later
  // and dismiss the next download's tag panel.
  useEffect(
    () => () => {
      if (dismissTimerRef.current) window.clearTimeout(dismissTimerRef.current);
    },
    [],
  );

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
  const [genre, setGenre] = useState("");
  const [coverUrl, setCoverUrl] = useState<string | null>(null);

  // Lyrics preview (LRCLIB) for the reviewed track + per-track embed toggle.
  const [lyrics, setLyrics] = useState<LyricsResult | null>(null);
  const [lyricsLoading, setLyricsLoading] = useState(false);
  const [embedLyrics, setEmbedLyrics] = useState(true);
  const [showLyrics, setShowLyrics] = useState(false);
  // Focus-trap the "view lyrics" popup + close it on Escape.
  const lyricsModalRef = useFocusTrap<HTMLDivElement>(showLyrics);
  useEffect(() => {
    if (!showLyrics) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setShowLyrics(false);
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [showLyrics]);

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
    setGenre(c.genre ?? "");
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
    if (!searchTitle.trim() || searchingRef.current) return;
    searchingRef.current = true;
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
      searchingRef.current = false;
    }
  };

  // Look the track's lyrics up (debounced) while reviewing, for the indicator
  // + preview; the checkbox defaults to whatever LRCLIB returned.
  useEffect(() => {
    if (stage !== "review" || !title.trim() || !fetchLyrics) return;
    let cancelled = false;
    const id = window.setTimeout(() => {
      setLyrics(null);
      setLyricsLoading(true);
      previewLyrics({
        title: title.trim(),
        artist: artist.trim(),
        album: album.trim() || null,
        path,
      })
        .then((r) => {
          if (cancelled) return;
          setLyrics(r);
          setEmbedLyrics(r.found);
          setShowLyrics(false);
        })
        .catch(() => {
          if (!cancelled) setLyrics(null);
        })
        .finally(() => {
          if (!cancelled) setLyricsLoading(false);
        });
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, [stage, title, artist, album, path, fetchLyrics]);

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
        genre: genre.trim() || null,
        track_number: sel?.track_number ?? null,
        cover_url: coverUrl,
        embed_lyrics: lyrics?.found ? embedLyrics : false,
      });
      setStage("done");
      onApplied?.();
      dismissTimerRef.current = window.setTimeout(onDismiss, 1500);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : t("autotag.error"));
      setStage("review");
    }
  };

  const reviewing = stage === "review" || stage === "applying";

  return (
    <GlassPanel className={`p-5 ${panelClassName}`}>
      {autoOpen ? (
        // Re-tagging from history: the panel is fixed open (no collapse toggle).
        <div className="flex w-full items-center font-display text-lg font-normal text-fg">
          <span className="flex items-center gap-2">
            <Music4 size={18} className="text-accent-soft" />
            {t("autotag.title")}
          </span>
        </div>
      ) : (
        <button
          type="button"
          onClick={toggleOpen}
          aria-expanded={open}
          className="flex w-full items-center justify-between text-sm font-semibold text-fg hover:text-fg transition"
        >
          <span className="flex items-center gap-2">
            <Music4 size={16} className="text-accent-soft" />
            {t("autotag.title")}
          </span>
          <ChevronDown
            size={18}
            className={`text-fg-dim transition-transform ${open ? "rotate-180" : ""}`}
          />
        </button>
      )}

      {open && (
        <div className="mt-3">
          {filename && (
            <p className="text-xs text-fg-dim mb-3 truncate">{filename}</p>
          )}

      {stage === "loading" && (
        <div className="py-6 flex items-center gap-3 text-fg-dim">
          <Loader2 size={20} className="animate-spin text-accent-soft" />
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
            <div className="w-[124px] h-[124px] rounded-xl overflow-hidden bg-surface-2 shrink-0 flex items-center justify-center">
              {coverUrl ? (
                <Thumbnail
                  key={coverUrl}
                  src={coverUrl}
                  alt={album}
                  className="h-full w-full object-cover"
                  fallback={<Music4 className="size-7 text-fg-faint" />}
                />
              ) : (
                <Music4 className="size-7 text-fg-faint" />
              )}
            </div>
            <div className="flex-1 space-y-2 min-w-0">
              <label className="block">
                <span className="text-xs text-fg-dim">
                  {t("autotag.fieldTitle")}
                </span>
                <input
                  className={INPUT}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label className="block">
                <span className="text-xs text-fg-dim">
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
              <span className="text-xs text-fg-dim">
                {t("autotag.fieldAlbum")}
              </span>
              <input
                className={INPUT}
                value={album}
                onChange={(e) => setAlbum(e.target.value)}
              />
            </label>
            <label className="block">
              <span className="text-xs text-fg-dim">
                {t("autotag.fieldYear")}
              </span>
              <input
                className={INPUT}
                value={year}
                onChange={(e) => setYear(e.target.value)}
              />
            </label>
          </div>

          <label className="mt-3 block">
            <span className="text-xs text-fg-dim">
              {t("autotag.fieldGenre")}
            </span>
            <input
              className={INPUT}
              value={genre}
              onChange={(e) => setGenre(e.target.value)}
            />
          </label>

          {results.length > 1 && (
            <div className="mt-4">
              <span className="text-xs text-fg-dim">
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
                        ? "border-accent/40 bg-accent/15"
                        : "border-line/10 hover:bg-surface-hover"
                    }`}
                  >
                    <div className="w-9 h-9 rounded bg-surface-2 overflow-hidden shrink-0">
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
                      <span className="block truncate text-fg">
                        {r.album ?? r.title}
                      </span>
                      <span className="block truncate text-fg-dim">
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
            className="mt-3 text-xs text-accent-soft hover:text-accent flex items-center gap-1"
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
                className="flex items-center justify-center rounded-xl border border-line/10 px-3 text-fg hover:bg-surface-hover transition disabled:opacity-50"
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

          {fetchLyrics && reviewing && (lyricsLoading || lyrics) && (
            <div className="mt-4 rounded-xl border border-line/10 bg-surface-2 p-3">
              {lyricsLoading ? (
                <p className="flex items-center gap-2 text-xs text-fg-dim">
                  <Loader2 size={13} className="animate-spin" />
                  {t("autotag.lyricsSearching")}
                </p>
              ) : lyrics?.found ? (
                <>
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={embedLyrics}
                      onChange={(e) => setEmbedLyrics(e.target.checked)}
                      className="size-4 shrink-0 accent-accent"
                    />
                    <span>{t("autotag.lyrics")}</span>
                    <span className="text-xs text-emerald-400">
                      {lyrics.instrumental
                        ? t("autotag.lyricsInstrumental")
                        : lyrics.has_synced
                          ? t("autotag.lyricsFoundSynced")
                          : t("autotag.lyricsFound")}
                    </span>
                  </label>
                  {lyrics.plain && (
                    <button
                      type="button"
                      onClick={() => setShowLyrics(true)}
                      className="mt-1 text-xs text-fg-dim transition hover:text-fg"
                    >
                      {t("autotag.lyricsShow")}
                    </button>
                  )}
                </>
              ) : (
                <p className="text-xs text-fg-faint">{t("autotag.lyricsNone")}</p>
              )}
            </div>
          )}

          <div className="mt-5 flex justify-end gap-3">
            <button
              type="button"
              onClick={onDismiss}
              disabled={stage === "applying"}
              className="text-sm text-fg-dim hover:text-fg transition disabled:opacity-50"
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
      {showLyrics &&
        lyrics?.plain &&
        createPortal(
          <div
            className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4"
            onClick={() => setShowLyrics(false)}
          >
            <div
              ref={lyricsModalRef}
              tabIndex={-1}
              role="dialog"
              aria-modal="true"
              aria-label={t("autotag.lyrics")}
              onClick={(e) => e.stopPropagation()}
              className="flex max-h-[80vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-line/10 bg-surface shadow-2xl outline-none"
            >
              <div className="flex items-center justify-between gap-3 border-b border-line/10 px-4 py-3">
                <h3 className="truncate text-sm font-semibold text-fg">
                  {title.trim() || t("autotag.lyrics")}
                </h3>
                <button
                  type="button"
                  onClick={() => setShowLyrics(false)}
                  aria-label={t("autotag.close")}
                  className="rounded-md p-1 text-fg-dim transition hover:bg-surface-hover hover:text-fg"
                >
                  <X size={16} />
                </button>
              </div>
              <div
                tabIndex={0}
                aria-label={t("autotag.lyrics")}
                className="overflow-auto whitespace-pre-wrap px-6 py-5 text-center font-sans text-[15px] leading-8 tracking-[0.01em] text-fg outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/40"
              >
                {lyrics.plain}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </GlassPanel>
  );
}
