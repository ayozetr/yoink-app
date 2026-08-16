import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, ChevronDown, Loader2, Music4, Search } from "lucide-react";
import { GlassPanel } from "../../components/ui/GlassPanel";
import { Button } from "../../components/ui/Button";
import { Thumbnail } from "../../components/ui/Thumbnail";
import { applyAudioTags, identifyAudio, searchAudio } from "../../lib/api";
import type { TagCandidate } from "../../types/autotag";
import { guessFromFilename } from "./filename";

interface TagItem {
  path: string;
  filename: string;
}

interface AutoTagBatchPanelProps {
  /** Audio files from a finished playlist. */
  items: TagItem[];
  onDismiss: () => void;
  /** Called after tags are written, so the history (cover art) can refresh. */
  onApplied?: () => void;
}

const INPUT =
  "w-full min-w-0 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm " +
  "text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-violet-500/50";

type TrackStatus = "loading" | "ready" | "nomatch" | "applied" | "error";

interface Track {
  path: string;
  filename: string;
  status: TrackStatus;
  results: TagCandidate[];
  selected: number;
  title: string;
  artist: string;
  album: string;
  year: string;
  coverUrl: string | null;
  included: boolean;
}

function initTrack(item: TagItem): Track {
  return {
    path: item.path,
    filename: item.filename,
    status: "loading",
    results: [],
    selected: -1,
    title: "",
    artist: "",
    album: "",
    year: "",
    coverUrl: null,
    included: false,
  };
}

/**
 * Batch audio auto-tagging card for a finished playlist. Collapsed by default;
 * on first open it looks every track up in the Apple Music catalogue, lists
 * them with their best match + an include checkbox, lets each row be expanded
 * (accordion) to review/edit/search, and writes all the checked ones at once.
 */
export function AutoTagBatchPanel({
  items,
  onDismiss,
  onApplied,
}: AutoTagBatchPanelProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [tracks, setTracks] = useState<Track[]>(() => items.map(initTrack));
  const [expanded, setExpanded] = useState(-1);
  const [applying, setApplying] = useState(false);
  const startedRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  // Cancel any in-flight catalogue lookups when the card unmounts.
  useEffect(() => () => abortRef.current?.abort(), []);

  // Latest tracks for applyMarked, so edits made mid-apply aren't lost to a
  // stale snapshot captured at click time.
  const tracksRef = useRef(tracks);
  useEffect(() => {
    tracksRef.current = tracks;
  }, [tracks]);

  const patch = useCallback(
    (i: number, p: Partial<Track>) =>
      setTracks((ts) => ts.map((tr, idx) => (idx === i ? { ...tr, ...p } : tr))),
    [],
  );

  const loadInto = (i: number, c: TagCandidate, ci: number) =>
    patch(i, {
      selected: ci,
      title: c.title,
      artist: c.artist,
      album: c.album ?? "",
      year: c.year ?? "",
      coverUrl: c.cover_url,
      // Picking a candidate (manual search or clicking a result) means the user
      // wants it applied — mark it included, like the auto-identify path does,
      // so a manually-found match isn't silently skipped on "apply to selected".
      included: true,
    });

  // Identify the tracks the first time the card is opened — through a small
  // concurrency pool so we don't fire N parallel requests at once (MusicBrainz
  // caps at ~1 req/s). Cancellable on unmount via the shared AbortController.
  const identifyAll = useCallback(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    const queue = items.map((item, i) => ({ item, i }));

    const worker = async () => {
      let next = queue.shift();
      while (next) {
        const { item, i } = next;
        try {
          const data = await identifyAudio(item.path, controller.signal);
          if (controller.signal.aborted) return;
          const top = data.results[0];
          if (top) {
            patch(i, {
              status: "ready",
              results: data.results,
              selected: 0,
              title: top.title,
              artist: top.artist,
              album: top.album ?? "",
              year: top.year ?? "",
              coverUrl: top.cover_url,
              included: true,
            });
          } else {
            const guess = guessFromFilename(item.filename);
            patch(i, {
              status: "nomatch",
              title: guess.title,
              artist: guess.artist,
            });
          }
        } catch {
          if (controller.signal.aborted) return;
          patch(i, { status: "error" });
        }
        next = queue.shift();
      }
    };

    const POOL = 3;
    for (let w = 0; w < POOL; w += 1) void worker();
  }, [items, patch]);

  const toggleOpen = () => {
    if (!open && !startedRef.current) {
      startedRef.current = true;
      identifyAll();
    }
    setOpen((v) => !v);
  };

  const searchForTrack = async (i: number, artist: string, title: string) => {
    if (!title.trim()) return;
    patch(i, { status: "loading" });
    try {
      const data = await searchAudio(
        artist.trim(),
        title.trim(),
        abortRef.current?.signal,
      );
      if (abortRef.current?.signal.aborted) return;
      const top = data.results[0];
      if (top) {
        patch(i, { status: "ready", results: data.results });
        loadInto(i, top, 0);
      } else {
        patch(i, { status: "nomatch", results: [] });
      }
    } catch {
      patch(i, { status: "error" });
    }
  };

  const applyMarked = async () => {
    setApplying(true);
    for (let i = 0; i < tracksRef.current.length; i += 1) {
      const tr = tracksRef.current[i];
      if (!tr.included || tr.status === "applied") continue;
      try {
        const sel = tr.selected >= 0 ? tr.results[tr.selected] : null;
        await applyAudioTags({
          path: tr.path,
          title: tr.title.trim() || null,
          artist: tr.artist.trim() || null,
          album: tr.album.trim() || null,
          year: tr.year.trim() || null,
          track_number: sel?.track_number ?? null,
          cover_url: tr.coverUrl,
        });
        patch(i, { status: "applied", included: false });
      } catch {
        patch(i, { status: "error" });
      }
    }
    setApplying(false);
    onApplied?.(); // refresh history so freshly-tagged covers show up
  };

  const markedCount = tracks.filter((tr) => tr.included).length;

  return (
    <GlassPanel className="p-5">
      <button
        type="button"
        onClick={toggleOpen}
        aria-expanded={open}
        className="flex w-full items-center justify-between text-sm font-semibold text-zinc-200 hover:text-white transition"
      >
        <span className="flex items-center gap-2">
          <Music4 size={16} className="text-violet-400" />
          {t("autotag.batchTitle", { count: tracks.length })}
        </span>
        <ChevronDown
          size={18}
          className={`text-zinc-400 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="mt-3 space-y-1">
          {tracks.map((tr, i) => (
            <div key={tr.path} className="rounded-xl border border-white/5">
              <div className="flex items-center gap-2 px-2 py-1.5">
                <input
                  type="checkbox"
                  aria-label={t("autotag.includeTrack")}
                  checked={tr.included}
                  disabled={applying || tr.status === "applied" || tr.status === "loading"}
                  onChange={() => patch(i, { included: !tr.included })}
                  className="size-4 accent-violet-500 shrink-0 disabled:opacity-40"
                />
                <button
                  type="button"
                  onClick={() => setExpanded(expanded === i ? -1 : i)}
                  aria-expanded={expanded === i}
                  className="flex flex-1 items-center gap-2 min-w-0 text-left"
                >
                  <div className="relative w-9 h-9 rounded bg-white/5 overflow-hidden shrink-0 flex items-center justify-center">
                    {tr.coverUrl ? (
                      <Thumbnail
                        key={tr.coverUrl}
                        src={tr.coverUrl}
                        alt={tr.album}
                        className="h-full w-full object-cover"
                        fallback={<Music4 className="size-4 text-white/40" />}
                      />
                    ) : (
                      <Music4 className="size-4 text-white/40" />
                    )}
                  </div>
                  <span className="min-w-0 flex-1 text-xs">
                    {tr.status === "loading" ? (
                      <span className="flex items-center gap-1.5 text-zinc-400">
                        <Loader2 size={12} className="animate-spin" />
                        {t("autotag.identifying")}
                      </span>
                    ) : tr.status === "applied" ? (
                      <span className="flex items-center gap-1.5 text-emerald-300">
                        <Check size={12} />
                        {tr.artist} — {tr.title}
                      </span>
                    ) : tr.status === "nomatch" ? (
                      <span className="block truncate text-amber-400/90">
                        {t("autotag.noResults")} · {tr.filename}
                      </span>
                    ) : tr.status === "error" ? (
                      <span className="block truncate text-red-400/90">
                        {t("autotag.error")} · {tr.filename}
                      </span>
                    ) : (
                      <>
                        <span className="block truncate text-zinc-200">
                          {tr.artist} — {tr.title}
                        </span>
                        <span className="block truncate text-zinc-400">
                          {tr.album}
                          {tr.year ? ` (${tr.year})` : ""}
                        </span>
                      </>
                    )}
                  </span>
                  <ChevronDown
                    size={14}
                    className={`text-zinc-500 shrink-0 transition-transform ${expanded === i ? "rotate-180" : ""}`}
                  />
                </button>
              </div>

              {expanded === i && tr.status !== "loading" && (
                <div className="border-t border-white/5 px-3 py-3 space-y-2">
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <label className="block">
                      <span className="text-xs text-zinc-400">
                        {t("autotag.fieldTitle")}
                      </span>
                      <input
                        className={INPUT}
                        value={tr.title}
                        onChange={(e) => patch(i, { title: e.target.value })}
                      />
                    </label>
                    <label className="block">
                      <span className="text-xs text-zinc-400">
                        {t("autotag.fieldArtist")}
                      </span>
                      <input
                        className={INPUT}
                        value={tr.artist}
                        onChange={(e) => patch(i, { artist: e.target.value })}
                      />
                    </label>
                    <label className="block">
                      <span className="text-xs text-zinc-400">
                        {t("autotag.fieldAlbum")}
                      </span>
                      <input
                        className={INPUT}
                        value={tr.album}
                        onChange={(e) => patch(i, { album: e.target.value })}
                      />
                    </label>
                    <label className="block">
                      <span className="text-xs text-zinc-400">
                        {t("autotag.fieldYear")}
                      </span>
                      <input
                        className={INPUT}
                        value={tr.year}
                        onChange={(e) => patch(i, { year: e.target.value })}
                      />
                    </label>
                  </div>

                  <button
                    type="button"
                    onClick={() => void searchForTrack(i, tr.artist, tr.title)}
                    className="flex items-center gap-1.5 text-xs text-violet-400 hover:text-violet-300 transition"
                  >
                    <Search size={12} /> {t("autotag.searchAction")}
                  </button>

                  {tr.results.length > 1 && (
                    <div className="space-y-1 max-h-40 overflow-y-auto">
                      {tr.results.map((r, ci) => (
                        <button
                          type="button"
                          key={`${r.title}-${r.album}-${ci}`}
                          onClick={() => loadInto(i, r, ci)}
                          className={`flex w-full items-center gap-2 rounded-lg border px-2 py-1 text-left transition ${
                            ci === tr.selected
                              ? "border-violet-500/50 bg-violet-600/15"
                              : "border-white/5 hover:bg-white/5"
                          }`}
                        >
                          <div className="relative w-7 h-7 rounded bg-white/5 overflow-hidden shrink-0">
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
                          <span className="min-w-0 text-[11px]">
                            <span className="block truncate text-zinc-200">
                              {r.album ?? r.title}
                            </span>
                            <span className="block truncate text-zinc-400">
                              {r.year ?? ""}
                            </span>
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          <div className="mt-4 flex justify-end gap-3">
            <button
              type="button"
              onClick={onDismiss}
              disabled={applying}
              className="text-sm text-zinc-300 hover:text-white transition disabled:opacity-50"
            >
              {t("autotag.dismiss")}
            </button>
            <Button
              variant="gradient"
              onClick={() => void applyMarked()}
              disabled={applying || markedCount === 0}
              className="px-4 py-2 text-sm disabled:opacity-50"
            >
              {applying ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Check size={16} />
              )}
              {t("autotag.applyMarked", { count: markedCount })}
            </Button>
          </div>
        </div>
      )}
    </GlassPanel>
  );
}
