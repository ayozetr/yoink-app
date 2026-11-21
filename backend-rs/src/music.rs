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

fn spotify_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"(?i)^(?:https?://)?(?:open\.spotify\.com/(?:intl-[a-z-]+/)?|spotify:)(track|album|playlist)[/:]([A-Za-z0-9]+)",
        )
        .unwrap()
    })
}

fn next_data_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r#"(?s)<script id="__NEXT_DATA__"[^>]*>(.*?)</script>"#).unwrap())
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

async fn get_text(url: &str) -> Result<String, String> {
    client()
        .get(url)
        .send()
        .await
        .map_err(|e| e.to_string())?
        .text()
        .await
        .map_err(|e| e.to_string())
}

async fn get_json_auth(url: &str, token: &str) -> Result<Value, String> {
    client()
        .get(url)
        .bearer_auth(token)
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

// --- Spotify (public embed + anonymous token) ------------------------------

/// Recursively find the first non-empty string value for `key` (mirrors `_find_key`).
fn find_key(obj: &Value, key: &str, depth: u32) -> Option<String> {
    if depth > 7 {
        return None;
    }
    match obj {
        Value::Object(map) => {
            for (k, v) in map {
                if k == key {
                    if let Some(st) = v.as_str() {
                        if !st.is_empty() {
                            return Some(st.to_string());
                        }
                    }
                }
                if let Some(found) = find_key(v, key, depth + 1) {
                    return Some(found);
                }
            }
            None
        }
        Value::Array(arr) => arr.iter().take(5).find_map(|v| find_key(v, key, depth + 1)),
        _ => None,
    }
}

fn sp_cover(entity: &Value) -> Option<String> {
    if let Some(last) = entity
        .get("visualIdentity")
        .and_then(|v| v.get("image"))
        .and_then(Value::as_array)
        .and_then(|im| im.last())
    {
        if let Some(u) = s(last, "url") {
            return Some(u);
        }
    }
    entity
        .get("coverArt")
        .and_then(|c| c.get("sources"))
        .and_then(Value::as_array)
        .and_then(|src| src.last())
        .and_then(|l| s(l, "url"))
}

fn sp_year(entity: &Value) -> Option<String> {
    let rd = entity.get("releaseDate")?;
    let text = if rd.is_object() {
        s(rd, "isoString").or_else(|| rd.get("year").map(|y| y.to_string().trim_matches('"').to_string()))
    } else if let Some(st) = rd.as_str() {
        Some(st.to_string())
    } else if rd.is_number() {
        Some(rd.to_string())
    } else {
        None
    };
    text.filter(|t| t.len() >= 4).map(|t| t.chars().take(4).collect())
}

fn join_artists(arr: Option<&Vec<Value>>) -> String {
    arr.map(|a| {
        a.iter()
            .filter_map(|x| s(x, "name"))
            .filter(|n| !n.is_empty())
            .collect::<Vec<_>>()
            .join(", ")
    })
    .unwrap_or_default()
}

async fn sp_api_tracks(kind: &str, sid: &str, token: &str) -> (Vec<Value>, bool) {
    let base = if kind == "playlist" { "playlists" } else { "albums" };
    let mut items: Vec<Value> = Vec::new();
    let mut offset = 0;
    while offset < 2000 {
        let url = format!("https://api.spotify.com/v1/{base}/{sid}/tracks?limit=50&offset={offset}");
        let page = match get_json_auth(&url, token).await {
            Ok(p) => p,
            Err(_) => return (items, false),
        };
        let page_items = page.get("items").and_then(Value::as_array).cloned().unwrap_or_default();
        let n = page_items.len();
        items.extend(page_items);
        if page.get("next").map_or(true, Value::is_null) || n == 0 {
            break;
        }
        offset += n;
    }
    (items, true)
}

fn sp_track_from_api(item: &Value, kind: &str, album_entity: &Value) -> Option<MusicTrack> {
    let track = if kind == "playlist" { item.get("track")? } else { item };
    let name = track.get("name").and_then(Value::as_str).filter(|n| !n.is_empty())?;
    let album = track.get("album");
    let (album_name, year, cover) = if kind == "playlist" {
        let images = album.and_then(|a| a.get("images")).and_then(Value::as_array);
        (
            album.and_then(|a| s(a, "name")),
            album
                .and_then(|a| s(a, "release_date"))
                .map(|d| d.chars().take(4).collect::<String>())
                .filter(|y| !y.is_empty()),
            images.and_then(|im| im.first()).and_then(|i| s(i, "url")),
        )
    } else {
        (s(album_entity, "name"), sp_year(album_entity), sp_cover(album_entity))
    };
    let tid = track.get("id").and_then(Value::as_str).unwrap_or("");
    Some(MusicTrack {
        title: name.to_string(),
        artists: join_artists(track.get("artists").and_then(Value::as_array)),
        isrc: track.get("external_ids").and_then(|e| s(e, "isrc")),
        duration_ms: track.get("duration_ms").and_then(Value::as_i64),
        is_explicit: track.get("explicit").and_then(Value::as_bool).unwrap_or(false),
        album: album_name,
        year,
        cover_url: cover,
        source_url: if tid.is_empty() {
            String::new()
        } else {
            format!("https://open.spotify.com/track/{tid}")
        },
    })
}

/// Fallback: the <=100-track list embedded in the page (no ISRC, no API token).
fn spotify_embed_tracklist(entity: &Value, kind: &str, cover: &Option<String>) -> (Vec<MusicTrack>, bool) {
    let is_album = kind == "album";
    let album_name = if is_album { s(entity, "name") } else { None };
    let album_year = if is_album { sp_year(entity) } else { None };
    let mut tracks = Vec::new();
    if let Some(list) = entity.get("trackList").and_then(Value::as_array) {
        for item in list {
            let Some(title) = item.get("title").and_then(Value::as_str).filter(|t| !t.is_empty()) else {
                continue;
            };
            let uri = item.get("uri").and_then(Value::as_str).unwrap_or("");
            let parts: Vec<&str> = uri.split(':').collect();
            let surl = if parts.len() == 3 {
                format!("https://open.spotify.com/{}/{}", parts[1], parts[2])
            } else {
                String::new()
            };
            tracks.push(MusicTrack {
                title: title.to_string(),
                artists: item.get("subtitle").and_then(Value::as_str).unwrap_or("").to_string(),
                isrc: None,
                duration_ms: item.get("duration").and_then(Value::as_i64),
                is_explicit: item.get("isExplicit").and_then(Value::as_bool).unwrap_or(false),
                album: album_name.clone(),
                year: album_year.clone(),
                cover_url: if is_album { cover.clone() } else { None },
                source_url: surl,
            });
        }
    }
    let truncated = tracks.len() >= 100;
    (tracks, truncated)
}

/// Resolve a Spotify track/album/playlist URL via the public embed page (+ the
/// anonymous API token it carries, for a full tracklist with ISRCs).
pub async fn resolve_spotify(url: &str) -> Result<MusicImportInfo, String> {
    let caps = spotify_re()
        .captures(url)
        .ok_or_else(|| "Not a recognised Spotify URL.".to_string())?;
    let kind = caps[1].to_lowercase();
    let sid = caps[2].to_string();

    let body = get_text(&format!("https://open.spotify.com/embed/{kind}/{sid}")).await?;
    let blob = next_data_re()
        .captures(&body)
        .ok_or_else(|| "Spotify embed page changed shape.".to_string())?;
    let data: Value = serde_json::from_str(&blob[1])
        .map_err(|_| "Could not parse the Spotify metadata.".to_string())?;
    let entity = data
        .pointer("/props/pageProps/state/data/entity")
        .ok_or_else(|| "Could not parse the Spotify metadata.".to_string())?;
    let token = find_key(&data, "accessToken", 0);
    let cover = sp_cover(entity);
    let name = s(entity, "name").or_else(|| s(entity, "title")).unwrap_or_default();

    if kind == "track" {
        let track = MusicTrack {
            title: name.clone(),
            artists: join_artists(entity.get("artists").and_then(Value::as_array)),
            isrc: None,
            duration_ms: entity.get("duration").and_then(Value::as_i64),
            is_explicit: entity.get("isExplicit").and_then(Value::as_bool).unwrap_or(false),
            album: None,
            year: sp_year(entity),
            cover_url: cover.clone(),
            source_url: format!("https://open.spotify.com/track/{sid}"),
        };
        return Ok(MusicImportInfo {
            source: "spotify".into(),
            kind: "track".into(),
            name: track.title.clone(),
            subtitle: Some(track.artists.clone()),
            cover_url: cover,
            tracks: vec![track],
            truncated: false,
        });
    }

    let (tracks, truncated) = if let Some(tok) = token {
        let (api_items, complete) = sp_api_tracks(&kind, &sid, &tok).await;
        if !api_items.is_empty() {
            let tr: Vec<MusicTrack> = api_items
                .iter()
                .filter_map(|it| sp_track_from_api(it, &kind, entity))
                .collect();
            (tr, !complete || api_items.len() >= 2000)
        } else {
            spotify_embed_tracklist(entity, &kind, &cover)
        }
    } else {
        spotify_embed_tracklist(entity, &kind, &cover)
    };

    let subtitle = if kind == "playlist" {
        s(entity, "subtitle")
    } else {
        tracks.first().map(|t| t.artists.clone())
    };
    Ok(MusicImportInfo {
        source: "spotify".into(),
        kind,
        name,
        subtitle,
        cover_url: cover,
        tracks,
        truncated,
    })
}
