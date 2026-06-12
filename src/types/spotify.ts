/** Spotify import types — mirror `backend/app/models/spotify.py`. */

export type SpotifyKind = "track" | "album" | "playlist";

export interface SpotifyTrack {
  title: string;
  artists: string;
  duration_ms: number | null;
  is_explicit: boolean;
  album: string | null;
  year: string | null;
  cover_url: string | null;
  spotify_url: string;
}

export interface SpotifyImportInfo {
  type: SpotifyKind;
  name: string;
  /** Playlist owner, or album/track artist. */
  subtitle: string | null;
  cover_url: string | null;
  tracks: SpotifyTrack[];
  /** True if the embed exposed fewer tracks than the real total. */
  truncated: boolean;
}
