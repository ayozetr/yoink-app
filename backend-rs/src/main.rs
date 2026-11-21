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
    extract::Json,
    http::{HeaderValue, Method, StatusCode},
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tower_http::cors::CorsLayer;

const APP_VERSION: &str = env!("CARGO_PKG_VERSION");

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
struct InfoResponse {
    #[serde(rename = "type")]
    kind: &'static str,
    video: Option<VideoInfo>,
    playlist: Option<Value>,
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

/// Build the VideoInfo from yt-dlp's single-video JSON.
fn map_video(j: &Value) -> VideoInfo {
    let raw_formats = j.get("formats").and_then(Value::as_array);
    let formats: Vec<MediaFormat> = raw_formats
        .map(|fs| fs.iter().filter_map(map_format).collect())
        .unwrap_or_default();

    let has_audio = formats.iter().any(|f| f.has_audio);
    let best_audio_abr = raw_formats
        .map(|fs| {
            fs.iter()
                .filter(|f| codec(f, "acodec").is_some())
                .filter_map(|f| f.get("abr").and_then(Value::as_f64))
                .fold(None::<f64>, |acc, abr| Some(acc.map_or(abr, |a| a.max(abr))))
        })
        .flatten();
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
                s(f, "protocol").map(|p| p.contains("m3u8")).unwrap_or(false)
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
        // TODO(slice-2): port the VR / image heuristics from services/vr.py.
        is_vr: false,
        vr_layout: "180_sbs".to_string(),
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

async fn info(Json(req): Json<InfoRequest>) -> Result<Json<InfoResponse>, (StatusCode, String)> {
    let output = tokio::process::Command::new(ytdlp_bin())
        .args(["-J", "--no-warnings", &req.url])
        .output()
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("could not run yt-dlp: {e}"),
            )
        })?;

    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        // A genuinely unsupported/private URL vs. a transient failure is refined
        // in a later slice (503 retryable vs 422); 422 for now.
        return Err((
            StatusCode::UNPROCESSABLE_ENTITY,
            format!("yt-dlp could not extract this URL: {}", err.trim()),
        ));
    }

    let j: Value = serde_json::from_slice(&output.stdout)
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, format!("bad yt-dlp JSON: {e}")))?;

    if j.get("_type").and_then(Value::as_str) == Some("playlist") {
        // TODO(slice-2): map playlists (flat listing) — see routers/info.py.
        return Err((
            StatusCode::NOT_IMPLEMENTED,
            "playlists are not handled by the Rust core yet".to_string(),
        ));
    }

    Ok(Json(InfoResponse {
        kind: "video",
        video: Some(map_video(&j)),
        playlist: None,
    }))
}

// ---- server ------------------------------------------------------------------

#[tokio::main]
async fn main() {
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
        .allow_methods([Method::GET, Method::POST])
        .allow_headers([axum::http::header::CONTENT_TYPE]);

    let app = Router::new()
        .route("/api/version", get(version))
        .route("/api/info", post(info))
        .layer(cors);

    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    println!("yoink-core {APP_VERSION} listening on http://{addr}");
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
