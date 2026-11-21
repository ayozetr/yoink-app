// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Keyless music-import resolvers (port of services/music_import.py). Each source
//! turns a URL into the same MusicImportInfo shape; only the metadata is read —
//! audio is matched + downloaded from YouTube downstream. Deezer (public JSON
//! API) is ported here; Spotify/Apple/Tidal/Amazon are later slices.

use std::sync::OnceLock;

use regex::Regex;
use serde::Serialize;
use serde_json::Value;

#[derive(Serialize, Clone)]
pub struct MusicTrack {
    pub title: String,
    pub artists: String,
    pub isrc: Option<String>,
    pub duration_ms: Option<i64>,
    pub is_explicit: bool,
    pub album: Option<String>,
    pub year: Option<String>,
    pub cover_url: Option<String>,
    pub source_url: String,
}

#[derive(Serialize)]
pub struct MusicImportInfo {
    pub source: String,
    #[serde(rename = "type")]
    pub kind: String,
    pub name: String,
    pub subtitle: Option<String>,
    pub cover_url: Option<String>,
    pub tracks: Vec<MusicTrack>,
    pub truncated: bool,
}

fn deezer_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"(?i)^(?:https?://)?(?:www\.)?(?:deezer\.com|deezer\.page\.link)/(?:[a-z]{2}/)?(track|album|playlist)/(\d+)",
        )
        .unwrap()
    })
}

/// Detect the music service for a URL (only the services we can resolve).
pub fn detect_source(url: &str) -> Option<&'static str> {
    let u = url.to_lowercase();
    if u.contains("spotify.com") || u.starts_with("spotify:") {
        Some("spotify")
    } else if u.contains("deezer.com") || u.contains("deezer.page.link") || u.contains("dzr.page.link") {
        Some("deezer")
    } else if u.contains("music.apple.com") {
        Some("apple")
    } else if u.contains("tidal.com") {
        Some("tidal")
    } else if u.contains("music.amazon.") {
        Some("amazon")
    } else {
        None
    }
}

fn client() -> reqwest::Client {
    reqwest::Client::builder()
        .user_agent("Yoink")
        .build()
        .unwrap_or_default()
}

async fn get_json(url: &str) -> Result<Value, String> {
    client()
        .get(url)
        .send()
        .await
        .map_err(|e| e.to_string())?
        .json::<Value>()
        .await
        .map_err(|e| e.to_string())
}

async fn final_url(url: &str) -> Result<String, String> {
    Ok(client()
        .get(url)
        .send()
        .await
        .map_err(|e| e.to_string())?
        .url()
        .to_string())
}

fn s(v: &Value, key: &str) -> Option<String> {
    v.get(key).and_then(Value::as_str).map(str::to_string)
}

fn deezer_track(
    item: &Value,
    album_name: Option<&str>,
    year: Option<&str>,
    cover: Option<&str>,
) -> Option<MusicTrack> {
    let title = item.get("title").and_then(Value::as_str).filter(|t| !t.is_empty())?;
    let alb = item.get("album");
    let dur = item.get("duration").and_then(Value::as_i64);
    Some(MusicTrack {
        title: title.to_string(),
        artists: item
            .get("artist")
            .and_then(|a| a.get("name"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        isrc: s(item, "isrc"),
        duration_ms: dur.map(|d| d * 1000),
        is_explicit: item.get("explicit_lyrics").and_then(Value::as_bool).unwrap_or(false),
        album: album_name
            .map(str::to_string)
            .or_else(|| alb.and_then(|a| s(a, "title"))),
        year: year.map(str::to_string),
        cover_url: cover.map(str::to_string).or_else(|| {
            alb.and_then(|a| s(a, "cover_xl").or_else(|| s(a, "cover_big")))
        }),
        source_url: s(item, "link").unwrap_or_default(),
    })
}

/// Resolve a Deezer track/album/playlist URL via the keyless public API.
pub async fn resolve_deezer(url: &str) -> Result<MusicImportInfo, String> {
    // Short share links (dzr.page.link/…) redirect to the canonical URL.
    let url = if deezer_re().is_match(url) {
        url.to_string()
    } else {
        final_url(url).await?
    };
    let caps = deezer_re()
        .captures(&url)
        .ok_or_else(|| "Not a recognised Deezer URL.".to_string())?;
    let kind = caps[1].to_lowercase();
    let did = &caps[2];
    let data = get_json(&format!("https://api.deezer.com/{kind}/{did}")).await?;
    if data.get("error").is_some() {
        return Err("Deezer couldn't resolve that URL.".into());
    }
    let cover = s(&data, "cover_xl")
        .or_else(|| s(&data, "picture_xl"))
        .or_else(|| s(&data, "cover_big"));

    if kind == "track" {
        let alb = data.get("album");
        let cover = cover.clone().or_else(|| {
            alb.and_then(|a| s(a, "cover_xl").or_else(|| s(a, "cover_big")))
        });
        let album_name = alb.and_then(|a| a.get("title")).and_then(Value::as_str);
        let year = s(&data, "release_date").map(|d| d.chars().take(4).collect::<String>());
        let track = deezer_track(&data, album_name, year.as_deref().filter(|y| !y.is_empty()), cover.as_deref())
            .ok_or_else(|| "Deezer returned no track.".to_string())?;
        return Ok(MusicImportInfo {
            source: "deezer".into(),
            kind: "track".into(),
            name: track.title.clone(),
            subtitle: Some(track.artists.clone()),
            cover_url: cover,
            tracks: vec![track],
            truncated: false,
        });
    }

    let name = s(&data, "title").unwrap_or_default();
    let is_album = kind == "album";
    let album_name = if is_album { Some(name.clone()) } else { None };
    let album_year = if is_album {
        s(&data, "release_date")
            .map(|d| d.chars().take(4).collect::<String>())
            .filter(|y| !y.is_empty())
    } else {
        None
    };
    let subtitle = if is_album {
        data.get("artist").and_then(|a| s(a, "name"))
    } else {
        data.get("creator").and_then(|c| s(c, "name"))
    };

    let mut items: Vec<Value> = data
        .get("tracks")
        .and_then(|t| t.get("data"))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut next = data.get("tracks").and_then(|t| s(t, "next"));
    while let Some(n) = next.clone() {
        if items.len() >= 2000 {
            break;
        }
        let page = get_json(&n).await?;
        if let Some(arr) = page.get("data").and_then(Value::as_array) {
            items.extend(arr.iter().cloned());
        }
        next = s(&page, "next");
    }

    let track_cover = if is_album { cover.clone() } else { None };
    let tracks: Vec<MusicTrack> = items
        .iter()
        .filter_map(|it| {
            deezer_track(it, album_name.as_deref(), album_year.as_deref(), track_cover.as_deref())
        })
        .collect();
    let truncated = next.is_some();

    Ok(MusicImportInfo {
        source: "deezer".into(),
        kind,
        name,
        subtitle,
        cover_url: cover,
        tracks,
        truncated,
    })
}
