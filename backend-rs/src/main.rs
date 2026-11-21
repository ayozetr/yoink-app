// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Yoink core (Rust) — first vertical slice of the Python-backend port.
//!
//! Serves the same local HTTP API the React UI already talks to (so the UI is
//! unchanged) but, instead of wrapping yt-dlp's Python library, it shells out to
//! the **yt-dlp binary** and maps its JSON to the existing contract. This slice
//! implements `GET /api/version` and `POST /api/info` (single video); playlists,
//! search, download (WS), history, settings, autotag and music import are the
//! next slices. yt-dlp stays the engine — we never reimplement it.

use std::net::SocketAddr;

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        Json,
    },
    http::{HeaderValue, Method, StatusCode},
    response::Response,
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::io::{AsyncBufReadExt, AsyncReadExt};
use tower_http::cors::CorsLayer;

mod audio_normalize;
mod autotag;
mod cli;
mod library;
mod matching;
mod music;
mod nfo;
mod vr;

const APP_VERSION: &str = env!("CARGO_PKG_VERSION");
// "Auto-tag name" filename templates (mirror core/config.py) — when one is the
// active template, auto-tagging renames the file to the tagged "Artist - Title".
const AUTOTAG_FILENAME_TEMPLATE: &str = "%(autotag)s";
const AUTOTAG_FILENAME_TEMPLATE_REVERSED: &str = "%(autotag_ta)s";

/// Lossless audio codecs — mirrors the Python `source_lossless` heuristic.
const LOSSLESS: &[&str] = &["flac", "alac", "wav", "pcm", "tta", "ape", "wavpack"];

// ---- contract (mirrors backend/app/models/media.py) --------------------------

#[derive(Deserialize)]
struct InfoRequest {
    url: String,
}

#[derive(Serialize)]
struct MediaFormat {
    format_id: String,
    ext: String,
    resolution: Option<String>,
    fps: Option<f64>,
    vcodec: Option<String>,
    acodec: Option<String>,
    filesize: Option<i64>,
    has_video: bool,
    has_audio: bool,
}

#[derive(Serialize)]
struct VideoInfo {
    id: String,
    title: String,
    duration: Option<f64>,
    duration_string: Option<String>,
    uploader: Option<String>,
    thumbnail_url: Option<String>,
    webpage_url: Option<String>,
    extractor: Option<String>,
    formats: Vec<MediaFormat>,
    source_lossless: bool,
    best_audio_abr: Option<f64>,
    has_audio: bool,
    subtitle_langs: Vec<String>,
    auto_caption_langs: Vec<String>,
    has_chapters: bool,
    is_hls: bool,
    audio_langs: Vec<String>,
    is_vr: bool,
    vr_layout: String,
    is_image: bool,
}

#[derive(Serialize)]
struct PlaylistEntry {
    id: String,
    title: String,
    url: String,
    duration_string: Option<String>,
    thumbnail_url: Option<String>,
    uploader: Option<String>,
    view_count: Option<i64>,
    already_downloaded: bool,
    playlist_index: Option<i64>,
    is_image: bool,
}

#[derive(Serialize)]
struct PlaylistInfo {
    id: String,
    title: String,
    uploader: Option<String>,
    thumbnail_url: Option<String>,
    entry_count: usize,
    entries: Vec<PlaylistEntry>,
    truncated: bool,
}

#[derive(Serialize)]
struct InfoResponse {
    #[serde(rename = "type")]
    kind: &'static str,
    video: Option<VideoInfo>,
    playlist: Option<PlaylistInfo>,
}

#[derive(Serialize)]
struct SearchResponse {
    results: Vec<PlaylistEntry>,
}

#[derive(Deserialize)]
struct SearchParams {
    q: String,
    #[serde(default)]
    source: Option<String>,
}

/// What the UI sends over the download WebSocket. Unknown fields (the advanced
/// options not handled by this slice — subs, chapters, trim, VR, HLS…) are
/// ignored for now; see DownloadRequest in backend/app/models/media.py.
#[derive(Clone, Deserialize)]
struct DownloadRequest {
    url: String,
    #[serde(default = "d_video")]
    kind: String,
    #[serde(default)]
    quality: Option<String>,
    #[serde(default = "d_mp4")]
    container: String,
    #[serde(default = "d_mp3")]
    audio_format: String,
    #[serde(default)]
    audio_bitrate: Option<String>,
    #[serde(default)]
    video_codec: Option<String>,
    #[serde(default)]
    embed_subs: bool,
    #[serde(default)]
    subtitle_lang: Option<String>,
    #[serde(default)]
    embed_chapters: bool,
    #[serde(default)]
    audio_multistreams: bool,
    #[serde(default)]
    trim_start: Option<f64>,
    #[serde(default)]
    trim_end: Option<f64>,
    #[serde(default)]
    is_hls: bool,
    #[serde(default)]
    is_vr: bool,
    #[serde(default)]
    vr_layout: Option<String>,
    #[serde(default)]
    auto_vr: bool,
}

fn d_video() -> String {
    "video".into()
}
fn d_mp4() -> String {
    "mp4".into()
}
fn d_mp3() -> String {
    "mp3".into()
}

#[derive(Serialize)]
struct VersionInfo {
    current: String,
    latest: Option<String>,
    update_available: bool,
    release_url: Option<String>,
    error: Option<String>,
}

// ---- helpers -----------------------------------------------------------------

fn ytdlp_bin() -> String {
    std::env::var("YOINK_YTDLP").unwrap_or_else(|_| "yt-dlp".to_string())
}

/// yt-dlp stderr markers that mark a likely-temporary failure (network blip,
/// 5xx/429, or an anti-bot 403) worth retrying — as opposed to a permanent
/// unsupported/private/deleted URL. Mirrors _TRANSIENT_MARKERS.
const TRANSIENT_MARKERS: &[&str] = &[
    "http error 500",
    "http error 502",
    "http error 503",
    "http error 504",
    "http error 429",
    "http error 403",
    "timed out",
    "timeout",
    "connection reset",
    "connection refused",
    "connection aborted",
    "remote end closed",
    "temporary failure",
    "sign in to confirm you're not a bot",
    "failed to extract any player response",
    "getaddrinfo failed",
];

fn is_transient(stderr: &str) -> bool {
    let low = stderr.to_lowercase();
    TRANSIENT_MARKERS.iter().any(|m| low.contains(m))
}

/// Cookie args for a yt-dlp call. `use_browser=false` drops the browser store
/// (the fallback), keeping a cookies file if one is configured.
fn cookie_args(settings: &AppSettings, use_browser: bool) -> Vec<String> {
    if use_browser {
        if let Some(b) = settings
            .cookies_from_browser
            .as_deref()
            .filter(|s| !s.is_empty())
        {
            return vec!["--cookies-from-browser".into(), b.into()];
        }
    }
    if let Some(f) = settings.cookies_file.as_deref().filter(|s| !s.is_empty()) {
        return vec!["--cookies".into(), f.into()];
    }
    vec![]
}

async fn ytdlp_once(base: &[&str], cookies: &[String]) -> Result<Vec<u8>, (bool, String)> {
    let mut cmd = tokio::process::Command::new(ytdlp_bin());
    cmd.args(base);
    cmd.args(cookies);
    match cmd.output().await {
        Ok(o) if o.status.success() => Ok(o.stdout),
        Ok(o) => {
            let err = String::from_utf8_lossy(&o.stderr).trim().to_string();
            Err((is_transient(&err), err))
        }
        Err(e) => Err((true, format!("could not run yt-dlp: {e}"))),
    }
}

/// Run a yt-dlp `-J` command with a transient-retry (up to 3 attempts, 0.6 s
/// backoff) and a browser-cookie fallback (retry once with the fragile browser
/// store dropped). Mirrors extract_info's retry + with_cookie_fallback. The Err
/// carries (transient, message) so a caller can map it to 503 vs 422.
async fn run_ytdlp_json(base: &[&str], settings: &AppSettings) -> Result<Vec<u8>, (bool, String)> {
    let primary = cookie_args(settings, true);
    let fallback = cookie_args(settings, false);
    let has_browser = settings
        .cookies_from_browser
        .as_deref()
        .is_some_and(|s| !s.is_empty());
    let mut last = (false, "yt-dlp failed".to_string());
    for attempt in 0..3 {
        match ytdlp_once(base, &primary).await {
            Ok(out) => return Ok(out),
            Err(e) => {
                last = e;
                // The browser cookie store is the most fragile part of a request
                // (locked DB, app-bound decryption, …) — retry once without it.
                if has_browser {
                    if let Ok(out) = ytdlp_once(base, &fallback).await {
                        return Ok(out);
                    }
                }
                if !last.0 {
                    break; // a permanent failure — don't keep retrying
                }
                if attempt < 2 {
                    tokio::time::sleep(std::time::Duration::from_millis(600)).await;
                }
            }
        }
    }
    Err(last)
}

fn s(v: &Value, key: &str) -> Option<String> {
    v.get(key).and_then(Value::as_str).map(str::to_string)
}

fn codec(v: &Value, key: &str) -> Option<String> {
    match v.get(key).and_then(Value::as_str) {
        Some("none") | None => None,
        Some(c) => Some(c.to_string()),
    }
}

/// Map one yt-dlp format object to the MediaFormat contract.
fn map_format(f: &Value) -> Option<MediaFormat> {
    let format_id = s(f, "format_id")?;
    let vcodec = codec(f, "vcodec");
    let acodec = codec(f, "acodec");
    let resolution = f
        .get("height")
        .and_then(Value::as_i64)
        .map(|h| format!("{h}p"))
        .or_else(|| s(f, "resolution"));
    let filesize = f
        .get("filesize")
        .and_then(Value::as_i64)
        .or_else(|| f.get("filesize_approx").and_then(Value::as_i64));
    Some(MediaFormat {
        ext: s(f, "ext").unwrap_or_else(|| "unknown".into()),
        resolution,
        fps: f.get("fps").and_then(Value::as_f64),
        has_video: vcodec.is_some(),
        has_audio: acodec.is_some(),
        vcodec,
        acodec,
        filesize,
        format_id,
    })
}

fn keys(v: &Value, key: &str) -> Vec<String> {
    v.get(key)
        .and_then(Value::as_object)
        .map(|m| m.keys().cloned().collect())
        .unwrap_or_default()
}

fn fmt_duration(secs: f64) -> String {
    let total = secs as i64;
    let (h, m, s) = (total / 3600, (total % 3600) / 60, total % 60);
    if h > 0 {
        format!("{h}:{m:02}:{s:02}")
    } else {
        format!("{m}:{s:02}")
    }
}

/// Best thumbnail URL for an item (flat entries carry a `thumbnails` array).
fn thumb_of(v: &Value) -> Option<String> {
    if let Some(t) = s(v, "thumbnail") {
        return Some(t);
    }
    v.get("thumbnails")
        .and_then(Value::as_array)
        .and_then(|a| a.last())
        .and_then(|t| s(t, "url"))
}

/// Map one flat playlist/search entry to the PlaylistEntry contract.
fn map_entry(e: &Value) -> PlaylistEntry {
    let duration_string = s(e, "duration_string")
        .or_else(|| e.get("duration").and_then(Value::as_f64).map(fmt_duration));
    PlaylistEntry {
        id: s(e, "id").unwrap_or_default(),
        title: s(e, "title").unwrap_or_else(|| "(untitled)".into()),
        url: s(e, "url")
            .or_else(|| s(e, "webpage_url"))
            .unwrap_or_default(),
        duration_string,
        thumbnail_url: thumb_of(e),
        uploader: s(e, "uploader").or_else(|| s(e, "channel")),
        view_count: e.get("view_count").and_then(Value::as_i64),
        // TODO(slice-history): matched against completed downloads for playlist sync.
        already_downloaded: false,
        playlist_index: None,
        is_image: false,
    }
}

fn map_entries(j: &Value) -> Vec<PlaylistEntry> {
    j.get("entries")
        .and_then(Value::as_array)
        .map(|es| es.iter().filter(|e| !e.is_null()).map(map_entry).collect())
        .unwrap_or_default()
}

/// Entries shown for a playlist. Mirrors `_ENTRY_CAP` in ytdlp_service.py: a big
/// listing (a whole channel, a YouTube mix) is capped and flagged `truncated`.
const ENTRY_CAP: usize = 200;

/// Build the flat PlaylistInfo from yt-dlp's `--flat-playlist` JSON — deduped by
/// id and capped, like ytdlp_service.py's `_build_playlist`.
fn map_playlist(j: &Value) -> PlaylistInfo {
    let raw: Vec<&Value> = j
        .get("entries")
        .and_then(Value::as_array)
        .map(|a| a.iter().filter(|e| e.is_object()).collect())
        .unwrap_or_default();
    let reported_total = j
        .get("playlist_count")
        .and_then(Value::as_u64)
        .map(|c| c as usize);

    // Dynamic mixes repeat the same id; dedupe (first wins, but swap in a later
    // copy if the kept one has no usable URL) so one pick is one download.
    let has_url = |e: &Value| e.get("url").is_some() || e.get("webpage_url").is_some();
    let mut seen: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    let mut unique: Vec<&Value> = Vec::new();
    for e in raw.iter().copied() {
        let id = s(e, "id").unwrap_or_default();
        if !id.is_empty() {
            if let Some(&idx) = seen.get(&id) {
                if !has_url(unique[idx]) && has_url(e) {
                    unique[idx] = e;
                }
                continue;
            }
            seen.insert(id, unique.len());
        }
        unique.push(e);
    }

    let unique_len = unique.len();
    let entries: Vec<PlaylistEntry> = unique.into_iter().take(ENTRY_CAP).map(map_entry).collect();
    let capped = unique_len > ENTRY_CAP;
    let fetched_all = reported_total.is_none_or(|t| raw.len() >= t);
    let truncated = capped || !fetched_all;
    let entry_count = if fetched_all && !capped {
        entries.len()
    } else {
        reported_total.unwrap_or(unique_len)
    };
    let thumbnail_url =
        thumb_of(j).or_else(|| entries.first().and_then(|e| e.thumbnail_url.clone()));
    PlaylistInfo {
        id: s(j, "id").unwrap_or_default(),
        title: s(j, "title").unwrap_or_else(|| "(untitled)".into()),
        uploader: s(j, "uploader").or_else(|| s(j, "channel")),
        thumbnail_url,
        entry_count,
        entries,
        truncated,
    }
}

/// Build the VideoInfo from yt-dlp's single-video JSON.
fn map_video(j: &Value) -> VideoInfo {
    let raw_formats = j.get("formats").and_then(Value::as_array);
    let formats: Vec<MediaFormat> = raw_formats
        .map(|fs| fs.iter().filter_map(map_format).collect())
        .unwrap_or_default();

    let has_audio = formats.iter().any(|f| f.has_audio);
    let best_audio_abr = raw_formats.and_then(|fs| {
        fs.iter()
            .filter(|f| codec(f, "acodec").is_some())
            .filter_map(|f| f.get("abr").and_then(Value::as_f64))
            .fold(None::<f64>, |acc, abr| {
                Some(acc.map_or(abr, |a| a.max(abr)))
            })
    });
    let source_lossless = raw_formats
        .map(|fs| {
            fs.iter().any(|f| {
                codec(f, "acodec")
                    .map(|c| LOSSLESS.iter().any(|l| c.to_lowercase().starts_with(l)))
                    .unwrap_or(false)
            })
        })
        .unwrap_or(false);
    let is_hls = raw_formats
        .map(|fs| {
            fs.iter().any(|f| {
                s(f, "protocol")
                    .map(|p| p.contains("m3u8"))
                    .unwrap_or(false)
            })
        })
        .unwrap_or(false);
    let mut audio_langs: Vec<String> = raw_formats
        .map(|fs| {
            fs.iter()
                .filter(|f| codec(f, "acodec").is_some())
                .filter_map(|f| s(f, "language"))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    audio_langs.sort();
    audio_langs.dedup();

    let subtitle_langs = keys(j, "subtitles");
    let auto_caption_langs: Vec<String> = keys(j, "automatic_captions")
        .into_iter()
        .filter(|l| !subtitle_langs.contains(l))
        .collect();
    let has_chapters = j
        .get("chapters")
        .and_then(Value::as_array)
        .map(|c| !c.is_empty())
        .unwrap_or(false);

    // VR heuristic (non-strict: the preview card lets the user confirm/override).
    let (is_vr, vr_layout) = vr::detect_vr(j, false);

    VideoInfo {
        id: s(j, "id").unwrap_or_default(),
        title: s(j, "title").unwrap_or_else(|| "(untitled)".into()),
        duration: j.get("duration").and_then(Value::as_f64),
        duration_string: s(j, "duration_string"),
        uploader: s(j, "uploader").or_else(|| s(j, "channel")),
        thumbnail_url: s(j, "thumbnail"),
        webpage_url: s(j, "webpage_url"),
        extractor: s(j, "extractor"),
        formats,
        source_lossless,
        best_audio_abr,
        has_audio,
        subtitle_langs,
        auto_caption_langs,
        has_chapters,
        is_hls,
        audio_langs,
        is_vr,
        vr_layout,
        is_image: false,
    }
}

// ---- handlers ----------------------------------------------------------------

async fn version() -> Json<VersionInfo> {
    Json(VersionInfo {
        current: APP_VERSION.to_string(),
        latest: None,
        update_available: false,
        release_url: None,
        error: None,
    })
}

/// Extract metadata for a URL (shared by the `/api/info` handler and the CLI).
/// `--flat-playlist` keeps a single video fully detailed while a playlist URL
/// returns a fast, flat listing. Err is `(transient, message)`.
async fn fetch_info_response(
    url: &str,
    settings: &AppSettings,
) -> Result<InfoResponse, (bool, String)> {
    let stdout = run_ytdlp_json(&["-J", "--flat-playlist", "--no-warnings", url], settings).await?;
    let j: Value =
        serde_json::from_slice(&stdout).map_err(|e| (false, format!("bad yt-dlp JSON: {e}")))?;
    if j.get("_type").and_then(Value::as_str) == Some("playlist") {
        Ok(InfoResponse {
            kind: "playlist",
            video: None,
            playlist: Some(map_playlist(&j)),
        })
    } else {
        Ok(InfoResponse {
            kind: "video",
            video: Some(map_video(&j)),
            playlist: None,
        })
    }
}

async fn info(Json(req): Json<InfoRequest>) -> Result<Json<InfoResponse>, (StatusCode, String)> {
    let settings = load_settings();
    fetch_info_response(&req.url, &settings)
        .await
        .map(Json)
        .map_err(|(transient, err)| {
            if transient {
                // 503 so the UI shows "temporary — try again", not "unsupported".
                (
                    StatusCode::SERVICE_UNAVAILABLE,
                    format!("temporarily unavailable (anti-bot/network): {err}"),
                )
            } else {
                (
                    StatusCode::UNPROCESSABLE_ENTITY,
                    format!("yt-dlp could not extract this URL: {err}"),
                )
            }
        })
}

async fn search(
    axum::extract::Query(p): axum::extract::Query<SearchParams>,
) -> Result<Json<SearchResponse>, (StatusCode, String)> {
    let prefix = match p.source.as_deref() {
        Some("soundcloud") => "scsearch",
        _ => "ytsearch",
    };
    let query = format!("{prefix}20:{}", p.q);
    let settings = load_settings();
    let stdout = run_ytdlp_json(
        &["-J", "--flat-playlist", "--no-warnings", &query],
        &settings,
    )
    .await
    .map_err(|(_t, err)| (StatusCode::BAD_GATEWAY, format!("search failed: {err}")))?;
    let j: Value = serde_json::from_slice(&stdout).map_err(|e| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("bad yt-dlp JSON: {e}"),
        )
    })?;
    Ok(Json(SearchResponse {
        results: map_entries(&j),
    }))
}

// ---- download (WebSocket) ----------------------------------------------------

const PROGRESS_TEMPLATE: &str = "download:YPROG|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s";

fn download_dir() -> std::path::PathBuf {
    if let Ok(d) = std::env::var("YOINK_DOWNLOAD_DIR") {
        return std::path::PathBuf::from(d);
    }
    // TODO(slice-settings): read the configured download directory.
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    std::path::Path::new(&home).join("Downloads").join("Yoink")
}

fn err_event(msg: &str) -> Message {
    Message::Text(serde_json::json!({ "type": "error", "message": msg }).to_string())
}

/// yt-dlp format-sort token for a preferred video codec ("any" = no preference).
fn vcodec_sort(codec: &str) -> Option<&'static str> {
    match codec {
        "h264" => Some("h264"),
        "h265" => Some("hevc"),
        "vp9" => Some("vp9"),
        "av1" => Some("av01"),
        _ => None,
    }
}

/// Build the yt-dlp argument list for a download, honouring the request and the
/// user's settings (cookies, proxy, rate limit, SponsorBlock, subs, chapters,
/// codec, trimming). HLS trimming, VR tagging and loudness normalization need a
/// post-ffmpeg pass and are later slices — see download_service.py.
fn download_args(req: &DownloadRequest, settings: &AppSettings, out_template: &str) -> Vec<String> {
    let mut a: Vec<String> = vec![
        "--newline".into(),
        "--progress".into(),
        "--no-warnings".into(),
        "--no-playlist".into(),
        "-o".into(),
        out_template.into(),
        "--progress-template".into(),
        PROGRESS_TEMPLATE.into(),
        "--print".into(),
        "after_move:YDONE|%(filepath)s".into(),
    ];
    // Write yt-dlp's info JSON alongside the file (removed after post-processing)
    // when it's needed: the download-time .nfo, or auto-VR detection.
    if settings.nfo_sidecars || req.auto_vr {
        a.push("--write-info-json".into());
    }
    // Bundled ffmpeg location (set by the Tauri shell), so merges/extraction work
    // without a system ffmpeg.
    if let Ok(dir) = std::env::var("YOINK_FFMPEG") {
        if !dir.is_empty() {
            a.push("--ffmpeg-location".into());
            a.push(dir);
        }
    }
    let nonempty = |o: &Option<String>| o.as_deref().filter(|s| !s.is_empty()).map(str::to_string);

    // Network options (from settings).
    if let Some(b) = nonempty(&settings.cookies_from_browser) {
        a.push("--cookies-from-browser".into());
        a.push(b);
    } else if let Some(f) = nonempty(&settings.cookies_file) {
        a.push("--cookies".into());
        a.push(f);
    }
    if let Some(p) = nonempty(&settings.proxy) {
        a.push("--proxy".into());
        a.push(p);
    }
    if let Some(r) = nonempty(&settings.rate_limit) {
        a.push("--limit-rate".into());
        a.push(r);
    }

    // SponsorBlock (reachability check is a later slice — see download_service.py).
    if settings.sponsorblock_enabled {
        let flag = if settings.sponsorblock_action == "mark" {
            "--sponsorblock-mark"
        } else {
            "--sponsorblock-remove"
        };
        a.push(flag.into());
        a.push("all".into());
    }

    // Clip a range (non-HLS; HLS needs a full fetch + ffmpeg clip, a later slice).
    if (req.trim_start.is_some() || req.trim_end.is_some()) && !req.is_hls {
        let start = req.trim_start.unwrap_or(0.0);
        let end = req
            .trim_end
            .map(|e| e.to_string())
            .unwrap_or_else(|| "inf".into());
        a.push("--download-sections".into());
        a.push(format!("*{start}-{end}"));
    }

    if req.kind == "audio" {
        a.push("-x".into());
        a.push("--audio-format".into());
        a.push(req.audio_format.clone());
        let bitrate = req
            .audio_bitrate
            .as_deref()
            .unwrap_or(&settings.audio_bitrate);
        let quality = if bitrate != "best" {
            format!("{bitrate}K")
        } else {
            "0".into()
        };
        a.push("--audio-quality".into());
        a.push(quality);
    } else {
        let format = match req.quality.as_deref() {
            Some(q) if q != "best" => {
                let h = q.trim_end_matches('p');
                format!("bv*[height<={h}]+ba/b")
            }
            _ => "bv*+ba/b".into(),
        };
        a.push("-f".into());
        a.push(format);
        a.push("--merge-output-format".into());
        a.push(req.container.clone());

        let codec = req.video_codec.as_deref().unwrap_or(&settings.video_codec);
        if let Some(sort) = vcodec_sort(codec) {
            a.push("-S".into());
            a.push(format!("vcodec:{sort}"));
        }
        if req.embed_subs {
            a.push("--embed-subs".into());
            a.push("--sub-langs".into());
            a.push(req.subtitle_lang.clone().unwrap_or_else(|| "all".into()));
        }
        if req.embed_chapters {
            a.push("--embed-chapters".into());
            a.push("--embed-metadata".into());
        }
        if req.audio_multistreams {
            a.push("--audio-multistreams".into());
        }
    }

    a.push(req.url.clone());
    a
}

/// Parse one `YPROG|…` line into a serialized ProgressEvent, or None to skip.
/// One parsed `YPROG|…` progress tick.
#[derive(Clone)]
pub struct ProgressInfo {
    pub percent: f64,
    pub speed: Option<String>,
    pub eta: Option<String>,
    pub downloaded: Option<i64>,
    pub total: Option<i64>,
}

fn parse_progress(rest: &str) -> Option<ProgressInfo> {
    let mut it = rest.split('|');
    let percent = it
        .next()?
        .trim()
        .trim_end_matches('%')
        .parse::<f64>()
        .ok()?;
    let opt = |s: Option<&str>| {
        let s = s.unwrap_or("").trim();
        (!s.is_empty() && s != "NA").then(|| s.to_string())
    };
    let num = |s: Option<&str>| s.unwrap_or("").trim().parse::<i64>().ok();
    let speed = opt(it.next());
    let eta = opt(it.next());
    let downloaded = num(it.next());
    let total = num(it.next());
    Some(ProgressInfo {
        percent,
        speed,
        eta,
        downloaded,
        total,
    })
}

impl ProgressInfo {
    fn to_ws_message(&self) -> Message {
        Message::Text(
            serde_json::json!({
                "type": "progress",
                "status": "downloading",
                "percent": self.percent,
                "downloaded_bytes": self.downloaded,
                "total_bytes": self.total,
                "speed": self.speed,
                "eta": self.eta,
                "filename": Value::Null,
            })
            .to_string(),
        )
    }
}

/// Lifecycle events emitted by `execute_download` to its event channel.
pub enum DlEvent {
    Progress(ProgressInfo),
    Completed {
        filename: String,
        filepath: String,
        total_bytes: Option<i64>,
    },
    Error(String),
}

async fn ws_download(ws: WebSocketUpgrade) -> Response {
    ws.on_upgrade(run_download)
}

async fn run_download(mut socket: WebSocket) {
    // The UI sends the DownloadRequest as the first message.
    let req: DownloadRequest = match socket.recv().await {
        Some(Ok(Message::Text(t))) => match serde_json::from_str(&t) {
            Ok(r) => r,
            Err(e) => {
                let _ = socket.send(err_event(&format!("bad request: {e}"))).await;
                return;
            }
        },
        _ => return,
    };
    let settings = load_settings();
    // Run the shared download core off-task and forward its events to the socket;
    // a send failure (client gone) flips `cancel`, which stops yt-dlp.
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<DlEvent>();
    let cancel = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    let (c2, tx2) = (cancel.clone(), tx);
    let handle = tokio::spawn(async move { execute_download(&req, &settings, &tx2, &c2).await });
    while let Some(ev) = rx.recv().await {
        let msg = match ev {
            DlEvent::Progress(p) => p.to_ws_message(),
            DlEvent::Completed {
                filename,
                filepath,
                total_bytes,
            } => Message::Text(
                serde_json::json!({
                    "type": "completed", "filename": filename,
                    "filepath": filepath, "total_bytes": total_bytes,
                })
                .to_string(),
            ),
            DlEvent::Error(m) => err_event(&m),
        };
        if socket.send(msg).await.is_err() {
            cancel.store(true, std::sync::atomic::Ordering::Relaxed);
            break;
        }
    }
    let _ = handle.await;
    let _ = socket.send(Message::Close(None)).await;
}

/// Run a download end to end: spawn yt-dlp, stream progress + the terminal
/// completed/error over `tx`, post-process (HLS trim, .nfo, loudnorm, VR) and
/// record history. `cancel` stops the download when the caller goes away. Shared
/// by the WebSocket handler and the CLI.
async fn execute_download(
    req: &DownloadRequest,
    settings: &AppSettings,
    tx: &tokio::sync::mpsc::UnboundedSender<DlEvent>,
    cancel: &std::sync::atomic::AtomicBool,
) {
    let dir = std::env::var("YOINK_DOWNLOAD_DIR")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from(&settings.download_dir));
    let _ = std::fs::create_dir_all(&dir);
    let template = format!("{}/{}.%(ext)s", dir.display(), settings.filename_template);
    let args = download_args(req, settings, &template);

    let mut child = match tokio::process::Command::new(ytdlp_bin())
        .args(&args)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
    {
        Ok(c) => c,
        Err(e) => {
            let _ = tx.send(DlEvent::Error(format!("could not run yt-dlp: {e}")));
            return;
        }
    };

    let stdout = child.stdout.take().expect("piped");
    let mut lines = tokio::io::BufReader::new(stdout).lines();
    let mut final_path: Option<String> = None;
    while let Ok(Some(line)) = lines.next_line().await {
        if let Some(rest) = line.strip_prefix("YPROG|") {
            if let Some(info) = parse_progress(rest) {
                if tx.send(DlEvent::Progress(info)).is_err()
                    || cancel.load(std::sync::atomic::Ordering::Relaxed)
                {
                    let _ = child.kill().await; // caller went away — stop downloading
                    return;
                }
            }
        } else if let Some(p) = line.strip_prefix("YDONE|") {
            final_path = Some(p.to_string());
        }
    }

    let status = child.wait().await;
    let ok = matches!(status, Ok(s) if s.success());

    // Post-processing on the finished file, in order: read the sidecar info.json
    // once (for the .nfo + auto-VR detection) then remove it; loudness-normalize
    // audio; VR-tag video (which renames the file, so this updates final_path).
    if ok {
        if let Some(path) = final_path.clone() {
            // HLS trim: the range download was skipped for an HLS source (it can't
            // be trimmed that way), so the full stream was fetched — clip it now.
            if req.is_hls && (req.trim_start.is_some() || req.trim_end.is_some()) {
                let start = req.trim_start.unwrap_or(0.0);
                let end = req.trim_end;
                let pp = path.clone();
                let _ = tokio::task::spawn_blocking(move || {
                    audio_normalize::ffmpeg_trim(&pp, start, end)
                })
                .await;
            }
            let info_json = std::path::Path::new(&path).with_extension("info.json");
            let info: Option<Value> = std::fs::read_to_string(&info_json)
                .ok()
                .and_then(|t| serde_json::from_str(&t).ok());
            // Download-time .nfo (audio gets rewritten later from the tagged data).
            if settings.nfo_sidecars {
                if let Some(ref i) = info {
                    let k = if req.kind == "audio" {
                        "audio"
                    } else {
                        "video"
                    };
                    nfo::write(std::path::Path::new(&path), &nfo::from_info(i, k));
                }
            }
            let _ = std::fs::remove_file(&info_json); // written only for these steps

            if req.kind == "audio" && settings.normalize_audio {
                let fmt = req.audio_format.clone();
                let bitrate = req.audio_bitrate.clone().unwrap_or_else(|| "best".into());
                let target = settings.normalize_lufs as f64;
                let pp = path.clone();
                let done = tokio::task::spawn_blocking(move || {
                    audio_normalize::normalize(&pp, &fmt, &bitrate, target)
                })
                .await
                .unwrap_or(false);
                if done {
                    log_line(&format!(
                        "normalized to {} LUFS: {path}",
                        settings.normalize_lufs
                    ));
                }
            } else if req.kind != "audio" {
                let layout_opt = if req.is_vr {
                    Some(
                        req.vr_layout
                            .clone()
                            .unwrap_or_else(|| vr::DEFAULT_LAYOUT.into()),
                    )
                } else if req.auto_vr {
                    info.as_ref().and_then(|i| {
                        let (is_vr, layout) = vr::detect_vr(i, true);
                        is_vr.then_some(layout)
                    })
                } else {
                    None
                };
                if let Some(layout) = layout_opt {
                    let pp = path.clone();
                    if let Ok(np) = tokio::task::spawn_blocking(move || {
                        vr::apply_vr(std::path::Path::new(&pp), &layout)
                    })
                    .await
                    {
                        final_path = Some(np.to_string_lossy().into_owned());
                        log_line(&format!(
                            "VR-tagged: {}",
                            final_path.as_deref().unwrap_or("")
                        ));
                    }
                }
            }
        }
    }

    // History `quality` column: resolution for video, format/bitrate for audio.
    let quality_label = if req.kind == "audio" {
        match req.audio_bitrate.as_deref() {
            Some(b) if b != "best" => format!("{} {b}kbps", req.audio_format),
            _ => req.audio_format.clone(),
        }
    } else {
        req.quality.clone().unwrap_or_else(|| "best".into())
    };

    if ok {
        match &final_path {
            Some(path) => {
                let total_bytes = std::fs::metadata(path).ok().map(|m| m.len() as i64);
                let p = std::path::Path::new(path);
                let filename = p
                    .file_name()
                    .and_then(|n| n.to_str())
                    .unwrap_or("")
                    .to_string();
                let title = p
                    .file_stem()
                    .and_then(|n| n.to_str())
                    .unwrap_or(&filename)
                    .to_string();
                record_download(
                    &title,
                    &req.url,
                    &req.kind,
                    "completed",
                    Some(&filename),
                    Some(path),
                    total_bytes,
                    Some(&quality_label),
                    None,
                );
                log_line(&format!("completed: {filename}"));
                let _ = tx.send(DlEvent::Completed {
                    filename,
                    filepath: path.clone(),
                    total_bytes,
                });
            }
            None => {
                let _ = tx.send(DlEvent::Error(
                    "download finished but no output file was reported".into(),
                ));
            }
        }
    } else {
        // stderr is small (--no-warnings); read it for the failure reason.
        let mut buf = String::new();
        if let Some(mut se) = child.stderr.take() {
            let _ = se.read_to_string(&mut buf).await;
        }
        let reason = buf.trim();
        let reason = if reason.is_empty() {
            "download failed".to_string()
        } else {
            reason.to_string()
        };
        record_download(
            &req.url,
            &req.url,
            &req.kind,
            "error",
            None,
            None,
            None,
            Some(&quality_label),
            Some(&reason),
        );
        log_line(&format!("error: {} ({reason})", req.url));
        let _ = tx.send(DlEvent::Error(reason));
    }
}

// ---- settings + history ------------------------------------------------------

fn data_dir() -> std::path::PathBuf {
    if let Ok(d) = std::env::var("YOINK_DATA_DIR") {
        return std::path::PathBuf::from(d);
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    std::path::Path::new(&home).join(".yoink")
}

fn humanize_bytes(n: i64) -> String {
    const UNITS: [&str; 5] = ["B", "KB", "MB", "GB", "TB"];
    let mut v = n as f64;
    let mut u = 0;
    while v >= 1024.0 && u < UNITS.len() - 1 {
        v /= 1024.0;
        u += 1;
    }
    if u == 0 {
        format!("{n} B")
    } else {
        format!("{v:.1} {}", UNITS[u])
    }
}

/// User settings (mirrors AppSettings in backend/app/models/media.py). Stored as
/// `<data_dir>/settings.json`; missing keys fall back to the defaults below.
#[derive(Clone, Serialize, Deserialize)]
#[serde(default)]
struct AppSettings {
    download_dir: String,
    default_kind: String,
    default_quality: String,
    default_container: String,
    default_audio_format: String,
    default_embed_subs: bool,
    default_embed_chapters: bool,
    nfo_sidecars: bool,
    music_folders: bool,
    prefer_soundcloud_lossless: bool,
    fetch_lyrics: bool,
    lyrics_lrc: bool,
    cookies_from_browser: Option<String>,
    cookies_file: Option<String>,
    proxy: Option<String>,
    po_token: Option<String>,
    po_token_mode: String,
    autotag_source: String,
    sponsorblock_enabled: bool,
    sponsorblock_action: String,
    filename_template: String,
    rate_limit: Option<String>,
    use_aria2c: bool,
    video_codec: String,
    audio_bitrate: String,
    normalize_audio: bool,
    normalize_lufs: i32,
    check_updates: bool,
    notify_on_complete: bool,
    minimize_to_tray: bool,
    launch_at_startup: bool,
    disable_global_hotkeys: bool,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            download_dir: download_dir().display().to_string(),
            default_kind: "video".into(),
            default_quality: "best".into(),
            default_container: "mp4".into(),
            default_audio_format: "mp3".into(),
            default_embed_subs: false,
            default_embed_chapters: false,
            nfo_sidecars: false,
            music_folders: false,
            prefer_soundcloud_lossless: false,
            fetch_lyrics: false,
            lyrics_lrc: false,
            cookies_from_browser: None,
            cookies_file: None,
            proxy: None,
            po_token: None,
            po_token_mode: "manual".into(),
            autotag_source: "auto".into(),
            sponsorblock_enabled: false,
            sponsorblock_action: "remove".into(),
            filename_template: "%(title)s".into(),
            rate_limit: None,
            use_aria2c: false,
            video_codec: "any".into(),
            audio_bitrate: "best".into(),
            normalize_audio: false,
            normalize_lufs: -14,
            check_updates: true,
            notify_on_complete: true,
            minimize_to_tray: false,
            launch_at_startup: false,
            disable_global_hotkeys: false,
        }
    }
}

fn settings_path() -> std::path::PathBuf {
    data_dir().join("settings.json")
}

fn load_settings() -> AppSettings {
    std::fs::read_to_string(settings_path())
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save_settings(s: &AppSettings) -> Result<(), String> {
    let _ = std::fs::create_dir_all(data_dir());
    let json = serde_json::to_string_pretty(s).map_err(|e| e.to_string())?;
    std::fs::write(settings_path(), json).map_err(|e| e.to_string())
}

async fn get_settings() -> Json<AppSettings> {
    Json(load_settings())
}

async fn put_settings(
    Json(s): Json<AppSettings>,
) -> Result<Json<AppSettings>, (StatusCode, String)> {
    save_settings(&s).map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e))?;
    Ok(Json(s))
}

#[derive(Serialize)]
struct HistoryEntry {
    id: i64,
    title: String,
    url: String,
    kind: String,
    status: String,
    filename: Option<String>,
    filepath: Option<String>,
    filesize: Option<i64>,
    quality: Option<String>,
    error_message: Option<String>,
    created_at: String,
    mtime: Option<f64>,
}

#[derive(Serialize)]
struct HistoryStats {
    total_downloads: i64,
    total_bytes: i64,
    transferred: String,
}

fn history_db() -> std::path::PathBuf {
    data_dir().join("history.db")
}

const HISTORY_SCHEMA: &str = "CREATE TABLE IF NOT EXISTS downloads (\
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, url TEXT NOT NULL, \
    kind TEXT NOT NULL, status TEXT NOT NULL, filename TEXT, filepath TEXT, \
    filesize INTEGER, quality TEXT, error_message TEXT, created_at TEXT NOT NULL);";

fn file_mtime(path: &Option<String>) -> Option<f64> {
    let p = path.as_ref()?;
    std::fs::metadata(p)
        .ok()?
        .modified()
        .ok()?
        .duration_since(std::time::UNIX_EPOCH)
        .ok()
        .map(|d| d.as_secs_f64())
}

async fn get_history() -> Json<Vec<HistoryEntry>> {
    let conn = match rusqlite::Connection::open(history_db()) {
        Ok(c) => c,
        Err(_) => return Json(vec![]),
    };
    let mut stmt = match conn.prepare(
        "SELECT id,title,url,kind,status,filename,filepath,filesize,quality,error_message,created_at \
         FROM downloads ORDER BY id DESC LIMIT 50",
    ) {
        Ok(s) => s,
        Err(_) => return Json(vec![]),
    };
    let rows = stmt.query_map([], |r| {
        let filepath: Option<String> = r.get(6)?;
        Ok(HistoryEntry {
            id: r.get(0)?,
            title: r.get(1)?,
            url: r.get(2)?,
            kind: r.get(3)?,
            status: r.get(4)?,
            filename: r.get(5)?,
            mtime: file_mtime(&filepath),
            filepath,
            filesize: r.get(7)?,
            quality: r.get(8)?,
            error_message: r.get(9)?,
            created_at: r.get(10)?,
        })
    });
    Json(
        rows.map(|it| it.filter_map(Result::ok).collect())
            .unwrap_or_default(),
    )
}

async fn get_history_stats() -> Json<HistoryStats> {
    let (count, total) = rusqlite::Connection::open(history_db())
        .ok()
        .and_then(|c| {
            c.query_row(
                "SELECT COUNT(*), COALESCE(SUM(filesize),0) FROM downloads WHERE status='completed'",
                [],
                |r| Ok((r.get::<_, i64>(0)?, r.get::<_, i64>(1)?)),
            )
            .ok()
        })
        .unwrap_or((0, 0));
    Json(HistoryStats {
        total_downloads: count,
        total_bytes: total,
        transferred: humanize_bytes(total),
    })
}

/// Persist one finished download (completed or error) to the history DB.
#[allow(clippy::too_many_arguments)]
fn record_download(
    title: &str,
    url: &str,
    kind: &str,
    status: &str,
    filename: Option<&str>,
    filepath: Option<&str>,
    filesize: Option<i64>,
    quality: Option<&str>,
    error: Option<&str>,
) {
    let _ = std::fs::create_dir_all(data_dir());
    if let Ok(conn) = rusqlite::Connection::open(history_db()) {
        let _ = conn.execute_batch(HISTORY_SCHEMA);
        let created = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();
        let _ = conn.execute(
            "INSERT INTO downloads \
             (title,url,kind,status,filename,filepath,filesize,quality,error_message,created_at) \
             VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10)",
            rusqlite::params![
                title, url, kind, status, filename, filepath, filesize, quality, error, created
            ],
        );
    }
}

/// After auto-tagging: relabel the latest history row for this file to the tagged
/// "Artist - Title" (mirrors history_store.update_title).
fn update_history_title(filepath: &str, title: &str) {
    if let Ok(conn) = rusqlite::Connection::open(history_db()) {
        let _ = conn.execute(
            "UPDATE downloads SET title = ?1 \
             WHERE id = (SELECT MAX(id) FROM downloads WHERE filepath = ?2)",
            rusqlite::params![title, filepath],
        );
    }
}

/// After auto-tagging renamed/relocated the file: update title + location of the
/// latest history row for the old path (mirrors history_store.update_after_tag).
fn update_history_after_tag(old_filepath: &str, new_filepath: &str, filename: &str, title: &str) {
    if let Ok(conn) = rusqlite::Connection::open(history_db()) {
        let _ = conn.execute(
            "UPDATE downloads SET title = ?1, filepath = ?2, filename = ?3 \
             WHERE id = (SELECT MAX(id) FROM downloads WHERE filepath = ?4)",
            rusqlite::params![title, new_filepath, filename, old_filepath],
        );
    }
}

// ---- logs (Registro tab) -----------------------------------------------------

fn log_file() -> std::path::PathBuf {
    data_dir().join("logs").join("yoink.log")
}

/// Append one timestamped line to the app log (best-effort).
fn log_line(msg: &str) {
    let path = log_file();
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let line = format!("{} {msg}\n", chrono::Utc::now().format("%Y-%m-%d %H:%M:%S"));
    use std::io::Write;
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
    {
        let _ = f.write_all(line.as_bytes());
    }
}

async fn get_logs() -> Json<Value> {
    let path = log_file();
    let content = std::fs::read_to_string(&path).unwrap_or_default();
    let all: Vec<&str> = content.lines().collect();
    const CAP: usize = 1000;
    let truncated = all.len() > CAP;
    let tail = if truncated {
        &all[all.len() - CAP..]
    } else {
        &all[..]
    };
    Json(serde_json::json!({
        "path": path.display().to_string(),
        "content": tail.join("\n"),
        "lines": tail.len(),
        "truncated": truncated,
    }))
}

// ---- misc endpoints ----------------------------------------------------------

async fn ytdlp_version() -> Json<VersionInfo> {
    let current = tokio::process::Command::new(ytdlp_bin())
        .arg("--version")
        .output()
        .await
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_else(|| "unknown".into());
    Json(VersionInfo {
        current,
        latest: None,
        update_available: false,
        release_url: None,
        error: None,
    })
}

#[derive(Deserialize)]
struct OpenRequest {
    #[serde(default)]
    path: Option<String>,
    #[serde(default)]
    open_file: bool,
}

/// Reveal a file/folder in the OS file manager — constrained to the download
/// directory so it can't browse arbitrary paths (as in routers/history.py).
async fn open_path(Json(req): Json<OpenRequest>) -> Result<Json<Value>, (StatusCode, String)> {
    let settings = load_settings();
    let dl = std::path::PathBuf::from(&settings.download_dir);
    let _ = std::fs::create_dir_all(&dl);
    let dl = dl.canonicalize().unwrap_or(dl);

    let target = match &req.path {
        Some(p) => {
            let t = std::path::PathBuf::from(p);
            let t = t.canonicalize().unwrap_or(t);
            if t != dl && !t.starts_with(&dl) {
                return Err((
                    StatusCode::FORBIDDEN,
                    "path is outside the download directory".into(),
                ));
            }
            t
        }
        None => dl.clone(),
    };
    let to_open = if req.open_file {
        target
    } else if target.is_file() {
        target
            .parent()
            .map(std::path::Path::to_path_buf)
            .unwrap_or(target)
    } else {
        target
    };
    let _ = std::process::Command::new("xdg-open").arg(&to_open).spawn();
    Ok(Json(serde_json::json!({ "status": "ok" })))
}

// ---- music match -------------------------------------------------------------

#[derive(Deserialize)]
struct MusicTrack {
    #[serde(default)]
    title: String,
    #[serde(default)]
    artists: String,
    #[serde(default)]
    duration_ms: Option<i64>,
    #[serde(default)]
    isrc: Option<String>,
}

/// Run a yt-dlp flat search/extract (with transient-retry + cookie fallback) and
/// return its `entries` array.
async fn ytdlp_entries(query: &str, settings: &AppSettings) -> Vec<Value> {
    run_ytdlp_json(&["-J", "--flat-playlist", "--no-warnings", query], settings)
        .await
        .ok()
        .and_then(|out| serde_json::from_slice::<Value>(&out).ok())
        .and_then(|j| j.get("entries").and_then(Value::as_array).cloned())
        .unwrap_or_default()
}

fn cand_url(cand: &Value) -> Option<String> {
    cand.get("url")
        .or_else(|| cand.get("webpage_url"))
        .and_then(Value::as_str)
        .map(str::to_string)
}

/// Exact YouTube Music recording by ISRC (take result #1, duration-gated). ISRCs
/// are plain [A-Z0-9], so no URL-encoding is needed. Mirrors _ytmusic_isrc_match.
async fn ytmusic_isrc_match(
    isrc: &str,
    duration_ms: Option<i64>,
    settings: &AppSettings,
) -> Option<String> {
    let search = format!("https://music.youtube.com/search?q={isrc}#songs");
    let out = run_ytdlp_json(
        &[
            "-J",
            "--flat-playlist",
            "--playlist-items",
            "1",
            "--no-warnings",
            &search,
        ],
        settings,
    )
    .await
    .ok()?;
    let j: Value = serde_json::from_slice(&out).ok()?;
    let vid = j
        .get("entries")
        .and_then(Value::as_array)
        .and_then(|a| a.first())
        .and_then(|e| e.get("id"))
        .and_then(Value::as_str)?
        .to_string();
    if let Some(target) = duration_ms {
        let watch = format!("https://music.youtube.com/watch?v={vid}");
        if let Ok(out2) = run_ytdlp_json(
            &["-J", "--no-warnings", "--skip-download", &watch],
            settings,
        )
        .await
        {
            if let Ok(full) = serde_json::from_slice::<Value>(&out2) {
                if let Some(d) = full.get("duration").and_then(Value::as_f64) {
                    if ((d as i64) * 1000 - target).abs() > 3000 {
                        return None;
                    }
                }
            }
        }
    }
    Some(format!("https://music.youtube.com/watch?v={vid}"))
}

/// True if any audio format is lossless (FLAC/ALAC/WAV/AIFF).
fn formats_lossless(formats: Option<&Value>) -> bool {
    let Some(arr) = formats.and_then(Value::as_array) else {
        return false;
    };
    arr.iter().any(|f| {
        let acodec = f
            .get("acodec")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_lowercase();
        let ext = f
            .get("ext")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_lowercase();
        matches!(acodec.as_str(), "flac" | "alac")
            || matches!(ext.as_str(), "wav" | "flac" | "aiff")
    })
}

/// A lossless SoundCloud source for the track, if one exists and matches.
async fn soundcloud_lossless_match(
    title: &str,
    artists: &str,
    duration_ms: Option<i64>,
    settings: &AppSettings,
) -> Option<String> {
    let query = format!("{artists} {title}");
    let query = query.trim();
    if query.is_empty() {
        return None;
    }
    let candidates = ytdlp_entries(&format!("scsearch5:{query}"), settings).await;
    let (best, _) = matching::best_match(title, artists, duration_ms, &candidates)?;
    let url = cand_url(best)?;
    let out = run_ytdlp_json(&["-J", "--no-warnings", "--skip-download", &url], settings)
        .await
        .ok()?;
    let full: Value = serde_json::from_slice(&out).ok()?;
    formats_lossless(full.get("formats")).then_some(url)
}

/// Best source URL for an imported track: a lossless SoundCloud source (opt-in),
/// then the exact YouTube Music recording by ISRC, then a ranked YouTube text
/// search (tight top-5, widening to top-10). Mirrors find_youtube_match.
/// Best source URL for an imported track: a lossless SoundCloud source (opt-in),
/// then the exact YouTube Music recording by ISRC, then a ranked YouTube text
/// search (tight top-5, widening to top-10). Shared by the handler and the CLI.
async fn find_youtube_match(
    title: &str,
    artists: &str,
    duration_ms: Option<i64>,
    isrc: Option<&str>,
    settings: &AppSettings,
) -> Option<String> {
    if settings.prefer_soundcloud_lossless {
        if let Some(url) = soundcloud_lossless_match(title, artists, duration_ms, settings).await {
            return Some(url);
        }
    }
    if let Some(i) = isrc {
        if let Some(url) = ytmusic_isrc_match(i, duration_ms, settings).await {
            return Some(url);
        }
    }
    for count in [5, 10] {
        let candidates =
            ytdlp_entries(&format!("ytsearch{count}:{title} {artists}"), settings).await;
        if let Some((cand, _)) = matching::best_match(title, artists, duration_ms, &candidates) {
            if let Some(url) = cand_url(cand) {
                return Some(url);
            }
        }
    }
    None
}

async fn music_match(Json(track): Json<MusicTrack>) -> Result<Json<Value>, (StatusCode, String)> {
    let settings = load_settings();
    // Resolve the ISRC once (the track's own, else via Deezer) — for the match and
    // for tagging downstream.
    let isrc = match track.isrc.as_deref() {
        Some(i) if !i.is_empty() => Some(i.to_string()),
        _ => music::deezer_isrc(&track.title, &track.artists, track.duration_ms).await,
    };
    let url = find_youtube_match(
        &track.title,
        &track.artists,
        track.duration_ms,
        isrc.as_deref(),
        &settings,
    )
    .await;
    Ok(Json(
        serde_json::json!({ "youtube_url": url, "isrc": isrc }),
    ))
}

async fn music_cover(Json(track): Json<MusicTrack>) -> Json<Value> {
    let (cover_url, duration_ms) = music::track_meta(&track.title, &track.artists).await;
    Json(serde_json::json!({ "cover_url": cover_url, "duration_ms": duration_ms }))
}

#[derive(Deserialize)]
struct ResolveRequest {
    url: String,
}

/// Resolve a music-service URL into a tracklist (keyless). Deezer is ported;
/// Spotify/Apple/Tidal/Amazon are later slices.
/// Resolve a music-service URL into a tracklist (shared by the handler + CLI).
async fn resolve_music(url: &str) -> Result<music::MusicImportInfo, String> {
    match music::detect_source(url) {
        Some("deezer") => music::resolve_deezer(url).await,
        Some("spotify") => music::resolve_spotify(url).await,
        Some("apple") => music::resolve_apple(url).await,
        Some("tidal") => music::resolve_tidal(url).await,
        Some("amazon") => music::resolve_amazon(url).await,
        Some(other) => Err(format!("{other} import is not supported")),
        None => Err("Not a recognised music-service URL.".into()),
    }
}

async fn music_resolve(
    Json(req): Json<ResolveRequest>,
) -> Result<Json<music::MusicImportInfo>, (StatusCode, String)> {
    resolve_music(&req.url)
        .await
        .map(Json)
        .map_err(|e| (StatusCode::UNPROCESSABLE_ENTITY, e))
}

// ---- release notes ("what's new" popup) --------------------------------------

const REPO: &str = "ayozetr/yoink-app";

fn parse_ver(v: &str) -> Option<(u32, u32, u32)> {
    let mut it = v.trim_start_matches('v').split('.');
    Some((
        it.next()?.parse().ok()?,
        it.next()?.parse().ok()?,
        it.next()?.parse().ok()?,
    ))
}

/// The notes before the hidden `<!-- /whatsnew -->` marker (or the Downloads
/// table), matching routers/settings.py + updates._trim_notes.
fn trim_notes(body: &str) -> String {
    if let Some(idx) = body.find("<!-- /whatsnew -->") {
        return body[..idx].trim().to_string();
    }
    if let Some(idx) = body.find("\n## Downloads") {
        return body[..idx].trim().to_string();
    }
    body.trim().to_string()
}

#[derive(Deserialize)]
struct RnParams {
    #[serde(default)]
    since: Option<String>,
}

async fn release_notes(axum::extract::Query(p): axum::extract::Query<RnParams>) -> Json<Value> {
    let current = parse_ver(APP_VERSION);
    let since = p.since.as_deref().and_then(parse_ver);
    let client = reqwest::Client::builder()
        .user_agent("Yoink")
        .build()
        .unwrap_or_default();
    let releases: Vec<Value> = async {
        let resp = client
            .get(format!(
                "https://api.github.com/repos/{REPO}/releases?per_page=30"
            ))
            .send()
            .await
            .ok()?;
        resp.json::<Value>().await.ok()?.as_array().cloned()
    }
    .await
    .unwrap_or_default();

    let mut entries = Vec::new();
    for rel in &releases {
        let is_pre = rel
            .get("prerelease")
            .and_then(Value::as_bool)
            .unwrap_or(false)
            || rel.get("draft").and_then(Value::as_bool).unwrap_or(false);
        if is_pre {
            continue;
        }
        let tag = rel.get("tag_name").and_then(Value::as_str).unwrap_or("");
        let Some(ver) = parse_ver(tag) else { continue };
        let include = match (since, current) {
            (Some(sv), Some(cv)) => ver > sv && ver <= cv,
            (None, Some(cv)) => ver == cv,
            _ => false,
        };
        if !include {
            continue;
        }
        let body = rel.get("body").and_then(Value::as_str).unwrap_or("");
        entries.push(serde_json::json!({ "version": tag, "notes": trim_notes(body) }));
    }
    Json(serde_json::json!({ "entries": entries }))
}

// ---- autotag -----------------------------------------------------------------

#[derive(Deserialize)]
struct ApplyRequest {
    path: String,
    #[serde(default)]
    title: Option<String>,
    #[serde(default)]
    artist: Option<String>,
    #[serde(default)]
    album: Option<String>,
    #[serde(default)]
    year: Option<String>,
    #[serde(default)]
    genre: Option<String>,
    #[serde(default)]
    track_number: Option<u32>,
    #[serde(default)]
    isrc: Option<String>,
    #[serde(default)]
    cover_url: Option<String>,
}

/// Write the chosen tags + cover into a downloaded audio file (constrained to the
/// download directory). Lyrics, .nfo and music-folder relocation are later slices.
async fn autotag_apply(Json(req): Json<ApplyRequest>) -> Result<Json<Value>, (StatusCode, String)> {
    let settings = load_settings();
    let dl = std::path::PathBuf::from(&settings.download_dir);
    let dl = dl.canonicalize().unwrap_or(dl);
    let p = std::path::PathBuf::from(&req.path);
    let pc = p.canonicalize().unwrap_or(p);
    if pc != dl && !pc.starts_with(&dl) {
        return Err((
            StatusCode::FORBIDDEN,
            "path is outside the download directory".into(),
        ));
    }
    let cover = match req.cover_url.as_deref() {
        Some(u) if !u.is_empty() => autotag::fetch_cover(u).await,
        _ => None,
    };
    // Capture the tagged fields before they move into ApplyFields (needed for the
    // .nfo + rename/relocate below).
    let path_s = req.path.clone();
    let title_s = req.title.clone().unwrap_or_default().trim().to_string();
    let artist_s = req.artist.clone().unwrap_or_default().trim().to_string();
    let album_s = req.album.clone().unwrap_or_default().trim().to_string();
    let year_s = req.year.clone().unwrap_or_default().trim().to_string();
    let genre_s = req.genre.clone().unwrap_or_default().trim().to_string();
    let cover_url_s = req.cover_url.clone().unwrap_or_default();

    let fields = autotag::ApplyFields {
        path: req.path,
        title: req.title,
        artist: req.artist,
        album: req.album,
        year: req.year,
        genre: req.genre,
        track_number: req.track_number,
        isrc: req.isrc,
        cover,
    };
    let embedded = tokio::task::spawn_blocking(move || autotag::write_tags(&fields))
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
        .map_err(|e| (StatusCode::UNPROCESSABLE_ENTITY, e))?;

    // Rewrite the per-file .nfo (if enabled) with the *tagged* metadata.
    if settings.nfo_sidecars {
        let body = nfo::build(&nfo::NfoFields {
            kind: "audio",
            title: &title_s,
            artist: &artist_s,
            album: &album_s,
            genre: &genre_s,
            year: &year_s,
            thumb: &cover_url_s,
            ..Default::default()
        });
        nfo::write(std::path::Path::new(&path_s), &body);
    }

    // Reflect "Artist - Title" in history, and rename/relocate the file per the
    // active filename template + the music-folders setting (mirrors the router).
    let have_both = !artist_s.is_empty() && !title_s.is_empty();
    let new_title = if have_both {
        format!("{artist_s} - {title_s}")
    } else {
        title_s.clone()
    };
    let renamed: Option<String> = if have_both {
        if settings.filename_template == AUTOTAG_FILENAME_TEMPLATE {
            Some(format!("{artist_s} - {title_s}"))
        } else if settings.filename_template == AUTOTAG_FILENAME_TEMPLATE_REVERSED {
            Some(format!("{title_s} - {artist_s}"))
        } else {
            None
        }
    } else {
        None
    };
    if !new_title.is_empty() {
        let download_root = std::env::var("YOINK_DOWNLOAD_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| std::path::PathBuf::from(&settings.download_dir));
        if settings.music_folders && have_both {
            let stem = renamed.clone().unwrap_or_else(|| new_title.clone());
            let (old, a, al, y, cu, ns) = (
                path_s.clone(),
                artist_s.clone(),
                album_s.clone(),
                year_s.clone(),
                cover_url_s.clone(),
                stem.clone(),
            );
            let nfo_on = settings.nfo_sidecars;
            let new_path = tokio::task::spawn_blocking(move || {
                library::organize_music_library(
                    std::path::Path::new(&old),
                    &a,
                    &al,
                    &y,
                    &ns,
                    (!cu.is_empty()).then_some(cu.as_str()),
                    &download_root,
                    nfo_on,
                )
            })
            .await
            .unwrap_or_else(|_| std::path::PathBuf::from(&path_s));
            let filename = new_path
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("")
                .to_string();
            update_history_after_tag(&path_s, &new_path.to_string_lossy(), &filename, &stem);
        } else if let Some(r) = renamed.clone() {
            let (old, rr) = (path_s.clone(), r.clone());
            let new_path = tokio::task::spawn_blocking(move || {
                library::rename_to_tagged(std::path::Path::new(&old), &rr)
            })
            .await
            .unwrap_or_else(|_| std::path::PathBuf::from(&path_s));
            let filename = new_path
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("")
                .to_string();
            update_history_after_tag(&path_s, &new_path.to_string_lossy(), &filename, &r);
        } else {
            update_history_title(&path_s, &new_title);
        }
    }
    Ok(Json(
        serde_json::json!({ "ok": true, "embedded_cover": embedded }),
    ))
}

#[derive(Deserialize)]
struct IdentifyRequest {
    path: String,
}

/// Catalogue matches for a downloaded file, keyed on its filename (mirrors
/// autotag_service.identify). Only the basename is read, not the file.
async fn autotag_identify(Json(req): Json<IdentifyRequest>) -> Json<Value> {
    let name = std::path::Path::new(&req.path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("");
    let (artist, title) = autotag::guess_from_filename(name);
    let source = load_settings().autotag_source;
    let mut results = if title.is_empty() {
        vec![]
    } else {
        autotag::search_catalogue(&source, &artist, &title).await
    };
    // Some channels title "Song - Artist"; retry swapped if nothing matched.
    if results.is_empty() && !artist.is_empty() && !title.is_empty() {
        results = autotag::search_catalogue(&source, &title, &artist).await;
    }
    Json(serde_json::json!({ "results": results }))
}

#[derive(Deserialize)]
struct AutotagSearchRequest {
    #[serde(default)]
    artist: String,
    title: String,
}

async fn autotag_search(Json(req): Json<AutotagSearchRequest>) -> Json<Value> {
    let source = load_settings().autotag_source;
    let results = autotag::search_catalogue(&source, &req.artist, &req.title).await;
    Json(serde_json::json!({ "results": results }))
}

#[derive(Deserialize)]
struct LyricsRequest {
    title: String,
    #[serde(default)]
    artist: String,
    #[serde(default)]
    album: Option<String>,
    #[serde(default)]
    path: Option<String>,
}

async fn autotag_lyrics(Json(req): Json<LyricsRequest>) -> Json<Value> {
    let duration = req.path.as_deref().and_then(autotag::probe_duration);
    let r = autotag::fetch_lyrics(&req.title, &req.artist, req.album.as_deref(), duration).await;
    Json(serde_json::json!({
        "found": r.found,
        "instrumental": r.instrumental,
        "has_synced": r.has_synced,
        "plain": r.plain,
    }))
}

// ---- server ------------------------------------------------------------------

#[tokio::main]
async fn main() {
    // Launched with arguments → run the CLI; with none → serve the API (how the
    // Tauri shell spawns it).
    let argv: Vec<String> = std::env::args().collect();
    if argv.len() > 1 {
        std::process::exit(cli::run(argv).await);
    }

    let port: u16 = std::env::var("YOINK_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(8756);

    // Mirror the Python CORS allow-list: the Vite dev server and the Tauri
    // webview origins (a later slice can share the exact regex).
    let origins: Vec<HeaderValue> = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "tauri://localhost",
        "http://tauri.localhost",
    ]
    .iter()
    .filter_map(|o| o.parse().ok())
    .collect();
    let cors = CorsLayer::new()
        .allow_origin(origins)
        .allow_methods([Method::GET, Method::POST, Method::PUT])
        .allow_headers([axum::http::header::CONTENT_TYPE]);

    let app = Router::new()
        .route("/api/version", get(version))
        .route("/api/info", post(info))
        .route("/api/search", get(search))
        .route("/api/ws/download", get(ws_download))
        .route("/api/settings", get(get_settings).put(put_settings))
        .route("/api/history", get(get_history))
        .route("/api/history/stats", get(get_history_stats))
        .route("/api/ytdlp-version", get(ytdlp_version))
        .route("/api/release-notes", get(release_notes))
        .route("/api/logs", get(get_logs))
        .route("/api/open", post(open_path))
        .route("/api/music/match", post(music_match))
        .route("/api/music/resolve", post(music_resolve))
        .route("/api/music/cover", post(music_cover))
        .route("/api/autotag/apply", post(autotag_apply))
        .route("/api/autotag/identify", post(autotag_identify))
        .route("/api/autotag/search", post(autotag_search))
        .route("/api/autotag/lyrics", post(autotag_lyrics))
        .layer(cors);

    // Shut down when the parent (the Tauri shell) closes our stdin — mirrors the
    // Python backend's watchdog. Only when the shell asks (it hands us an open
    // pipe); a dev/standalone run inherits an already-EOF stdin and must NOT
    // exit, so the watchdog is gated on the env var the shell sets.
    if std::env::var_os("YOINK_STDIN_WATCHDOG").is_some() {
        tokio::spawn(async {
            let mut stdin = tokio::io::stdin();
            let mut buf = [0u8; 256];
            loop {
                match stdin.read(&mut buf).await {
                    Ok(0) | Err(_) => std::process::exit(0),
                    Ok(_) => {}
                }
            }
        });
    }

    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    println!("yoink-core {APP_VERSION} listening on http://{addr}");
    log_line(&format!("yoink-core {APP_VERSION} started on port {port}"));
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
