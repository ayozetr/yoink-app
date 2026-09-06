/**
 * Audio auto-tagging types — mirror of `backend/app/models/autotag.py`.
 *
 * Metadata + cover art come from the Apple Music (iTunes) catalogue. Flow:
 * identify/search → (user picks a version + edits) → apply. Nothing is written
 * to the file until `apply`.
 */

/** One catalogue match (an Apple Music track release). */
export interface TagCandidate {
  title: string;
  artist: string;
  album: string | null;
  year: string | null;
  genre: string | null;
  track_number: number | null;
  cover_url: string | null;
}

/** Matches from identify/search (best first; empty = nothing found). */
export interface CandidateList {
  results: TagCandidate[];
}

/** The (possibly user-edited) tags to write into the file. */
export interface ApplyRequest {
  path: string;
  title?: string | null;
  artist?: string | null;
  album?: string | null;
  year?: string | null;
  genre?: string | null;
  track_number?: number | null;
  cover_url?: string | null;
  /** Embed lyrics for this track (omitted = use the global setting). */
  embed_lyrics?: boolean | null;
}

export interface ApplyResponse {
  ok: boolean;
  embedded_cover: boolean;
}

/** Preview-time lyrics availability for the auto-tag card. */
export interface LyricsResult {
  found: boolean;
  instrumental: boolean;
  has_synced: boolean;
  /** The full plain lyrics (shown in the "view lyrics" popup). */
  plain: string | null;
}
