// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Audio auto-tagging. Writes the chosen metadata
//! (title/artist/album/year/genre/track/ISRC), embeds the cover and (optionally)
//! plain lyrics into a downloaded file with `lofty`, which maps each tag to the
//! right frame per format (ID3 TSRC, MP4 iTunes atom, Vorbis `ISRC`, …). The
//! catalogue lookups are Apple Music, Deezer and MusicBrainz; lyrics come from
//! LRCLIB. The .nfo sidecar and music-folder relocation live in the apply route.

use lofty::config::WriteOptions;
use lofty::file::TaggedFileExt;
use lofty::picture::{MimeType, Picture, PictureType};
use lofty::prelude::{Accessor, ItemKey, TagExt};
use lofty::tag::Tag;

pub struct ApplyFields {
    pub path: String,
    pub title: Option<String>,
    pub artist: Option<String>,
    pub album: Option<String>,
    pub year: Option<String>,
    pub genre: Option<String>,
    pub track_number: Option<u32>,
    pub isrc: Option<String>,
    /// Already-fetched cover bytes (JPEG/PNG), if any.
    pub cover: Option<Vec<u8>>,
}

fn sniff_mime(bytes: &[u8]) -> MimeType {
    if bytes.starts_with(&[0x89, 0x50, 0x4E, 0x47]) {
        MimeType::Png
    } else {
        MimeType::Jpeg
    }
}

/// Write the tags + cover into the file. Returns whether a cover was embedded.
pub fn write_tags(f: &ApplyFields) -> Result<bool, String> {
    let mut tagged = lofty::read_from_path(&f.path).map_err(|e| e.to_string())?;
    let tag_type = tagged.primary_tag_type();
    if tagged.primary_tag_mut().is_none() {
        tagged.insert_tag(Tag::new(tag_type));
    }
    let tag = tagged
        .primary_tag_mut()
        .ok_or_else(|| "this file type cannot be tagged".to_string())?;

    if let Some(t) = &f.title {
        tag.set_title(t.clone());
    }
    if let Some(a) = &f.artist {
        tag.set_artist(a.clone());
    }
    if let Some(al) = &f.album {
        tag.set_album(al.clone());
    }
    if let Some(y) = f.year.as_ref().and_then(|y| y.parse::<u32>().ok()) {
        tag.set_year(y);
    }
    if let Some(g) = &f.genre {
        tag.set_genre(g.clone());
    }
    if let Some(tn) = f.track_number {
        tag.set_track(tn);
    }
    if let Some(isrc) = &f.isrc {
        tag.insert_text(ItemKey::Isrc, isrc.clone());
    }

    let mut embedded = false;
    if let Some(bytes) = &f.cover {
        let mime = sniff_mime(bytes);
        tag.push_picture(Picture::new_unchecked(
            PictureType::CoverFront,
            Some(mime),
            None,
            bytes.clone(),
        ));
        embedded = true;
    }

    tag.save_to_path(&f.path, WriteOptions::default())
        .map_err(|e| e.to_string())?;
    Ok(embedded)
}

/// Embed plain lyrics into the file's primary tag (best-effort). Mirrors the
/// cover/ISRC path in `write_tags`: open, ensure a tag, set the lyrics field, save.
pub fn embed_lyrics(path: &str, text: &str) -> Result<(), String> {
    let mut tagged = lofty::read_from_path(path).map_err(|e| e.to_string())?;
    let tag_type = tagged.primary_tag_type();
    if tagged.primary_tag_mut().is_none() {
        tagged.insert_tag(Tag::new(tag_type));
    }
    let tag = tagged
        .primary_tag_mut()
        .ok_or_else(|| "this file type cannot be tagged".to_string())?;
    tag.insert_text(ItemKey::Lyrics, text.to_string());
    tag.save_to_path(path, WriteOptions::default())
        .map_err(|e| e.to_string())
}

/// Fetch cover bytes (best-effort) for embedding.
pub async fn fetch_cover(url: &str) -> Option<Vec<u8>> {
    let resp = reqwest::Client::builder()
        .user_agent("Yoink")
        .build()
        .ok()?
        .get(url)
        .send()
        .await
        .ok()?;
    resp.bytes().await.ok().map(|b| b.to_vec())
}

// --- catalogue search (Apple Music + Deezer) for the auto-tag card ---------

use std::sync::OnceLock;

use regex::Regex;
use serde::Serialize;
use serde_json::Value;
use unicode_normalization::UnicodeNormalization;

#[derive(Serialize, Clone)]
pub struct TagCandidate {
    pub title: String,
    pub artist: String,
    pub album: Option<String>,
    pub year: Option<String>,
    pub genre: Option<String>,
    pub track_number: Option<i64>,
    pub cover_url: Option<String>,
}

fn http() -> reqwest::Client {
    reqwest::Client::builder()
        .user_agent("Yoink")
        .build()
        .unwrap_or_default()
}

async fn get_json(url: &str, params: &[(&str, &str)]) -> Option<Value> {
    http()
        .get(url)
        .query(params)
        .send()
        .await
        .ok()?
        .json::<Value>()
        .await
        .ok()
}

fn sget(v: &Value, k: &str) -> Option<String> {
    v.get(k)
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
}

fn clean_album(name: Option<String>) -> Option<String> {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| Regex::new(r"(?i)\s*-\s*(?:single|ep)$").unwrap());
    name.map(|n| re.replace(&n, "").trim().to_string())
        .filter(|n| !n.is_empty())
}

fn user_country() -> Option<String> {
    for key in ["LC_ALL", "LC_MESSAGES", "LANG"] {
        if let Ok(v) = std::env::var(key) {
            if let Some((_, rest)) = v.split_once('_') {
                let region: String = rest.chars().take(2).collect();
                if region.chars().all(|c| c.is_ascii_alphabetic()) && region.len() == 2 {
                    return Some(region.to_uppercase());
                }
            }
        }
    }
    None
}

async fn itunes_search(artist: &str, title: &str) -> Vec<TagCandidate> {
    let term = format!("{artist} {title}");
    let term = term.trim();
    if term.is_empty() {
        return vec![];
    }
    let mut stores: Vec<Option<String>> = vec![None];
    if let Some(region) = user_country() {
        if region != "US" {
            stores.insert(0, Some(region));
        }
    }
    let mut out = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for country in stores {
        let mut params = vec![("term", term), ("entity", "song"), ("limit", "8")];
        if let Some(c) = &country {
            params.push(("country", c));
        }
        let Some(data) = get_json("https://itunes.apple.com/search", &params).await else {
            continue;
        };
        for item in data
            .get("results")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let artist = sget(item, "artistName").unwrap_or_default();
            let title = sget(item, "trackName").unwrap_or_default();
            let key = (artist.to_lowercase(), title.to_lowercase());
            if !seen.insert(key) {
                continue;
            }
            let date = item
                .get("releaseDate")
                .and_then(Value::as_str)
                .unwrap_or("");
            out.push(TagCandidate {
                title,
                artist,
                album: clean_album(sget(item, "collectionName")),
                year: (date.len() >= 4).then(|| date[..4].to_string()),
                genre: sget(item, "primaryGenreName"),
                track_number: item.get("trackNumber").and_then(Value::as_i64),
                cover_url: sget(item, "artworkUrl100")
                    .map(|a| a.replace("100x100bb", "1000x1000bb")),
            });
        }
    }
    out
}

async fn deezer_search(artist: &str, title: &str) -> Vec<TagCandidate> {
    let term = format!("{artist} {title}");
    let term = term.trim();
    if term.is_empty() {
        return vec![];
    }
    let Some(data) = get_json(
        "https://api.deezer.com/search",
        &[("q", term), ("limit", "8")],
    )
    .await
    else {
        return vec![];
    };
    data.get("data")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .map(|item| {
            let album = item.get("album");
            TagCandidate {
                title: sget(item, "title").unwrap_or_default(),
                artist: item
                    .get("artist")
                    .and_then(|a| sget(a, "name"))
                    .unwrap_or_default(),
                album: album.and_then(|a| sget(a, "title")),
                year: None,
                genre: None,
                track_number: None,
                cover_url: album.and_then(|a| sget(a, "cover_xl").or_else(|| sget(a, "cover_big"))),
            }
        })
        .collect()
}

fn norm_for_match(text: &str) -> String {
    static PAREN: OnceLock<Regex> = OnceLock::new();
    static NONALNUM: OnceLock<Regex> = OnceLock::new();
    let paren = PAREN.get_or_init(|| Regex::new(r"[\(\[][^\)\]]*[\)\]]").unwrap());
    let nonalnum = NONALNUM.get_or_init(|| Regex::new(r"[^a-z0-9]+").unwrap());
    let deaccented: String = text
        .nfkd()
        .filter(|c| !matches!(*c as u32, 0x0300..=0x036F))
        .collect::<String>()
        .to_lowercase();
    let no_paren = paren.replace_all(&deaccented, " ");
    nonalnum.replace_all(&no_paren, " ").trim().to_string()
}

fn relevant(cands: Vec<TagCandidate>, title: &str) -> Vec<TagCandidate> {
    let query = norm_for_match(title);
    let qtok: std::collections::HashSet<&str> =
        query.split_whitespace().filter(|t| t.len() >= 2).collect();
    if qtok.is_empty() {
        return cands;
    }
    cands
        .into_iter()
        .filter(|c| {
            let norm = norm_for_match(&c.title);
            let ctok: std::collections::HashSet<&str> =
                norm.split_whitespace().filter(|t| t.len() >= 2).collect();
            ctok.is_empty()
                || qtok.intersection(&ctok).next().is_some()
                || norm.contains(&query)
                || query.contains(&norm)
        })
        .collect()
}

const VERSION_EXTRAS: &[&str] = &[
    "remix",
    "version",
    "live",
    "edit",
    "acoustic",
    "instrumental",
    "sped up",
    "slowed",
    "cover",
    "karaoke",
];

fn rank(mut results: Vec<TagCandidate>, artist: &str, title: &str) -> Vec<TagCandidate> {
    let qt = title.trim().to_lowercase();
    let qa = artist.trim().to_lowercase();
    let score = |c: &TagCandidate| -> i64 {
        let ct = c.title.trim().to_lowercase();
        let mut s = 0i64;
        if ct == qt {
            s += 100;
        } else if !qt.is_empty() && ct.contains(&qt) {
            s += 40;
        }
        for extra in VERSION_EXTRAS {
            if ct.contains(extra) && !qt.contains(extra) {
                s -= 25;
            }
        }
        s -= (ct.len() as i64 - qt.len() as i64).abs() / 8;
        if !qa.is_empty() && c.artist.trim().to_lowercase().contains(&qa) {
            s += 15;
        }
        s
    };
    results.sort_by_key(|c| std::cmp::Reverse(score(c)));
    results
}

async fn auto_search(artist: &str, title: &str) -> Vec<TagCandidate> {
    let mut combined = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for results in [
        itunes_search(artist, title).await,
        deezer_search(artist, title).await,
    ] {
        for cand in results {
            let key = (
                cand.artist.trim().to_lowercase(),
                cand.title.trim().to_lowercase(),
            );
            if seen.insert(key) {
                combined.push(cand);
            }
        }
    }
    // MusicBrainz is a fallback only when both fast sources come up empty
    // (broad coverage, but rate-limited).
    if combined.is_empty() {
        return musicbrainz_search(artist, title).await;
    }
    combined
}

/// Search the chosen catalogue (auto / apple / deezer), ranked, unrelated dropped.
pub async fn search_catalogue(source: &str, artist: &str, title: &str) -> Vec<TagCandidate> {
    let results = match source {
        "deezer" => deezer_search(artist, title).await,
        "apple" | "itunes" => itunes_search(artist, title).await,
        "musicbrainz" => musicbrainz_search(artist, title).await,
        _ => auto_search(artist, title).await, // "auto" = Apple + Deezer, MusicBrainz fallback
    };
    rank(relevant(results, title), artist, title)
}

fn strip_noise(s: &str) -> String {
    s.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// Best-effort (artist, title) from a download filename (mirrors
/// guess_from_filename): strip the extension + trailing tags, split on " - ".
pub fn guess_from_filename(name: &str) -> (String, String) {
    static TAGS: OnceLock<Regex> = OnceLock::new();
    static DASH: OnceLock<Regex> = OnceLock::new();
    // Bracketed noise tags, English + Spanish + French, incl. accented "vídeo".
    let tags = TAGS.get_or_init(|| {
        Regex::new(r"(?i)\s*[\(\[][^\)\]]*?\b(?:official|oficial|officiel|video|v[ií]deo|videoclip|clip|audio|lyrics?|letras?|visualizer|visualiser|hd|4k|mv|prod|explicit|remaster)\b[^\)\]]*[\)\]]").unwrap()
    });
    let dash = DASH.get_or_init(|| Regex::new(r"^(.+?)\s[-\x{2013}\x{2014}]\s(.+)$").unwrap());

    // Fold fullwidth / CJK punctuation yt-dlp leaves in filenames to ASCII, so the
    // noise strippers catch "（Official MV）", "Song ｜ VIDEO", "Title： Part 2".
    let folded: String = name
        .chars()
        .map(|c| match c {
            '：' => ':',
            '｜' => '|',
            '（' => '(',
            '）' => ')',
            '【' => '[',
            '】' => ']',
            other => other,
        })
        .collect();
    let base = folded.rsplit_once('.').map(|(b, _)| b).unwrap_or(&folded);
    let base = tags.replace_all(base, "");
    let base = strip_title_noise(&base);
    if let Some(caps) = dash.captures(&base) {
        let artist = strip_title_noise(&caps[1]);
        let title = strip_title_noise(&caps[2]);
        return (artist, title);
    }
    (String::new(), base)
}

/// Strip trailing un-bracketed YouTube noise, a trailing "feat …", and wrapping
/// quotes — what muddies the catalogue query. Mirrors legacy `_strip_noise`:
/// handles "- Official Video", "｜ MV", and the Spanish "… Vídeo/Audio Oficial".
fn strip_title_noise(text: &str) -> String {
    static FEAT: OnceLock<Regex> = OnceLock::new();
    static TRAILING: OnceLock<Regex> = OnceLock::new();
    static TRAILING_ES: OnceLock<Regex> = OnceLock::new();
    let feat = FEAT.get_or_init(|| {
        Regex::new(r"(?i)\s*[\(\[]?\s*\b(?:feat|ft|featuring)\b\.?\s+[^\)\]]+[\)\]]?\s*$").unwrap()
    });
    let trailing = TRAILING.get_or_init(|| {
        Regex::new(r"(?i)\s*(?:[|\x{FF5C}\-\x{2013}\x{2014}]\s*(?:official\s+|oficial\s+|full\s+|music\s+|lyrics?\s+)*|(?:official\s+|oficial\s+|full\s+|music\s+|lyrics?\s+)+)(?:video|v[ií]deo|videoclip|audio|visualizer|visualiser|mv|hd|4k|hq)(?:\s+oficial)?\s*$").unwrap()
    });
    // Spanish word order "… Vídeo/Videoclip/Audio Oficial" with no leading
    // separator — unambiguous noise (requires the trailing "oficial" to stay safe).
    let trailing_es = TRAILING_ES
        .get_or_init(|| Regex::new(r"(?i)\s+(?:v[ií]deo|videoclip|audio)\s+oficial\s*$").unwrap());

    let mut s = feat.replace(text, "").into_owned();
    loop {
        let stripped = trailing.replace(&s, "");
        let stripped = trailing_es.replace(&stripped, "");
        let next = strip_noise(stripped.trim());
        if next == s {
            break;
        }
        s = next;
    }
    s.trim()
        .trim_matches([
            '"', '\'', '`', '\u{2018}', '\u{2019}', '\u{201C}', '\u{201D}',
        ])
        .trim()
        .to_string()
}

// --- lyrics (LRCLIB) -------------------------------------------------------

pub struct LyricsResult {
    pub found: bool,
    pub instrumental: bool,
    pub has_synced: bool,
    pub plain: Option<String>,
}

fn to_lyrics(rec: &Value) -> Option<(Option<String>, bool, bool)> {
    let instrumental = rec
        .get("instrumental")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let nz = |k: &str| {
        rec.get(k)
            .and_then(Value::as_str)
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
    };
    let plain = nz("plainLyrics");
    let synced = nz("syncedLyrics");
    if !instrumental && plain.is_none() && synced.is_none() {
        return None;
    }
    Some((plain, synced.is_some(), instrumental))
}

/// Audio duration (seconds) from the file, for LRCLIB's exact signature match.
pub fn probe_duration(path: &str) -> Option<f64> {
    use lofty::file::AudioFile;
    let tagged = lofty::read_from_path(path).ok()?;
    Some(tagged.properties().duration().as_secs_f64())
}

/// Look up lyrics on LRCLIB (keyless). Mirrors lyrics.fetch_lyrics (the exact
/// /get with duration, then /search by track+artist).
pub async fn fetch_lyrics(
    title: &str,
    artist: &str,
    album: Option<&str>,
    duration: Option<f64>,
) -> LyricsResult {
    let empty = LyricsResult {
        found: false,
        instrumental: false,
        has_synced: false,
        plain: None,
    };
    let (title, artist) = (title.trim(), artist.trim());
    if title.is_empty() {
        return empty;
    }
    let build = |rec: &Value| {
        to_lyrics(rec).map(|(plain, has_synced, instrumental)| LyricsResult {
            found: true,
            instrumental,
            has_synced,
            plain,
        })
    };

    if let Some(d) = duration {
        let dur = (d as i64).to_string();
        let mut params = vec![
            ("track_name", title),
            ("artist_name", artist),
            ("duration", dur.as_str()),
        ];
        if let Some(al) = album.filter(|a| !a.is_empty()) {
            params.push(("album_name", al));
        }
        if let Some(got) = get_json("https://lrclib.net/api/get", &params).await {
            if let Some(r) = build(&got) {
                return r;
            }
        }
    }

    if let Some(hits) = get_json(
        "https://lrclib.net/api/search",
        &[("track_name", title), ("artist_name", artist)],
    )
    .await
    {
        for hit in hits.as_array().into_iter().flatten() {
            if let Some(r) = build(hit) {
                return r;
            }
        }
    }
    empty
}

// --- MusicBrainz (fallback when Apple + Deezer both come up empty) ----------

fn mb_escape(v: &str) -> String {
    v.chars()
        .flat_map(|c| {
            if c == '"' || c == '\\' {
                vec!['\\', c]
            } else {
                vec![c]
            }
        })
        .collect()
}

async fn musicbrainz_search(artist: &str, title: &str) -> Vec<TagCandidate> {
    if title.trim().is_empty() {
        return vec![];
    }
    let mut terms = vec![format!("recording:\"{}\"", mb_escape(title))];
    if !artist.trim().is_empty() {
        terms.insert(0, format!("artist:\"{}\"", mb_escape(artist)));
    }
    let q = terms.join(" AND ");
    // MusicBrainz requires a descriptive, contactable User-Agent.
    let client = reqwest::Client::builder()
        .user_agent("Yoink/4.4.0 (+https://github.com/ayozetr/yoink-app)")
        .build()
        .unwrap_or_default();
    let data = match client
        .get("https://musicbrainz.org/ws/2/recording")
        .query(&[("query", q.as_str()), ("fmt", "json"), ("limit", "8")])
        .send()
        .await
    {
        Ok(r) => r.json::<Value>().await.ok(),
        Err(_) => None,
    };
    let Some(data) = data else { return vec![] };
    let mut out = Vec::new();
    for rec in data
        .get("recordings")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let name = rec
            .get("artist-credit")
            .and_then(Value::as_array)
            .map(|cs| {
                cs.iter()
                    .map(|c| {
                        c.get("name")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string()
                            + c.get("joinphrase").and_then(Value::as_str).unwrap_or("")
                    })
                    .collect::<String>()
            })
            .unwrap_or_default();
        let release = rec
            .get("releases")
            .and_then(Value::as_array)
            .and_then(|r| r.first());
        let mbid = release.and_then(|r| sget(r, "id"));
        let date = release
            .and_then(|r| r.get("date").and_then(Value::as_str))
            .unwrap_or("");
        out.push(TagCandidate {
            title: sget(rec, "title").unwrap_or_default(),
            artist: name,
            album: release.and_then(|r| sget(r, "title")),
            year: (date.len() >= 4).then(|| date[..4].to_string()),
            genre: None,
            track_number: None,
            // Cover Art Archive serves the front cover by release MBID (307 → image, else 404).
            cover_url: mbid.map(|id| format!("https://coverartarchive.org/release/{id}/front-500")),
        });
    }
    out
}

#[cfg(test)]
mod autotag_tests {
    use super::{clean_album, guess_from_filename};

    #[test]
    fn guess_from_filename_cases() {
        let cases: &[(&str, &str, &str)] = &[
            (
                "Las Ninyas del Corro - Hood Films.m4a",
                "Las Ninyas del Corro",
                "Hood Films",
            ),
            ("Artist - Title (prod. X) [4K].opus", "Artist", "Title"),
            ("JustATitle.flac", "", "JustATitle"),
            ("Soft Cell - Tainted Love.mp3", "Soft Cell", "Tainted Love"),
            (
                "Drake - Hotline Bling (Music Video) [4K].mp3",
                "Drake",
                "Hotline Bling",
            ),
            (
                "Quevedo - Columbia (Vídeo Oficial).m4a",
                "Quevedo",
                "Columbia",
            ),
            (
                "Aitana - Mariposas (Audio Oficial).mp3",
                "Aitana",
                "Mariposas",
            ),
            ("Morad - Pelele (Letra).mp3", "Morad", "Pelele"),
            // Un-bracketed trailing noise (English + Spanish word order).
            ("Artist - Song - Official Audio.mp3", "Artist", "Song"),
            (
                "Quevedo - Columbia Vídeo Oficial.mp3",
                "Quevedo",
                "Columbia",
            ),
            // Fullwidth colon yt-dlp leaves on disk, folded back to ASCII.
            ("Artist - Title： Part 2.mp3", "Artist", "Title: Part 2"),
        ];
        for (name, artist, title) in cases {
            assert_eq!(
                guess_from_filename(name),
                (artist.to_string(), title.to_string()),
                "guess_from_filename({name:?})"
            );
        }
    }

    #[test]
    fn clean_album_strips_single_and_ep_suffix() {
        assert_eq!(
            clean_album(Some("Hood Films - Single".into())),
            Some("Hood Films".into())
        );
        assert_eq!(
            clean_album(Some("#SKIT2025 - EP".into())),
            Some("#SKIT2025".into())
        );
        assert_eq!(
            clean_album(Some("Whenever You Need Somebody".into())),
            Some("Whenever You Need Somebody".into())
        );
        assert_eq!(clean_album(None), None);
    }
}

#[cfg(test)]
mod lyrics_tests {
    use super::to_lyrics;
    use serde_json::json;

    #[test]
    fn plain_and_synced_present() {
        let (plain, has_synced, instrumental) = to_lyrics(
            &json!({"plainLyrics":"la la la","syncedLyrics":"[00:01.00] la","instrumental":false}),
        )
        .expect("some");
        assert_eq!(plain.as_deref(), Some("la la la"));
        assert!(has_synced);
        assert!(!instrumental);
    }

    #[test]
    fn instrumental_has_no_plain() {
        let (plain, has_synced, instrumental) =
            to_lyrics(&json!({"instrumental":true,"plainLyrics":null})).expect("some");
        assert!(instrumental);
        assert!(plain.is_none());
        assert!(!has_synced);
    }

    #[test]
    fn none_when_nothing_found() {
        assert!(
            to_lyrics(&json!({"instrumental":false,"plainLyrics":"","syncedLyrics":""})).is_none()
        );
        assert!(to_lyrics(&json!({})).is_none());
    }
}
