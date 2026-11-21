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
    } else if u.contains("deezer.com")
        || u.contains("deezer.page.link")
        || u.contains("dzr.page.link")
    {
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
    let title = item
        .get("title")
        .and_then(Value::as_str)
        .filter(|t| !t.is_empty())?;
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
        is_explicit: item
            .get("explicit_lyrics")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        album: album_name
            .map(str::to_string)
            .or_else(|| alb.and_then(|a| s(a, "title"))),
        year: year.map(str::to_string),
        cover_url: cover
            .map(str::to_string)
            .or_else(|| alb.and_then(|a| s(a, "cover_xl").or_else(|| s(a, "cover_big")))),
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
        let cover = cover
            .clone()
            .or_else(|| alb.and_then(|a| s(a, "cover_xl").or_else(|| s(a, "cover_big"))));
        let album_name = alb.and_then(|a| a.get("title")).and_then(Value::as_str);
        let year = s(&data, "release_date").map(|d| d.chars().take(4).collect::<String>());
        let track = deezer_track(
            &data,
            album_name,
            year.as_deref().filter(|y| !y.is_empty()),
            cover.as_deref(),
        )
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
            deezer_track(
                it,
                album_name.as_deref(),
                album_year.as_deref(),
                track_cover.as_deref(),
            )
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
        s(rd, "isoString").or_else(|| {
            rd.get("year")
                .map(|y| y.to_string().trim_matches('"').to_string())
        })
    } else if let Some(st) = rd.as_str() {
        Some(st.to_string())
    } else if rd.is_number() {
        Some(rd.to_string())
    } else {
        None
    };
    text.filter(|t| t.len() >= 4)
        .map(|t| t.chars().take(4).collect())
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
    let base = if kind == "playlist" {
        "playlists"
    } else {
        "albums"
    };
    let mut items: Vec<Value> = Vec::new();
    let mut offset = 0;
    while offset < 2000 {
        let url =
            format!("https://api.spotify.com/v1/{base}/{sid}/tracks?limit=50&offset={offset}");
        let page = match get_json_auth(&url, token).await {
            Ok(p) => p,
            Err(_) => return (items, false),
        };
        let page_items = page
            .get("items")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        let n = page_items.len();
        items.extend(page_items);
        if page.get("next").is_none_or(Value::is_null) || n == 0 {
            break;
        }
        offset += n;
    }
    (items, true)
}

fn sp_track_from_api(item: &Value, kind: &str, album_entity: &Value) -> Option<MusicTrack> {
    let track = if kind == "playlist" {
        item.get("track")?
    } else {
        item
    };
    let name = track
        .get("name")
        .and_then(Value::as_str)
        .filter(|n| !n.is_empty())?;
    let album = track.get("album");
    let (album_name, year, cover) = if kind == "playlist" {
        let images = album
            .and_then(|a| a.get("images"))
            .and_then(Value::as_array);
        (
            album.and_then(|a| s(a, "name")),
            album
                .and_then(|a| s(a, "release_date"))
                .map(|d| d.chars().take(4).collect::<String>())
                .filter(|y| !y.is_empty()),
            images.and_then(|im| im.first()).and_then(|i| s(i, "url")),
        )
    } else {
        (
            s(album_entity, "name"),
            sp_year(album_entity),
            sp_cover(album_entity),
        )
    };
    let tid = track.get("id").and_then(Value::as_str).unwrap_or("");
    Some(MusicTrack {
        title: name.to_string(),
        artists: join_artists(track.get("artists").and_then(Value::as_array)),
        isrc: track.get("external_ids").and_then(|e| s(e, "isrc")),
        duration_ms: track.get("duration_ms").and_then(Value::as_i64),
        is_explicit: track
            .get("explicit")
            .and_then(Value::as_bool)
            .unwrap_or(false),
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
fn spotify_embed_tracklist(
    entity: &Value,
    kind: &str,
    cover: &Option<String>,
) -> (Vec<MusicTrack>, bool) {
    let is_album = kind == "album";
    let album_name = if is_album { s(entity, "name") } else { None };
    let album_year = if is_album { sp_year(entity) } else { None };
    let mut tracks = Vec::new();
    if let Some(list) = entity.get("trackList").and_then(Value::as_array) {
        for item in list {
            let Some(title) = item
                .get("title")
                .and_then(Value::as_str)
                .filter(|t| !t.is_empty())
            else {
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
                artists: item
                    .get("subtitle")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                isrc: None,
                duration_ms: item.get("duration").and_then(Value::as_i64),
                is_explicit: item
                    .get("isExplicit")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
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
    let name = s(entity, "name")
        .or_else(|| s(entity, "title"))
        .unwrap_or_default();

    if kind == "track" {
        let track = MusicTrack {
            title: name.clone(),
            artists: join_artists(entity.get("artists").and_then(Value::as_array)),
            isrc: None,
            duration_ms: entity.get("duration").and_then(Value::as_i64),
            is_explicit: entity
                .get("isExplicit")
                .and_then(Value::as_bool)
                .unwrap_or(false),
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

// --- Apple Music (iTunes Lookup API + playlist page scrape) ----------------

fn apple_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"(?i)^(?:https?://)?(?:[\w-]+\.)*music\.apple\.com/(?:([a-z]{2})/)?(album|song|playlist)/[^/]+/(pl\.[\w-]+|\d+)",
        )
        .unwrap()
    })
}

fn apple_track_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"[?&]i=(\d+)").unwrap())
}

fn curly_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"\{[^}]*\}").unwrap())
}

fn serialized_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r#"(?s)<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>"#).unwrap()
    })
}

fn meta_content(html: &str, property: &str) -> Option<String> {
    let re = Regex::new(&format!(r#"<meta property="{property}" content="([^"]+)""#)).ok()?;
    re.captures(html).map(|c| unescape_html(&c[1]))
}

fn unescape_html(s: &str) -> String {
    s.replace("&amp;", "&")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&#x27;", "'")
        .replace("&#x2F;", "/")
        .replace("&#x3C;", "<")
        .replace("&#x3E;", ">")
        .replace("&#x26;", "&")
        .replace("&#34;", "\"")
        .replace("&apos;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
}

fn single(source: &str, kind: &str, track: MusicTrack) -> MusicImportInfo {
    MusicImportInfo {
        source: source.into(),
        kind: kind.into(),
        name: track.title.clone(),
        subtitle: Some(track.artists.clone()),
        cover_url: track.cover_url.clone(),
        tracks: vec![track],
        truncated: false,
    }
}

fn apple_track(item: &Value, album_name: Option<&str>) -> Option<MusicTrack> {
    let title = item
        .get("trackName")
        .and_then(Value::as_str)
        .filter(|t| !t.is_empty())?;
    let art = item
        .get("artworkUrl100")
        .and_then(Value::as_str)
        .map(|a| a.replace("100x100bb", "600x600bb"))
        .filter(|a| !a.is_empty());
    let date = item
        .get("releaseDate")
        .and_then(Value::as_str)
        .unwrap_or("");
    Some(MusicTrack {
        title: title.to_string(),
        artists: s(item, "artistName").unwrap_or_default(),
        isrc: None,
        duration_ms: item.get("trackTimeMillis").and_then(Value::as_i64),
        is_explicit: item.get("trackExplicitness").and_then(Value::as_str) == Some("explicit"),
        album: album_name
            .map(str::to_string)
            .or_else(|| s(item, "collectionName")),
        year: (date.len() >= 4).then(|| date[..4].to_string()),
        cover_url: art,
        source_url: s(item, "trackViewUrl").unwrap_or_default(),
    })
}

fn apple_art_url(artwork: &Value, size: i32) -> Option<String> {
    let dict = artwork
        .get("dictionary")
        .filter(|d| d.is_object())
        .unwrap_or(artwork);
    let url = dict.get("url").and_then(Value::as_str)?;
    let url = url
        .replace("{w}", &size.to_string())
        .replace("{h}", &size.to_string())
        .replace("{c}", "bb")
        .replace("{f}", "jpg");
    Some(curly_re().replace_all(&url, "").to_string())
}

fn walk_apple(node: &Value, out: &mut Vec<Value>) {
    match node {
        Value::Object(m) => {
            let dur_int = node
                .get("duration")
                .is_some_and(|d| d.is_i64() || d.is_u64());
            if m.contains_key("artistName") && m.contains_key("title") && dur_int {
                out.push(node.clone());
            }
            for v in m.values() {
                walk_apple(v, out);
            }
        }
        Value::Array(a) => {
            for v in a {
                walk_apple(v, out);
            }
        }
        _ => {}
    }
}

async fn resolve_apple_playlist(url: &str) -> Result<MusicImportInfo, String> {
    let html = get_text(url).await?;
    let blob = serialized_re()
        .captures(&html)
        .ok_or_else(|| "Could not read the Apple Music playlist page.".to_string())?;
    let data: Value = serde_json::from_str(&blob[1])
        .map_err(|_| "Could not parse the Apple Music playlist data.".to_string())?;
    let mut songs: Vec<Value> = Vec::new();
    walk_apple(&data, &mut songs);
    if songs.is_empty() {
        return Err("The Apple Music playlist exposed no tracks.".into());
    }
    let tracks: Vec<MusicTrack> = songs
        .iter()
        .map(|song| MusicTrack {
            title: s(song, "title").unwrap_or_default().trim().to_string(),
            artists: s(song, "artistName").unwrap_or_default().trim().to_string(),
            isrc: None,
            duration_ms: song.get("duration").and_then(Value::as_i64),
            is_explicit: song
                .get("showExplicitBadge")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            album: None,
            year: None,
            cover_url: song.get("artwork").and_then(|a| apple_art_url(a, 600)),
            source_url: song
                .get("contentDescriptor")
                .and_then(|c| s(c, "url"))
                .unwrap_or_default(),
        })
        .collect();
    let raw_name = meta_content(&html, "og:title").unwrap_or_else(|| "Apple Music".into());
    let name = Regex::new(r"(?i)\s+(?:en|on)\s+Apple Music$")
        .map(|re| re.replace(&raw_name, "").trim().to_string())
        .unwrap_or(raw_name);
    let cover = meta_content(&html, "og:image")
        .or_else(|| tracks.first().and_then(|t| t.cover_url.clone()));
    Ok(MusicImportInfo {
        source: "apple".into(),
        kind: "playlist".into(),
        name,
        subtitle: None,
        cover_url: cover,
        tracks,
        truncated: false,
    })
}

pub async fn resolve_apple(url: &str) -> Result<MusicImportInfo, String> {
    let caps = apple_re()
        .captures(url)
        .ok_or_else(|| "Not a recognised Apple Music URL.".to_string())?;
    let country = caps
        .get(1)
        .map(|m| m.as_str().to_lowercase())
        .unwrap_or_else(|| "us".into());
    let kind = caps[2].to_lowercase();
    let apple_id = caps[3].to_string();

    if kind == "playlist" {
        return resolve_apple_playlist(url).await;
    }

    let find_track = |results: &[Value]| {
        results
            .iter()
            .find(|r| r.get("wrapperType").and_then(Value::as_str) == Some("track"))
            .cloned()
    };

    // A single track inside an album URL (?i=trackId).
    if let Some(tm) = apple_track_re().captures(url) {
        let data = get_json(&format!(
            "https://itunes.apple.com/lookup?id={}&country={country}",
            &tm[1]
        ))
        .await?;
        let results = data
            .get("results")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        let track = find_track(&results)
            .and_then(|i| apple_track(&i, None))
            .ok_or_else(|| "Apple Music returned no track.".to_string())?;
        return Ok(single("apple", "track", track));
    }

    let data = get_json(&format!(
        "https://itunes.apple.com/lookup?id={apple_id}&country={country}&entity=song"
    ))
    .await?;
    let results = data
        .get("results")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let collection = results
        .iter()
        .find(|r| r.get("wrapperType").and_then(Value::as_str) == Some("collection"))
        .cloned();
    let Some(coll) = collection else {
        let track = find_track(&results)
            .and_then(|sgi| apple_track(&sgi, None))
            .ok_or_else(|| "Apple Music returned no track.".to_string())?;
        return Ok(single("apple", "track", track));
    };
    let name = s(&coll, "collectionName").unwrap_or_default();
    let subtitle = s(&coll, "artistName");
    let cover = s(&coll, "artworkUrl100")
        .map(|a| a.replace("100x100bb", "600x600bb"))
        .filter(|a| !a.is_empty());
    let tracks: Vec<MusicTrack> = results
        .iter()
        .filter(|r| r.get("wrapperType").and_then(Value::as_str) == Some("track"))
        .filter_map(|sg| apple_track(sg, Some(&name)))
        .collect();
    Ok(MusicImportInfo {
        source: "apple".into(),
        kind: "album".into(),
        name,
        subtitle,
        cover_url: cover,
        tracks,
        truncated: false,
    })
}

// --- Tidal (public embed scrape) -------------------------------------------

fn tidal_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"(?i)^(?:https?://)?(?:tidal\.com|embed\.tidal\.com|listen\.tidal\.com)/(?:browse/)?(track|album|playlist)s?/([\w-]+)",
        )
        .unwrap()
    })
}

fn tidal_item_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?s)<list-item\b.*?</list-item>").unwrap())
}

fn tidal_slot_re(slot: &str) -> Regex {
    Regex::new(&format!(
        r#"(?s)<(?:span|time) slot="{slot}"[^>]*>(.*?)</(?:span|time)>"#
    ))
    .unwrap()
}

fn strip_tags(s: &str) -> String {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| Regex::new(r"<[^>]+>").unwrap());
    re.replace_all(s, "").to_string()
}

fn tidal_join_artists(fragment: &str) -> String {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| Regex::new(r"<[^>]+>").unwrap());
    let mut names: Vec<String> = Vec::new();
    for part in re.split(fragment) {
        let p = unescape_html(part.trim());
        if !p.is_empty() && p != "," && p != "&" && p != "/" && !names.contains(&p) {
            names.push(p);
        }
    }
    names.join(", ")
}

fn mmss_to_ms(t: &str) -> Option<i64> {
    let parts: Vec<&str> = t.trim().split(':').collect();
    let nums: Vec<i64> = parts
        .iter()
        .filter_map(|p| p.trim().parse::<i64>().ok())
        .collect();
    if nums.len() != parts.len() || nums.is_empty() {
        return None;
    }
    Some(nums.iter().fold(0i64, |acc, n| acc * 60 + n) * 1000)
}

pub async fn resolve_tidal(url: &str) -> Result<MusicImportInfo, String> {
    let caps = tidal_re()
        .captures(url)
        .ok_or_else(|| "Not a recognised Tidal URL.".to_string())?;
    let kind = caps[1].to_lowercase();
    let tid = caps[2].to_string();
    let html = get_text(&format!(
        "https://embed.tidal.com/{kind}s/{tid}?countryCode=US"
    ))
    .await?;
    let page = get_text(&format!("https://tidal.com/{kind}/{tid}"))
        .await
        .unwrap_or_default();

    let (mut og_artist, mut og_name) = (None, None);
    if let Some(text) = meta_content(&page, "og:title") {
        if let Some((a, n)) = text.split_once(" - ") {
            og_artist = Some(a.trim().to_string());
            og_name = Some(n.trim().to_string());
        } else {
            og_name = Some(text.trim().to_string());
        }
    }
    let cover = meta_content(&page, "og:image");

    let title_re = tidal_slot_re("title");
    let artist_re = tidal_slot_re("artist");
    let duration_re = tidal_slot_re("duration");
    let pid_re = Regex::new(r#"product-id="(\d+)""#).unwrap();

    let mut tracks: Vec<MusicTrack> = Vec::new();
    for block in tidal_item_re().find_iter(&html).map(|m| m.as_str()) {
        let Some(tm) = title_re.captures(block) else {
            continue;
        };
        let title = unescape_html(&strip_tags(&tm[1])).trim().to_string();
        if title.is_empty() {
            continue;
        }
        let artist = artist_re
            .captures(block)
            .map(|am| tidal_join_artists(&am[1]))
            .unwrap_or_default();
        let dur_ms = duration_re
            .captures(block)
            .and_then(|dm| mmss_to_ms(&strip_tags(&dm[1])));
        let pid = pid_re.captures(block).map(|m| m[1].to_string());
        tracks.push(MusicTrack {
            title,
            artists: if artist.is_empty() {
                og_artist.clone().unwrap_or_default()
            } else {
                artist
            },
            isrc: None,
            duration_ms: dur_ms,
            is_explicit: block.contains(r#"slot="explicit-badge"><i class="badge explicit""#),
            album: if kind == "album" {
                og_name.clone()
            } else {
                None
            },
            year: None,
            cover_url: if kind == "album" { cover.clone() } else { None },
            source_url: pid
                .map(|p| format!("https://tidal.com/track/{p}"))
                .unwrap_or_default(),
        });
    }

    // A single-track URL has no list-items — build it from the page's og tags.
    if kind == "track" && tracks.is_empty() {
        if let Some(name) = og_name.clone() {
            tracks.push(MusicTrack {
                title: name,
                artists: og_artist.clone().unwrap_or_default(),
                isrc: None,
                duration_ms: None,
                is_explicit: false,
                album: None,
                year: None,
                cover_url: cover.clone(),
                source_url: format!("https://tidal.com/track/{tid}"),
            });
        }
    }

    if tracks.is_empty() {
        return Err("Could not read the Tidal tracklist.".into());
    }
    // TODO(slice-music): _deezer_enrich_each for a playlist's per-track covers.
    if kind == "track" {
        tracks.truncate(1);
        let t = &tracks[0];
        return Ok(MusicImportInfo {
            source: "tidal".into(),
            kind: "track".into(),
            name: t.title.clone(),
            subtitle: Some(t.artists.clone()),
            cover_url: cover,
            tracks,
            truncated: false,
        });
    }
    let subtitle = if kind == "album" { og_artist } else { None };
    Ok(MusicImportInfo {
        source: "tidal".into(),
        kind,
        name: og_name.unwrap_or_else(|| "Tidal".into()),
        subtitle,
        cover_url: cover,
        tracks,
        truncated: false,
    })
}

// --- lazy per-track metadata (cover + duration via Deezer) -----------------

async fn get_json_query(base: &str, params: &[(&str, &str)]) -> Result<Value, String> {
    client()
        .get(base)
        .query(params)
        .send()
        .await
        .map_err(|e| e.to_string())?
        .json::<Value>()
        .await
        .map_err(|e| e.to_string())
}

// Deezer's keyless API rate-limits bursts (~50 req / 5 s) with a "Quota limit
// exceeded" error (code 4). Pace every call through a shared gate (~8/s, safely
// under the limit) plus one backoff retry, so a big enrichment burst never trips
// it and silently drops covers. Mirrors _deezer_search's throttle.
const DEEZER_MIN_INTERVAL: std::time::Duration = std::time::Duration::from_millis(120);

/// Reserve the next Deezer slot; returns how long to wait before firing.
fn deezer_gate() -> std::time::Duration {
    static GATE: OnceLock<std::sync::Mutex<std::time::Instant>> = OnceLock::new();
    let gate = GATE.get_or_init(|| std::sync::Mutex::new(std::time::Instant::now()));
    let mut next = gate.lock().unwrap();
    let now = std::time::Instant::now();
    let wait = next.saturating_duration_since(now);
    *next = now.max(*next) + DEEZER_MIN_INTERVAL;
    wait
}

/// Run a Deezer request through the paced gate, retrying once on a quota error.
async fn deezer_retry<F, Fut>(mut make: F) -> Option<Value>
where
    F: FnMut() -> Fut,
    Fut: std::future::Future<Output = Result<Value, String>>,
{
    for attempt in 0..2u32 {
        let wait = deezer_gate();
        if !wait.is_zero() {
            tokio::time::sleep(wait).await;
        }
        let v = make().await.ok();
        if let Some(ref j) = v {
            if j.get("error")
                .and_then(|e| e.get("code"))
                .and_then(Value::as_i64)
                == Some(4)
            {
                tokio::time::sleep(std::time::Duration::from_millis(
                    1500 * (attempt as u64 + 1),
                ))
                .await;
                continue; // quota exceeded — back off, retry once
            }
        }
        return v;
    }
    None
}

async fn deezer_query(base: &str, params: &[(&str, &str)]) -> Option<Value> {
    deezer_retry(|| get_json_query(base, params)).await
}

async fn deezer_get(url: &str) -> Option<Value> {
    deezer_retry(|| get_json(url)).await
}

/// One keyless Deezer lookup for a track -> (cover_url, duration_ms). Best-effort:
/// (None, None) on any miss. Mirrors _deezer_track_meta in music_import.py.
pub async fn track_meta(title: &str, artists: &str) -> (Option<String>, Option<i64>) {
    if title.is_empty() {
        return (None, None);
    }
    let queries = [
        format!("artist:\"{artists}\" track:\"{title}\""),
        format!("{artists} {title}").trim().to_string(),
    ];
    for q in queries {
        if q.is_empty() {
            continue;
        }
        let Some(data) = deezer_query(
            "https://api.deezer.com/search",
            &[("limit", "1"), ("q", &q)],
        )
        .await
        else {
            continue;
        };
        if let Some(first) = data
            .get("data")
            .and_then(Value::as_array)
            .and_then(|a| a.first())
        {
            let cover = first
                .get("album")
                .and_then(|a| s(a, "cover_xl").or_else(|| s(a, "cover_big")))
                .or_else(|| s(first, "cover_xl"));
            let duration = first
                .get("duration")
                .and_then(Value::as_i64)
                .map(|d| d * 1000);
            if cover.is_some() || duration.is_some() {
                return (cover, duration);
            }
        }
    }
    (None, None)
}

// --- Amazon Music (public embed scrape) ------------------------------------

const AMZ_BROWSER_UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 \
     (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

fn amazon_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"^(?:https?://)?music\.amazon\.[a-z]{2,3}(?:\.[a-z]{2})?/(albums|tracks|playlists|user-playlists)/([A-Z0-9.]+)",
        )
        .unwrap()
    })
}

async fn get_text_browser(url: &str) -> Result<String, String> {
    reqwest::Client::builder()
        .user_agent(AMZ_BROWSER_UA)
        .build()
        .unwrap_or_default()
        .get(url)
        .send()
        .await
        .map_err(|e| e.to_string())?
        .text()
        .await
        .map_err(|e| e.to_string())
}

/// Strip Amazon's size token (e.g. `._SY240_`) to get the original image.
fn amz_full_size(url: &str) -> String {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"\._[^./]+_\.").unwrap())
        .replace(url, ".")
        .into_owned()
}

/// Loosely normalise a track title for cross-service matching (mirrors _norm_title).
fn amz_norm_title(title: &str) -> String {
    static EXPL: OnceLock<Regex> = OnceLock::new();
    static PAREN: OnceLock<Regex> = OnceLock::new();
    static PUNCT: OnceLock<Regex> = OnceLock::new();
    static WS: OnceLock<Regex> = OnceLock::new();
    let expl = EXPL.get_or_init(|| Regex::new(r"(?i)\s*\[explicit\]\s*").unwrap());
    let paren = PAREN.get_or_init(|| Regex::new(r"\s*\([^)]*\)\s*").unwrap());
    let punct = PUNCT.get_or_init(|| Regex::new(r"[^\w\s]").unwrap());
    let ws = WS.get_or_init(|| Regex::new(r"\s+").unwrap());
    let t = title.to_lowercase();
    let t = expl.replace_all(&t, " ");
    let t = paren.replace_all(&t, " ");
    let t = punct.replace_all(&t, "");
    ws.replace_all(&t, " ").trim().to_string()
}

/// Amazon's embed carries neither cover art nor durations, so look the album up
/// on Deezer's keyless API and fill them in (mirrors _deezer_enrich). Mutates
/// `tracks`; returns the album cover. Best-effort no-op on any miss.
async fn deezer_enrich(name: &str, artist: &str, tracks: &mut [MusicTrack]) -> Option<String> {
    if name.is_empty() {
        return None;
    }
    let queries = [
        format!("artist:\"{artist}\" album:\"{name}\""),
        format!("{artist} {name}").trim().to_string(),
    ];
    let mut aid: Option<i64> = None;
    for q in queries {
        if let Some(found) = deezer_query(
            "https://api.deezer.com/search/album",
            &[("limit", "1"), ("q", &q)],
        )
        .await
        {
            if let Some(first) = found
                .get("data")
                .and_then(Value::as_array)
                .and_then(|a| a.first())
            {
                aid = first.get("id").and_then(Value::as_i64);
                break;
            }
        }
    }
    let aid = aid?;
    let album = deezer_get(&format!("https://api.deezer.com/album/{aid}")).await?;
    let cover = s(&album, "cover_xl").or_else(|| s(&album, "cover_big"));
    let mut durations: std::collections::HashMap<String, i64> = std::collections::HashMap::new();
    if let Some(arr) = album
        .get("tracks")
        .and_then(|t| t.get("data"))
        .and_then(Value::as_array)
    {
        for entry in arr {
            let key = amz_norm_title(entry.get("title").and_then(Value::as_str).unwrap_or(""));
            if !key.is_empty() && !durations.contains_key(&key) {
                if let Some(d) = entry.get("duration").and_then(Value::as_i64) {
                    durations.insert(key, d * 1000);
                }
            }
        }
    }
    for track in tracks.iter_mut() {
        if track.duration_ms.is_none() {
            track.duration_ms = durations.get(&amz_norm_title(&track.title)).copied();
        }
        if let Some(c) = &cover {
            if track.cover_url.is_none() {
                track.cover_url = Some(c.clone());
            }
        }
    }
    cover
}

/// Resolve an Amazon Music album/track/playlist embed (keyless scrape + Deezer
/// enrichment). Mirrors _resolve_amazon in music_import.py.
pub async fn resolve_amazon(url: &str) -> Result<MusicImportInfo, String> {
    let caps = amazon_re()
        .captures(url)
        .ok_or_else(|| "Not a recognised Amazon Music URL.".to_string())?;
    let kind_path = caps[1].to_lowercase();
    let asin = caps[2].to_string();
    let kind = if kind_path == "tracks" {
        "track"
    } else if kind_path.contains("playlist") {
        "playlist"
    } else {
        "album"
    };
    let tld = Regex::new(r"music\.amazon\.([a-z]{2,3}(?:\.[a-z]{2})?)/")
        .ok()
        .and_then(|re| re.captures(url).map(|c| c[1].to_string()))
        .unwrap_or_else(|| "com".to_string());

    let raw = get_text_browser(&format!("https://music.amazon.{tld}/embed/{asin}")).await?;
    // Collapse inter-tag whitespace so titles/artists sit flush after their tags.
    static WS: OnceLock<Regex> = OnceLock::new();
    let html = WS
        .get_or_init(|| Regex::new(r">\s+<").unwrap())
        .replace_all(&raw, "><")
        .into_owned();

    static TITLE_TAG: OnceLock<Regex> = OnceLock::new();
    static HEADER_IMG: OnceLock<Regex> = OnceLock::new();
    static ORIGINAL: OnceLock<Regex> = OnceLock::new();
    static EXPL_SUFFIX: OnceLock<Regex> = OnceLock::new();
    let title_tag = TITLE_TAG.get_or_init(|| Regex::new(r"(?s)<title>(.*?)</title>").unwrap());
    let header_img = HEADER_IMG
        .get_or_init(|| Regex::new(r#"headerImg[^>]*><img[^>]*\bsrc="([^"]+)""#).unwrap());
    let original =
        ORIGINAL.get_or_init(|| Regex::new(r"(?i)amazon\s+(?:music\s+)?original").unwrap());
    let expl_suffix = EXPL_SUFFIX.get_or_init(|| Regex::new(r"\s*\[Explicit\]\s*$").unwrap());

    let header_cover = header_img
        .captures(&html)
        .map(|c| amz_full_size(&unescape_html(&c[1])));

    if kind == "track" {
        static TRACK_PREFIX: OnceLock<Regex> = OnceLock::new();
        static TRACK_ARTIST: OnceLock<Regex> = OnceLock::new();
        let prefix = TRACK_PREFIX.get_or_init(|| {
            Regex::new(
                r"(?s)^Amazon Music\s*[-\x{2013}]\s*(?:Pista|Canci\u{00f3}n|Cancion|Song|Track)\s*",
            )
            .unwrap()
        });
        let track_artist = TRACK_ARTIST.get_or_init(|| {
            Regex::new(r#"(?s)class="trackArtist[^"]*"[^>]*>(?:<a[^>]*>)?([^<]+)"#).unwrap()
        });
        let raw_title = title_tag
            .captures(&html)
            .map(|c| unescape_html(&c[1]))
            .unwrap_or_default();
        let name = prefix.replace(&raw_title, "").to_string();
        let name = expl_suffix.replace(name.trim(), "").trim().to_string();
        if name.is_empty() {
            return Err("Could not read the Amazon Music track.".to_string());
        }
        let artist = track_artist
            .captures(&html)
            .map(|c| unescape_html(c[1].trim()))
            .unwrap_or_default();
        let is_original = original.is_match(&name);
        let mut tracks = vec![MusicTrack {
            title: name.clone(),
            artists: artist.clone(),
            isrc: None,
            duration_ms: None,
            is_explicit: raw_title.contains("[Explicit]"),
            album: None,
            year: None,
            cover_url: if is_original {
                header_cover.clone()
            } else {
                None
            },
            source_url: format!("https://music.amazon.{tld}/tracks/{asin}"),
        }];
        deezer_enrich(&name, &artist, &mut tracks).await;
        if tracks[0].cover_url.is_none() {
            tracks[0].cover_url = header_cover.clone();
        }
        let cover = header_cover.or_else(|| tracks[0].cover_url.clone());
        return Ok(MusicImportInfo {
            source: "amazon".into(),
            kind: "track".into(),
            name,
            subtitle: Some(artist),
            cover_url: cover,
            tracks,
            truncated: false,
        });
    }

    // album / playlist
    static SET_PREFIX: OnceLock<Regex> = OnceLock::new();
    static ITEM: OnceLock<Regex> = OnceLock::new();
    static LIST_TITLE: OnceLock<Regex> = OnceLock::new();
    static LIST_ARTIST: OnceLock<Regex> = OnceLock::new();
    static ASIN_RE: OnceLock<Regex> = OnceLock::new();
    static TRACK_IMG: OnceLock<Regex> = OnceLock::new();
    let set_prefix = SET_PREFIX.get_or_init(|| {
        Regex::new(r"(?s)^Amazon Music\s*[-\x{2013}]\s*(?:\u{00c1}lbum|Album|Playlist|Lista)\s*")
            .unwrap()
    });
    let item = ITEM.get_or_init(|| Regex::new(r#"(?s)<li class="trackItem.*?</li>"#).unwrap());
    let list_title = LIST_TITLE.get_or_init(|| {
        Regex::new(r#"(?s)class="trackListTitle[^"]*"[^>]*>(?:<a[^>]*>)?([^<]+)"#).unwrap()
    });
    let list_artist = LIST_ARTIST.get_or_init(|| {
        Regex::new(r#"(?s)class="trackListArtist[^"]*"[^>]*>(?:<a[^>]*>)?([^<]+)"#).unwrap()
    });
    let asin_re = ASIN_RE.get_or_init(|| Regex::new(r#"data-asin="([A-Z0-9]+)""#).unwrap());
    let track_img = TRACK_IMG.get_or_init(|| {
        Regex::new(r#"imageBackground[^>]*background-image:\s*url\(['"]?([^'")]+)"#).unwrap()
    });

    let set_name = title_tag
        .captures(&html)
        .map(|c| {
            let n = unescape_html(&c[1]);
            let n = set_prefix.replace(&n, "").to_string();
            expl_suffix.replace(n.trim(), "").trim().to_string()
        })
        .unwrap_or_default();

    let mut tracks: Vec<MusicTrack> = Vec::new();
    let mut amazon_covers: Vec<Option<String>> = Vec::new();
    for block in item.find_iter(&html).map(|m| m.as_str()) {
        let Some(tm) = list_title.captures(block) else {
            continue;
        };
        let raw_t = tm[1].to_string();
        let title = expl_suffix
            .replace(unescape_html(tm[1].trim()).trim(), "")
            .trim()
            .to_string();
        let artist = list_artist
            .captures(block)
            .map(|c| unescape_html(c[1].trim()))
            .unwrap_or_default();
        let asin_m = asin_re.captures(block).map(|c| c[1].to_string());
        let amazon_cover = track_img
            .captures(block)
            .map(|c| amz_full_size(&unescape_html(&c[1])))
            .or_else(|| header_cover.clone());
        amazon_covers.push(amazon_cover.clone());
        let is_original = original.is_match(&title);
        tracks.push(MusicTrack {
            title,
            artists: artist,
            isrc: None,
            duration_ms: None,
            is_explicit: raw_t.contains("[Explicit]"),
            album: if kind == "album" {
                Some(set_name.clone())
            } else {
                None
            },
            year: None,
            cover_url: if is_original { amazon_cover } else { None },
            source_url: asin_m
                .map(|a| format!("https://music.amazon.{tld}/tracks/{a}"))
                .unwrap_or_default(),
        });
    }

    if tracks.is_empty() {
        return Err("Could not read the Amazon Music tracklist.".to_string());
    }

    if kind == "album" {
        let artist0 = tracks[0].artists.clone();
        deezer_enrich(&set_name, &artist0, &mut tracks).await;
    } else {
        // Playlist: enrich each track's missing cover/duration on its own, run
        // concurrently (each lookup still funnels through the paced Deezer gate,
        // so the burst stays under the quota while overlapping network latency).
        let mut set = tokio::task::JoinSet::new();
        for (i, track) in tracks.iter().enumerate() {
            if track.cover_url.is_some() && track.duration_ms.is_some() {
                continue;
            }
            let (title, artists) = (track.title.clone(), track.artists.clone());
            set.spawn(async move { (i, track_meta(&title, &artists).await) });
        }
        while let Some(res) = set.join_next().await {
            if let Ok((i, (cover, dur))) = res {
                if tracks[i].cover_url.is_none() {
                    tracks[i].cover_url = cover;
                }
                if tracks[i].duration_ms.is_none() {
                    tracks[i].duration_ms = dur;
                }
            }
        }
    }

    // Backfill covers Deezer couldn't find (Amazon-exclusive) from Amazon.
    for (track, amazon_cover) in tracks.iter_mut().zip(amazon_covers) {
        if track.cover_url.is_none() {
            if let Some(c) = amazon_cover {
                track.cover_url = Some(c);
            }
        }
    }

    let cover = header_cover.or_else(|| tracks.iter().find_map(|t| t.cover_url.clone()));
    let subtitle = if kind == "album" {
        Some(tracks[0].artists.clone())
    } else {
        None
    };
    Ok(MusicImportInfo {
        source: "amazon".into(),
        kind: kind.into(),
        name: if set_name.is_empty() {
            "Amazon Music".into()
        } else {
            set_name
        },
        subtitle,
        cover_url: cover,
        tracks,
        truncated: false,
    })
}

// --- ISRC resolution (keyless Deezer) for the YouTube-Music exact match --------

const DURATION_TOLERANCE_MS: i64 = 3000;

fn primary_artist(artists: &str) -> String {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE
        .get_or_init(|| Regex::new(r"(?i)\s*(?:,|&|/|\bfeat\.?\b|\bft\.?\b|\bcon\b)\s*").unwrap());
    re.split(artists)
        .next()
        .unwrap_or(artists)
        .trim()
        .to_string()
}

/// Resolve a recording's ISRC via a keyless Deezer lookup (for sources that don't
/// carry one). Gated on duration: accepted only when the hit is within 3 s (or no
/// duration is known). Mirrors _deezer_isrc. Best-effort.
pub async fn deezer_isrc(title: &str, artists: &str, duration_ms: Option<i64>) -> Option<String> {
    if title.is_empty() {
        return None;
    }
    let primary = primary_artist(artists);
    let mut queries = vec![
        format!("artist:\"{artists}\" track:\"{title}\""),
        format!("{artists} {title}").trim().to_string(),
    ];
    if !primary.is_empty() && primary != artists {
        queries.push(format!("artist:\"{primary}\" track:\"{title}\""));
    }
    let mut seen = std::collections::HashSet::new();
    for q in queries {
        if q.is_empty() || !seen.insert(q.clone()) {
            continue;
        }
        let Some(found) = deezer_query(
            "https://api.deezer.com/search/track",
            &[("limit", "1"), ("q", &q)],
        )
        .await
        else {
            continue;
        };
        let Some(hit) = found
            .get("data")
            .and_then(Value::as_array)
            .and_then(|a| a.first())
        else {
            continue;
        };
        let dur = hit.get("duration").and_then(Value::as_i64);
        if let (Some(d), Some(target)) = (dur, duration_ms) {
            if (d * 1000 - target).abs() > DURATION_TOLERANCE_MS {
                continue;
            }
        }
        let Some(tid) = hit.get("id").and_then(Value::as_i64) else {
            continue;
        };
        let Some(full) = deezer_get(&format!("https://api.deezer.com/track/{tid}")).await else {
            continue;
        };
        if let Some(isrc) = full
            .get("isrc")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
        {
            return Some(isrc.to_string());
        }
    }
    None
}
