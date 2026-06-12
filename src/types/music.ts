/** Music import types — mirror `backend/app/models/music.py`. */

export type MusicSource = "spotify" | "deezer" | "apple" | "tidal" | "amazon";
export type MusicKind = "track" | "album" | "playlist";

export interface MusicTrack {
  title: string;
  artists: string;
  duration_ms: number | null;
  is_explicit: boolean;
  album: string | null;
  year: string | null;
  cover_url: string | null;
  source_url: string;
}

export interface MusicImportInfo {
  source: MusicSource;
  type: MusicKind;
  name: string;
  /** Playlist owner, or album/track artist. */
  subtitle: string | null;
  cover_url: string | null;
  tracks: MusicTrack[];
  /** True if fewer tracks were resolved than the real total. */
  truncated: boolean;
}

/** Display names for the supported sources. */
export const MUSIC_SOURCE_NAMES: Record<MusicSource, string> = {
  spotify: "Spotify",
  deezer: "Deezer",
  apple: "Apple Music",
  tidal: "Tidal",
  amazon: "Amazon Music",
};
