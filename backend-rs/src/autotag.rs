// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Audio auto-tagging — the write side of services/autotag_service.py. Writes the
//! chosen metadata (title/artist/album/year/genre/track/ISRC) and embeds the cover
//! into a downloaded file with `lofty`, which maps each tag to the right frame per
//! format (ID3 TSRC, MP4 iTunes atom, Vorbis `ISRC`, …). The catalogue lookups
//! (Apple/Deezer/MusicBrainz), lyrics and .nfo/music-folders are later slices.

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
    reqwest::Client::builder().user_agent("Yoink").build().unwrap_or_default()
}

async fn get_json(url: &str, params: &[(&str, &str)]) -> Option<Value> {
    http().get(url).query(params).send().await.ok()?.json::<Value>().await.ok()
}

fn sget(v: &Value, k: &str) -> Option<String> {
    v.get(k).and_then(Value::as_str).filter(|s| !s.is_empty()).map(str::to_string)
}

fn clean_album(name: Option<String>) -> Option<String> {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| Regex::new(r"(?i)\s*-\s*(?:single|ep)$").unwrap());
    name.map(|n| re.replace(&n, "").trim().to_string()).filter(|n| !n.is_empty())
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
        let Some(data) = get_json("https://itunes.apple.com/search", &params).await else { continue };
        for item in data.get("results").and_then(Value::as_array).into_iter().flatten() {
            let artist = sget(item, "artistName").unwrap_or_default();
            let title = sget(item, "trackName").unwrap_or_default();
            let key = (artist.to_lowercase(), title.to_lowercase());
            if !seen.insert(key) {
                continue;
            }
            let date = item.get("releaseDate").and_then(Value::as_str).unwrap_or("");
            out.push(TagCandidate {
                title,
                artist,
                album: clean_album(sget(item, "collectionName")),
                year: (date.len() >= 4).then(|| date[..4].to_string()),
                genre: sget(item, "primaryGenreName"),
                track_number: item.get("trackNumber").and_then(Value::as_i64),
                cover_url: sget(item, "artworkUrl100").map(|a| a.replace("100x100bb", "1000x1000bb")),
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
    let Some(data) = get_json("https://api.deezer.com/search", &[("q", term), ("limit", "8")]).await
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
                artist: item.get("artist").and_then(|a| sget(a, "name")).unwrap_or_default(),
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
    let qtok: std::collections::HashSet<&str> = query.split_whitespace().filter(|t| t.len() >= 2).collect();
    if qtok.is_empty() {
        return cands;
    }
    cands
        .into_iter()
        .filter(|c| {
            let norm = norm_for_match(&c.title);
            let ctok: std::collections::HashSet<&str> = norm.split_whitespace().filter(|t| t.len() >= 2).collect();
            ctok.is_empty() || qtok.intersection(&ctok).next().is_some() || norm.contains(&query) || query.contains(&norm)
        })
        .collect()
}

const VERSION_EXTRAS: &[&str] = &[
    "remix", "version", "live", "edit", "acoustic", "instrumental", "sped up", "slowed", "cover", "karaoke",
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
    results.sort_by(|a, b| score(b).cmp(&score(a)));
    results
}

async fn auto_search(artist: &str, title: &str) -> Vec<TagCandidate> {
    let mut combined = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for results in [itunes_search(artist, title).await, deezer_search(artist, title).await] {
        for cand in results {
            let key = (cand.artist.trim().to_lowercase(), cand.title.trim().to_lowercase());
            if seen.insert(key) {
                combined.push(cand);
            }
        }
    }
    combined
}

/// Search the chosen catalogue (auto / apple / deezer), ranked, unrelated dropped.
pub async fn search_catalogue(source: &str, artist: &str, title: &str) -> Vec<TagCandidate> {
    let results = match source {
        "deezer" => deezer_search(artist, title).await,
        "apple" | "itunes" => itunes_search(artist, title).await,
        _ => auto_search(artist, title).await, // "auto" (+ musicbrainz fallback: TODO)
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
    static PIPE: OnceLock<Regex> = OnceLock::new();
    let tags = TAGS.get_or_init(|| {
        Regex::new(r"(?i)\s*[\(\[][^\)\]]*(?:official|lyric|audio|video|visuali[sz]er|prod|hd|4k|mv|remaster)[^\)\]]*[\)\]]|\s*\b(?:feat\.?|ft\.?|featuring)\s.+$").unwrap()
    });
    let dash = DASH.get_or_init(|| Regex::new(r"^(.+?)\s[-\x{2013}\x{2014}]\s(.+)$").unwrap());
    let pipe = PIPE.get_or_init(|| Regex::new(r"\s*[|\x{FF5C}].*$").unwrap());

    let base = name.rsplit_once('.').map(|(b, _)| b).unwrap_or(name);
    let base = tags.replace_all(base, "");
    let base = strip_noise(&base);
    if let Some(caps) = dash.captures(&base) {
        let artist = strip_noise(&caps[1]);
        let raw_title = strip_noise(&caps[2]);
        let title = strip_noise(&pipe.replace(&raw_title, ""));
        return (artist, if title.is_empty() { raw_title } else { title });
    }
    (String::new(), base)
}
