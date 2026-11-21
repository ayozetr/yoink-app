// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! The backend client. The egui UI is synchronous and must never block, so all
//! network work (REST `/api/info`, the `/api/ws/download` WebSocket) runs on a
//! background tokio runtime. The UI talks to it over channels: it pushes [`Cmd`]s
//! and drains [`Evt`]s each frame, and the worker calls `ctx.request_repaint()`
//! whenever it has news so the UI wakes even while idle.

use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio_tungstenite::tungstenite::Message;

/// The local backend's port (`YOINK_PORT`, default 8756).
pub fn port() -> u16 {
    std::env::var("YOINK_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(8756)
}

fn http_base() -> String {
    format!("http://127.0.0.1:{}", port())
}

// ------------------------------------------------------------------ messages

/// A request from the UI to the worker.
pub enum Cmd {
    Analyze(String),
    Download(DownloadReq),
    SaveSettings(Box<Settings>),
    LoadHistory,
    Open(String),
}

/// A piece of news from the worker to the UI.
pub enum Evt {
    Settings(Box<Settings>),
    SettingsSaved,
    History(Vec<HistoryEntry>),
    Analyzing,
    Info(VideoLite),
    Playlist {
        title: String,
        count: usize,
    },
    AnalyzeErr(String),
    Progress {
        percent: f32,
        speed: Option<String>,
        eta: Option<String>,
    },
    Done(String),
    DownloadErr(String),
}

/// A mirror of the backend `AppSettings` — held whole so a save round-trips every
/// field, not just the ones the UI edits.
#[derive(Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    pub download_dir: String,
    pub default_kind: String,
    pub default_quality: String,
    pub default_container: String,
    pub default_audio_format: String,
    pub default_embed_subs: bool,
    pub default_embed_chapters: bool,
    pub nfo_sidecars: bool,
    pub music_folders: bool,
    pub prefer_soundcloud_lossless: bool,
    pub fetch_lyrics: bool,
    pub lyrics_lrc: bool,
    pub cookies_from_browser: Option<String>,
    pub cookies_file: Option<String>,
    pub proxy: Option<String>,
    pub po_token: Option<String>,
    pub po_token_mode: String,
    pub autotag_source: String,
    pub sponsorblock_enabled: bool,
    pub sponsorblock_action: String,
    pub filename_template: String,
    pub rate_limit: Option<String>,
    pub use_aria2c: bool,
    pub video_codec: String,
    pub audio_bitrate: String,
    pub normalize_audio: bool,
    pub normalize_lufs: i32,
    pub check_updates: bool,
    pub notify_on_complete: bool,
    pub minimize_to_tray: bool,
    pub launch_at_startup: bool,
    pub disable_global_hotkeys: bool,
}

/// A row of the download history (`GET /api/history`).
#[derive(Clone, Deserialize)]
pub struct HistoryEntry {
    pub title: String,
    pub kind: String,
    pub status: String,
    #[serde(default)]
    pub filepath: Option<String>,
    #[serde(default)]
    pub filesize: Option<i64>,
    #[serde(default)]
    pub quality: Option<String>,
    pub created_at: String,
}

/// The subset of `DownloadRequest` the UI sets; the backend fills the rest from
/// its serde defaults.
#[derive(Clone, Serialize)]
pub struct DownloadReq {
    pub url: String,
    pub kind: String, // "video" | "audio"
    pub quality: Option<String>,
    pub container: String,    // mp4 | mov | mkv | webm
    pub audio_format: String, // mp3 | m4a | opus | flac | wav
}

/// The fields of `VideoInfo` the preview shows.
#[derive(Clone, Deserialize)]
pub struct VideoLite {
    pub title: String,
    #[serde(default)]
    pub uploader: Option<String>,
    #[serde(default)]
    pub duration_string: Option<String>,
    #[serde(default)]
    pub has_audio: bool,
    #[serde(default)]
    pub is_vr: bool,
    #[serde(default)]
    pub formats: Vec<Value>,
}

#[derive(Deserialize)]
struct InfoResp {
    #[serde(default)]
    video: Option<VideoLite>,
    #[serde(default)]
    playlist: Option<PlaylistLite>,
}

#[derive(Deserialize)]
struct PlaylistLite {
    title: String,
    #[serde(default)]
    entry_count: usize,
}

// -------------------------------------------------------------------- client

/// Handle the UI holds: a sender for commands and a receiver for events.
pub struct Backend {
    tx: tokio::sync::mpsc::UnboundedSender<Cmd>,
    pub rx: std::sync::mpsc::Receiver<Evt>,
}

impl Backend {
    /// Spawn the worker thread (its own tokio runtime) and return the handle.
    pub fn spawn(ctx: egui::Context) -> Backend {
        let (cmd_tx, mut cmd_rx) = tokio::sync::mpsc::unbounded_channel::<Cmd>();
        let (evt_tx, evt_rx) = std::sync::mpsc::channel::<Evt>();

        std::thread::spawn(move || {
            let rt = tokio::runtime::Builder::new_multi_thread()
                .enable_all()
                .build()
                .expect("tokio runtime");
            rt.block_on(async move {
                // Read settings once at startup so the UI knows whether to run the
                // PO-token minter.
                {
                    let (evt_tx, ctx) = (evt_tx.clone(), ctx.clone());
                    tokio::spawn(async move { fetch_settings(evt_tx, ctx).await });
                }
                while let Some(cmd) = cmd_rx.recv().await {
                    let (evt_tx, ctx) = (evt_tx.clone(), ctx.clone());
                    match cmd {
                        Cmd::Analyze(url) => {
                            tokio::spawn(async move { analyze(url, evt_tx, ctx).await });
                        }
                        Cmd::Download(req) => {
                            tokio::spawn(async move { download(req, evt_tx, ctx).await });
                        }
                        Cmd::SaveSettings(s) => {
                            tokio::spawn(async move { save_settings(s, evt_tx, ctx).await });
                        }
                        Cmd::LoadHistory => {
                            tokio::spawn(async move { load_history(evt_tx, ctx).await });
                        }
                        Cmd::Open(path) => {
                            tokio::spawn(async move { open_path(path).await });
                        }
                    }
                }
            });
        });

        Backend {
            tx: cmd_tx,
            rx: evt_rx,
        }
    }

    pub fn send(&self, cmd: Cmd) {
        let _ = self.tx.send(cmd);
    }
}

fn emit(tx: &std::sync::mpsc::Sender<Evt>, ctx: &egui::Context, evt: Evt) {
    let _ = tx.send(evt);
    ctx.request_repaint();
}

async fn fetch_settings(tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let res = reqwest::Client::new()
        .get(format!("{}/api/settings", http_base()))
        .send()
        .await;
    if let Ok(r) = res {
        if let Ok(s) = r.json::<Settings>().await {
            emit(&tx, &ctx, Evt::Settings(Box::new(s)));
        }
    }
}

async fn save_settings(s: Box<Settings>, tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let res = reqwest::Client::new()
        .put(format!("{}/api/settings", http_base()))
        .json(&*s)
        .send()
        .await;
    match res {
        Ok(r) if r.status().is_success() => emit(&tx, &ctx, Evt::SettingsSaved),
        Ok(r) => emit(
            &tx,
            &ctx,
            Evt::DownloadErr(format!("save failed: {}", r.status())),
        ),
        Err(e) => emit(&tx, &ctx, Evt::DownloadErr(format!("save failed: {e}"))),
    }
}

async fn load_history(tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let res = reqwest::Client::new()
        .get(format!("{}/api/history", http_base()))
        .send()
        .await;
    if let Ok(r) = res {
        if let Ok(h) = r.json::<Vec<HistoryEntry>>().await {
            emit(&tx, &ctx, Evt::History(h));
        }
    }
}

async fn open_path(path: String) {
    let _ = reqwest::Client::new()
        .post(format!("{}/api/open", http_base()))
        .json(&serde_json::json!({ "path": path, "open_file": true }))
        .send()
        .await;
}

async fn analyze(url: String, tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    emit(&tx, &ctx, Evt::Analyzing);
    let client = reqwest::Client::new();
    let res = client
        .post(format!("{}/api/info", http_base()))
        .json(&serde_json::json!({ "url": url }))
        .send()
        .await;
    match res {
        Ok(r) if r.status().is_success() => match r.json::<InfoResp>().await {
            Ok(info) => {
                if let Some(v) = info.video {
                    emit(&tx, &ctx, Evt::Info(v));
                } else if let Some(p) = info.playlist {
                    emit(
                        &tx,
                        &ctx,
                        Evt::Playlist {
                            title: p.title,
                            count: p.entry_count,
                        },
                    );
                } else {
                    emit(&tx, &ctx, Evt::AnalyzeErr("empty response".into()));
                }
            }
            Err(e) => emit(&tx, &ctx, Evt::AnalyzeErr(format!("bad response: {e}"))),
        },
        Ok(r) => emit(
            &tx,
            &ctx,
            Evt::AnalyzeErr(format!("backend returned {}", r.status())),
        ),
        Err(e) => emit(
            &tx,
            &ctx,
            Evt::AnalyzeErr(format!("cannot reach backend: {e}")),
        ),
    }
}

async fn download(req: DownloadReq, tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let url = format!("ws://127.0.0.1:{}/api/ws/download", port());
    let (mut ws, _) = match tokio_tungstenite::connect_async(&url).await {
        Ok(s) => s,
        Err(e) => {
            return emit(
                &tx,
                &ctx,
                Evt::DownloadErr(format!("ws connect failed: {e}")),
            )
        }
    };
    let payload = serde_json::to_string(&req).unwrap_or_default();
    if let Err(e) = ws.send(Message::Text(payload)).await {
        return emit(&tx, &ctx, Evt::DownloadErr(format!("ws send failed: {e}")));
    }
    while let Some(msg) = ws.next().await {
        let text = match msg {
            Ok(Message::Text(t)) => t.to_string(),
            Ok(Message::Close(_)) | Err(_) => break,
            Ok(_) => continue,
        };
        let Ok(v) = serde_json::from_str::<Value>(&text) else {
            continue;
        };
        match v.get("type").and_then(Value::as_str) {
            Some("progress") => emit(
                &tx,
                &ctx,
                Evt::Progress {
                    percent: v.get("percent").and_then(Value::as_f64).unwrap_or(0.0) as f32,
                    speed: v.get("speed").and_then(Value::as_str).map(str::to_string),
                    eta: v.get("eta").and_then(Value::as_str).map(str::to_string),
                },
            ),
            Some("completed") => {
                let path = v
                    .get("filepath")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                emit(&tx, &ctx, Evt::Done(path));
                break;
            }
            Some("error") => {
                let msg = v
                    .get("message")
                    .and_then(Value::as_str)
                    .unwrap_or("download failed");
                emit(&tx, &ctx, Evt::DownloadErr(msg.to_string()));
                break;
            }
            _ => {}
        }
    }
}
