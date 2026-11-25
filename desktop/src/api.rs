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
    Search {
        query: String,
        source: String,
    },
    ResolveMusic(String),
    /// Resolve a queued URL's display title in the background (POST /api/info).
    ResolveTitle {
        id: u64,
        url: String,
    },
    Download(DownloadReq, AutotagOpts),
    /// Tag-panel lookups + write.
    AutotagIdentify {
        path: String,
    },
    AutotagSearch {
        artist: String,
        title: String,
    },
    AutotagApply(Box<ApplyArgs>),
    ImportTrack(Box<MusicTrack>),
    SaveSettings(Box<Settings>),
    ReloadSettings,
    LoadHistory,
    /// Clear the download history (records only), then reload it.
    ClearHistory,
    LoadLogs,
    /// Clear the log file, then reload it.
    ClearLogs,
    LoadWhatsNew {
        since: String,
    },
    Open(String),
    /// Re-run the GitHub release check on demand (the About "check" button).
    CheckUpdate,
    /// Download the given release asset (verifying `signature`) and replace this
    /// binary in place.
    SelfUpdate {
        url: String,
        signature: String,
    },
}

/// What the client should do after a plain audio download finishes. The catalogue
/// source itself is read server-side by the autotag routes (`AppSettings`); the
/// client only needs to know whether to also fetch + embed lyrics.
#[derive(Clone, Copy, Default)]
pub struct AutotagOpts {
    pub fetch_lyrics: bool,
    /// A manual (Home) download shows the interactive tag panel instead of
    /// silently auto-tagging; a queue download tags silently.
    pub interactive: bool,
}

/// One catalogue match for the tag panel (from identify/search).
#[derive(Clone, Default, Deserialize)]
pub struct TagCandidate {
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub artist: String,
    #[serde(default)]
    pub album: Option<String>,
    #[serde(default)]
    pub year: Option<String>,
    #[serde(default)]
    pub genre: Option<String>,
    #[serde(default)]
    pub track_number: Option<i64>,
    #[serde(default)]
    pub cover_url: Option<String>,
}

/// Fields the tag panel sends to apply the chosen tags.
#[derive(Clone, Default)]
pub struct ApplyArgs {
    pub path: String,
    pub title: String,
    pub artist: String,
    pub album: String,
    pub year: String,
    pub genre: String,
    pub track_number: Option<i64>,
    pub cover_url: Option<String>,
    pub embed_lyrics: bool,
}

/// A piece of news from the worker to the UI.
pub enum Evt {
    Settings(Box<Settings>),
    /// The backend never answered the settings request (its retry budget ran out).
    SettingsLoadFailed,
    SettingsSaved,
    UpdateAvailable {
        version: String,
        /// The download URL of the asset for this platform (AppImage/exe), if the
        /// release has one — the in-place updater pulls from here.
        asset_url: Option<String>,
        /// The asset's minisign signature (base64 of the `.sig` content) from
        /// `latest.json`, verified before the download is installed.
        signature: Option<String>,
    },
    /// A completed update check found no newer release (so the UI can confirm it).
    UpToDate,
    /// In-place update download progress, 0.0..=1.0.
    UpdateProgress(f32),
    /// The binary was replaced; the path to relaunch (the app then exits).
    UpdateInstalled(std::path::PathBuf),
    UpdateError(String),
    WhatsNew(Vec<(String, String)>),
    History(Vec<HistoryEntry>),
    Logs {
        path: String,
        content: String,
    },
    Analyzing,
    Info(VideoLite),
    SearchResults {
        query: String,
        items: Vec<SearchItem>,
    },
    /// A queued URL's resolved display title.
    QueueTitle {
        id: u64,
        title: String,
    },
    /// Tag-panel catalogue matches (identify or manual search).
    AutotagResults {
        candidates: Vec<TagCandidate>,
    },
    /// The tag write finished (ok flag).
    AutotagApplied {
        ok: bool,
    },
    Music(Box<MusicInfo>),
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
    pub video_codec: String,
    pub audio_bitrate: String,
    pub normalize_audio: bool,
    pub normalize_lufs: i32,
    pub check_updates: bool,
    pub notify_on_complete: bool,
    pub minimize_to_tray: bool,
    pub launch_at_startup: bool,
    #[serde(default = "default_true")]
    pub rounded_corners: bool,
}

fn default_true() -> bool {
    true
}

/// A row of the download history (`GET /api/history`).
#[derive(Clone, Deserialize)]
pub struct HistoryEntry {
    pub title: String,
    pub kind: String,
    pub status: String,
    #[serde(default)]
    pub url: String,
    #[serde(default)]
    pub filepath: Option<String>,
    #[serde(default)]
    pub filesize: Option<i64>,
    #[serde(default)]
    pub quality: Option<String>,
    pub created_at: String,
}

/// One track of a resolved music-service import (`POST /api/music/resolve`). Sent
/// back verbatim to `POST /api/music/match`, so it mirrors the backend `MusicTrack`.
#[derive(Clone, Serialize, Deserialize)]
pub struct MusicTrack {
    pub title: String,
    pub artists: String,
    #[serde(default)]
    pub isrc: Option<String>,
    #[serde(default)]
    pub duration_ms: Option<i64>,
    #[serde(default)]
    pub is_explicit: bool,
    #[serde(default)]
    pub album: Option<String>,
    #[serde(default)]
    pub year: Option<String>,
    #[serde(default)]
    pub cover_url: Option<String>,
    #[serde(default)]
    pub source_url: String,
}

/// One search result (`GET /api/search`).
#[derive(Clone, Deserialize)]
pub struct SearchItem {
    pub title: String,
    pub url: String,
    #[serde(default)]
    pub uploader: Option<String>,
    #[serde(default)]
    pub duration_string: Option<String>,
    #[serde(default)]
    pub thumbnail_url: Option<String>,
}

#[derive(Clone, Deserialize)]
pub struct MusicInfo {
    pub source: String,
    pub name: String,
    #[serde(default)]
    pub subtitle: Option<String>,
    #[serde(default)]
    pub cover_url: Option<String>,
    pub tracks: Vec<MusicTrack>,
}

/// True for a Spotify/Deezer/Apple Music/Tidal/Amazon Music link (routed to the
/// keyless music importer instead of yt-dlp).
pub fn is_music_url(url: &str) -> bool {
    let u = url.to_lowercase();
    [
        "open.spotify.com",
        "spotify.link",
        "deezer.com",
        "deezer.page.link",
        "music.apple.com",
        "tidal.com",
        "music.amazon.",
    ]
    .iter()
    .any(|h| u.contains(h))
}

/// The subset of `DownloadRequest` the UI sets; the backend fills the rest from
/// its serde defaults.
#[derive(Clone, Default, Serialize)]
pub struct DownloadReq {
    pub url: String,
    pub kind: String, // "video" | "audio"
    pub quality: Option<String>,
    pub container: String,    // mp4 | mov | mkv | webm
    pub audio_format: String, // mp3 | m4a | opus | flac | wav
    // Advanced options — omitted from the JSON when unset so the backend keeps
    // its own serde defaults.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub video_codec: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub audio_bitrate: Option<String>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub embed_subs: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub subtitle_lang: Option<String>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub embed_chapters: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trim_start: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trim_end: Option<f64>,
}

/// The fields of `VideoInfo` the preview shows.
#[derive(Clone, Deserialize)]
pub struct VideoLite {
    pub title: String,
    #[serde(default)]
    pub thumbnail_url: Option<String>,
    #[serde(default)]
    pub uploader: Option<String>,
    #[serde(default)]
    pub duration_string: Option<String>,
    #[serde(default)]
    pub has_audio: bool,
    #[serde(default)]
    pub is_vr: bool,
    #[serde(default)]
    pub subtitle_langs: Vec<String>,
    #[serde(default)]
    pub has_chapters: bool,
    #[serde(default)]
    pub formats: Vec<FmtLite>,
}

/// Just enough of a format to show the best resolution and a size estimate.
#[derive(Clone, Deserialize)]
pub struct FmtLite {
    #[serde(default)]
    pub resolution: Option<String>,
    #[serde(default)]
    pub filesize: Option<i64>,
    #[serde(default)]
    pub has_audio: bool,
}

impl FmtLite {
    /// The video height this format carries (e.g. 2160 for "2160p"/"3840x2160"),
    /// or None for an audio-only format.
    fn height(&self) -> Option<u32> {
        let r = self.resolution.as_deref()?;
        let h = match r.split_once('x') {
            Some((_, h)) => h,
            None => r.trim_end_matches('p'),
        };
        h.trim().parse::<u32>().ok()
    }
}

impl VideoLite {
    /// The tallest video height among the formats (e.g. 2160 for "3840x2160").
    pub fn best_height(&self) -> Option<u32> {
        self.formats
            .iter()
            .filter_map(|f| {
                // Video formats carry a height, as "2160p" (this backend) or
                // "3840x2160"; audio-only ones say "audio only", which won't
                // parse — so a parseable height is itself the "is video" test.
                let r = f.resolution.as_deref()?;
                let h = match r.split_once('x') {
                    Some((_, h)) => h,
                    None => r.trim_end_matches('p'),
                };
                h.trim().parse::<u32>().ok()
            })
            .max()
    }

    /// Best audio-only format size (what gets merged into a video, or downloaded
    /// on its own for an audio job).
    fn best_audio_filesize(&self) -> Option<i64> {
        self.formats
            .iter()
            .filter(|f| f.has_audio && f.height().is_none())
            .filter_map(|f| f.filesize)
            .max()
    }

    /// Estimated download size for the current selection, mirroring the web:
    /// an audio job is just the audio track; a video job is the video format at
    /// the chosen height plus the audio it will be merged with (video-only DASH
    /// formats carry no audio, so it's added — matching yt-dlp's bestvideo+bestaudio).
    pub fn estimated_size(&self, kind: &str, quality: &str) -> Option<i64> {
        if kind == "audio" {
            return self.best_audio_filesize();
        }
        let target = if quality == "best" {
            self.best_height()
        } else {
            quality.trim_end_matches('p').parse::<u32>().ok()
        };
        // The largest-filesize format at the target height (fall back to any
        // video format when the exact height has no size), and whether it already
        // bundles audio.
        let pick = |want: Option<u32>| {
            self.formats
                .iter()
                .filter(|f| f.height().is_some() && want.is_none_or(|h| f.height() == Some(h)))
                .filter_map(|f| f.filesize.map(|sz| (sz, f.has_audio)))
                .max_by_key(|(sz, _)| *sz)
        };
        let (video, bundled_audio) = match pick(target).or_else(|| pick(None)) {
            Some(v) => v,
            None => return self.best_audio_filesize(),
        };
        // Add the audio track only if the video format doesn't already include it.
        match (bundled_audio, self.best_audio_filesize()) {
            (false, Some(a)) => Some(video + a),
            _ => Some(video),
        }
    }
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
                // The startup update check is triggered by the UI once settings
                // load, so it honours the "check for updates" setting instead of
                // hitting GitHub unconditionally.
                // Prefetch the History and Logs tabs so switching to them is
                // instant instead of waiting for a request on first open.
                {
                    let (evt_tx, ctx) = (evt_tx.clone(), ctx.clone());
                    tokio::spawn(async move { load_history(evt_tx, ctx).await });
                }
                {
                    let (evt_tx, ctx) = (evt_tx.clone(), ctx.clone());
                    tokio::spawn(async move { load_logs(evt_tx, ctx).await });
                }
                while let Some(cmd) = cmd_rx.recv().await {
                    let (evt_tx, ctx) = (evt_tx.clone(), ctx.clone());
                    match cmd {
                        Cmd::Analyze(url) => {
                            tokio::spawn(async move { analyze(url, evt_tx, ctx).await });
                        }
                        Cmd::Search { query, source } => {
                            tokio::spawn(async move { search(query, source, evt_tx, ctx).await });
                        }
                        Cmd::ResolveMusic(url) => {
                            tokio::spawn(async move { resolve_music(url, evt_tx, ctx).await });
                        }
                        Cmd::ResolveTitle { id, url } => {
                            tokio::spawn(async move { resolve_title(id, url, evt_tx, ctx).await });
                        }
                        Cmd::Download(req, autotag) => {
                            tokio::spawn(async move { download(req, autotag, evt_tx, ctx).await });
                        }
                        Cmd::AutotagIdentify { path } => {
                            tokio::spawn(async move {
                                let c = identify_tags(&path).await;
                                emit(&evt_tx, &ctx, Evt::AutotagResults { candidates: c });
                            });
                        }
                        Cmd::AutotagSearch { artist, title } => {
                            tokio::spawn(async move {
                                let c = search_tags(&artist, &title).await;
                                emit(&evt_tx, &ctx, Evt::AutotagResults { candidates: c });
                            });
                        }
                        Cmd::AutotagApply(args) => {
                            tokio::spawn(async move { apply_tags(*args, evt_tx, ctx).await });
                        }
                        Cmd::ImportTrack(t) => {
                            tokio::spawn(async move { import_track(*t, evt_tx, ctx).await });
                        }
                        Cmd::SaveSettings(s) => {
                            tokio::spawn(async move { save_settings(s, evt_tx, ctx).await });
                        }
                        Cmd::ReloadSettings => {
                            tokio::spawn(async move { fetch_settings(evt_tx, ctx).await });
                        }
                        Cmd::LoadHistory => {
                            tokio::spawn(async move { load_history(evt_tx, ctx).await });
                        }
                        Cmd::ClearHistory => {
                            tokio::spawn(async move { clear_history(evt_tx, ctx).await });
                        }
                        Cmd::LoadLogs => {
                            tokio::spawn(async move { load_logs(evt_tx, ctx).await });
                        }
                        Cmd::ClearLogs => {
                            tokio::spawn(async move { clear_logs(evt_tx, ctx).await });
                        }
                        Cmd::CheckUpdate => {
                            tokio::spawn(async move { check_update(evt_tx, ctx).await });
                        }
                        Cmd::LoadWhatsNew { since } => {
                            tokio::spawn(async move { load_whatsnew(since, evt_tx, ctx).await });
                        }
                        Cmd::Open(path) => {
                            tokio::spawn(async move { open_path(path).await });
                        }
                        Cmd::SelfUpdate { url, signature } => {
                            tokio::spawn(async move {
                                do_self_update(url, signature, evt_tx, ctx).await
                            });
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
    // The bundled backend may still be starting, so retry (for up to ~60 s)
    // instead of leaving Settings stuck on its spinner forever.
    for _ in 0..120 {
        if let Ok(r) = reqwest::Client::new()
            .get(format!("{}/api/settings", http_base()))
            .send()
            .await
        {
            if let Ok(s) = r.json::<Settings>().await {
                emit(&tx, &ctx, Evt::Settings(Box::new(s)));
                return;
            }
        }
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }
    // The backend never came up — tell the UI so it can show a retry instead of
    // spinning forever.
    emit(&tx, &ctx, Evt::SettingsLoadFailed);
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

/// Clear the history records, then reload (so the list empties).
async fn clear_history(tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let _ = reqwest::Client::new()
        .delete(format!("{}/api/history", http_base()))
        .send()
        .await;
    load_history(tx, ctx).await;
}

/// The platform key in `latest.json` for this OS.
#[cfg(target_os = "windows")]
const UPDATE_PLATFORM: &str = "windows-x86_64";
#[cfg(not(target_os = "windows"))]
const UPDATE_PLATFORM: &str = "linux-x86_64";

/// Check for a newer release via the same `latest.json` manifest the legacy
/// updater uses, so one release (one signature) serves both apps. We pull the
/// platform's download URL and its minisign signature from it.
async fn check_update(tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let res = reqwest::Client::new()
        .get("https://github.com/ayozetr/yoink-app/releases/latest/download/latest.json")
        .header("User-Agent", "yoink-desktop")
        .send()
        .await;
    // On any failure (offline, rate-limited, unexpected JSON) still emit a
    // terminal event so the UI's "checking…" state clears and the user can retry.
    let Ok(r) = res.and_then(reqwest::Response::error_for_status) else {
        emit(&tx, &ctx, Evt::UpToDate);
        return;
    };
    let Ok(v) = r.json::<Value>().await else {
        emit(&tx, &ctx, Evt::UpToDate);
        return;
    };
    let Some(version) = v.get("version").and_then(Value::as_str) else {
        emit(&tx, &ctx, Evt::UpToDate);
        return;
    };
    let latest = version.trim_start_matches('v');
    if !is_newer(latest, env!("CARGO_PKG_VERSION")) {
        emit(&tx, &ctx, Evt::UpToDate);
        return;
    }
    let plat = v.get("platforms").and_then(|p| p.get(UPDATE_PLATFORM));
    let asset_url = plat
        .and_then(|p| p.get("url"))
        .and_then(Value::as_str)
        .map(str::to_string);
    let signature = plat
        .and_then(|p| p.get("signature"))
        .and_then(Value::as_str)
        .map(str::to_string);
    emit(
        &tx,
        &ctx,
        Evt::UpdateAvailable {
            version: latest.to_string(),
            asset_url,
            signature,
        },
    );
}

/// The file this running binary can replace in place, or `None` when in-place
/// updates don't apply (a dev build, or a system-packaged .deb/.rpm): on Linux
/// only an AppImage (its real path is in `$APPIMAGE`, since the running exe is
/// the read-only mount); on Windows the executable itself.
pub fn self_update_target() -> Option<std::path::PathBuf> {
    #[cfg(target_os = "windows")]
    {
        std::env::current_exe().ok()
    }
    #[cfg(target_os = "linux")]
    {
        std::env::var_os("APPIMAGE").map(std::path::PathBuf::from)
    }
    #[cfg(not(any(target_os = "windows", target_os = "linux")))]
    {
        None
    }
}

/// Download `url` to a temp file beside `target`, then atomically swap it in and
/// tell the UI to relaunch. Everything is staged in a sibling temp file so a
/// failed or partial download never touches the live binary.
async fn do_self_update(
    url: String,
    signature: String,
    tx: std::sync::mpsc::Sender<Evt>,
    ctx: egui::Context,
) {
    let Some(target) = self_update_target() else {
        emit(&tx, &ctx, Evt::UpdateError("unsupported".into()));
        return;
    };
    match download_and_install(&url, &signature, &target, &tx, &ctx).await {
        Ok(()) => emit(&tx, &ctx, Evt::UpdateInstalled(target)),
        Err(e) => emit(&tx, &ctx, Evt::UpdateError(e)),
    }
}

/// The minisign public key releases are signed with — the SAME key the legacy
/// (Tauri) app used, so one signature in `latest.json` serves both the one-time
/// legacy→egui migration and the egui updater. An update is installed only if it
/// verifies against this key, so a tampered/compromised download can't run code.
const UPDATE_PUBKEY: &str = "RWR6dwLE3M1KiXJX7UfdVQtaQVSLUTrqF/K+Nvq9oLw+oJdvjbioh0p9";

/// Verify `file` against `signature` (base64 of a minisign `.sig`, from
/// `latest.json`) using the embedded public key. Fail-closed.
fn verify_update_signature(file: &std::path::Path, signature: &str) -> Result<(), String> {
    use base64::Engine;
    use minisign_verify::{PublicKey, Signature};
    let sig_text = base64::engine::general_purpose::STANDARD
        .decode(signature.trim())
        .map_err(|_| "malformed signature".to_string())
        .and_then(|b| String::from_utf8(b).map_err(|_| "malformed signature".to_string()))?;
    let pk = PublicKey::from_base64(UPDATE_PUBKEY).map_err(|e| e.to_string())?;
    let sig = Signature::decode(&sig_text).map_err(|_| "malformed signature".to_string())?;
    let data = std::fs::read(file).map_err(|e| e.to_string())?;
    pk.verify(&data, &sig, false)
        .map_err(|_| "signature verification failed".to_string())
}

/// Only `https` URLs on GitHub's own release/asset hosts are accepted for the
/// self-update download — no plaintext, no arbitrary hosts, no scheme downgrade.
fn is_trusted_release_url(url: &reqwest::Url) -> bool {
    url.scheme() == "https"
        && matches!(
            url.host_str(),
            Some(h) if h == "github.com" || h == "objects.githubusercontent.com"
                || h.ends_with(".githubusercontent.com")
        )
}

async fn download_and_install(
    url: &str,
    signature: &str,
    target: &std::path::Path,
    tx: &std::sync::mpsc::Sender<Evt>,
    ctx: &egui::Context,
) -> Result<(), String> {
    if signature.is_empty() {
        return Err("no signature for this release".into());
    }
    let parsed = reqwest::Url::parse(url).map_err(|e| e.to_string())?;
    if !is_trusted_release_url(&parsed) {
        return Err("untrusted update URL".into());
    }
    let dir = target.parent().ok_or("no parent dir")?;
    // A random, O_EXCL temp name so a pre-planted file/symlink can't be followed.
    let tmp = dir.join(format!(
        ".yoink-update-{}-{}.tmp",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));

    // Enforce the host/scheme allowlist across every redirect hop, too.
    let client = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::custom(|attempt| {
            if is_trusted_release_url(attempt.url()) {
                attempt.follow()
            } else {
                attempt.error(std::io::Error::other("untrusted redirect"))
            }
        }))
        .build()
        .map_err(|e| e.to_string())?;
    let resp = client
        .get(url)
        .header("User-Agent", "yoink-desktop")
        .send()
        .await
        .and_then(reqwest::Response::error_for_status)
        .map_err(|e| e.to_string())?;
    let total = resp.content_length().unwrap_or(0);

    {
        use std::io::Write;
        // create_new (O_EXCL) refuses to open through a pre-existing file/symlink.
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&tmp)
            .map_err(|e| e.to_string())?;
        let mut done: u64 = 0;
        let mut resp = resp;
        let mut last = 0.0f32;
        // Enter the "downloading" state immediately (also the only feedback when
        // the server sends no Content-Length).
        emit(tx, ctx, Evt::UpdateProgress(0.0));
        while let Some(chunk) = resp.chunk().await.map_err(|e| e.to_string())? {
            file.write_all(&chunk).map_err(|e| e.to_string())?;
            done += chunk.len() as u64;
            if total > 0 {
                let pct = done as f32 / total as f32;
                if pct - last >= 0.01 {
                    last = pct;
                    emit(tx, ctx, Evt::UpdateProgress(pct));
                }
            }
        }
        file.flush().map_err(|e| e.to_string())?;
    }

    // Verify the minisign signature BEFORE the binary is made executable, run,
    // or swapped in — a tampered or wrong-host download never gets that far.
    if let Err(e) = verify_update_signature(&tmp, signature) {
        let _ = std::fs::remove_file(&tmp);
        return Err(e);
    }

    // Windows ships an NSIS installer, not a drop-in binary: a running .exe is
    // locked and can't be swapped underneath itself, and the app is several files
    // (desktop + core + yt-dlp + ffmpeg). Launch the verified installer silently
    // and let it replace everything once this process exits; the installer
    // relaunches the app when it's done.
    #[cfg(target_os = "windows")]
    {
        let installer = tmp.with_extension("exe");
        std::fs::rename(&tmp, &installer).map_err(|e| {
            let _ = std::fs::remove_file(&tmp);
            e.to_string()
        })?;
        std::process::Command::new(&installer)
            .arg("/S") // NSIS silent install (per-user; no UAC prompt)
            .spawn()
            .map_err(|e| e.to_string())?;
        Ok(())
    }

    // Linux: the AppImage is a single file. Make it executable and swap it in
    // atomically beside the running read-only mount.
    #[cfg(not(target_os = "windows"))]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(0o755));
        install_over(&tmp, target).inspect_err(|_| {
            let _ = std::fs::remove_file(&tmp);
        })
    }
}

/// Replace `target` with the freshly downloaded `tmp` (same directory).
#[cfg(not(target_os = "windows"))]
fn install_over(tmp: &std::path::Path, target: &std::path::Path) -> Result<(), String> {
    // A rename within one directory is atomic; the running AppImage keeps its
    // mount, so swapping the file underneath is safe.
    std::fs::rename(tmp, target).map_err(|e| e.to_string())
}

/// True if semver `a` is greater than `b` (numeric, dot-separated).
fn is_newer(a: &str, b: &str) -> bool {
    let parse = |s: &str| -> Vec<u32> {
        s.split('.')
            .map(|x| x.trim().parse().unwrap_or(0))
            .collect()
    };
    let (a, b) = (parse(a), parse(b));
    for i in 0..a.len().max(b.len()) {
        let (x, y) = (
            a.get(i).copied().unwrap_or(0),
            b.get(i).copied().unwrap_or(0),
        );
        if x != y {
            return x > y;
        }
    }
    false
}

async fn load_whatsnew(since: String, tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let mut req = reqwest::Client::new().get(format!("{}/api/release-notes", http_base()));
    if !since.is_empty() {
        req = req.query(&[("since", since.as_str())]);
    }
    if let Ok(r) = req.send().await {
        if let Ok(v) = r.json::<Value>().await {
            let entries = v
                .get("entries")
                .and_then(Value::as_array)
                .map(|a| {
                    a.iter()
                        .filter_map(|e| {
                            Some((
                                e.get("version").and_then(Value::as_str)?.to_string(),
                                e.get("notes")
                                    .and_then(Value::as_str)
                                    .unwrap_or("")
                                    .to_string(),
                            ))
                        })
                        .collect()
                })
                .unwrap_or_default();
            emit(&tx, &ctx, Evt::WhatsNew(entries));
        }
    }
}

/// Clear the log file, then reload (so the view empties).
async fn clear_logs(tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let _ = reqwest::Client::new()
        .delete(format!("{}/api/logs", http_base()))
        .send()
        .await;
    load_logs(tx, ctx).await;
}

async fn load_logs(tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let res = reqwest::Client::new()
        .get(format!("{}/api/logs", http_base()))
        .send()
        .await;
    if let Ok(r) = res {
        if let Ok(v) = r.json::<Value>().await {
            emit(
                &tx,
                &ctx,
                Evt::Logs {
                    path: v
                        .get("path")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string(),
                    content: v
                        .get("content")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string(),
                },
            );
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

/// Resolve a queued URL's title in the background so the row shows the content
/// name instead of the raw link. Best-effort: on any failure the row keeps the URL.
async fn resolve_title(id: u64, url: String, tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let res = reqwest::Client::new()
        .post(format!("{}/api/info", http_base()))
        .json(&serde_json::json!({ "url": url }))
        .send()
        .await;
    if let Ok(r) = res {
        if r.status().is_success() {
            if let Ok(info) = r.json::<InfoResp>().await {
                let title = info
                    .video
                    .map(|v| v.title)
                    .or_else(|| info.playlist.map(|p| p.title))
                    .filter(|t| !t.trim().is_empty());
                if let Some(title) = title {
                    emit(&tx, &ctx, Evt::QueueTitle { id, title });
                }
            }
        }
    }
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

async fn download(
    req: DownloadReq,
    autotag: AutotagOpts,
    tx: std::sync::mpsc::Sender<Evt>,
    ctx: egui::Context,
) {
    if let Some(path) = run_ws_download(&req, &tx, &ctx).await {
        // Auto-tag an audio download from the catalogue (title/artist/album/cover,
        // + .nfo / music-folder relocation server-side), mirroring the CLI. A file
        // with no catalogue match is left untouched. Best-effort: a tagging hiccup
        // never fails the download.
        // Queue audio is tagged silently here; a manual (interactive) audio
        // download is tagged through the tag panel the UI opens on Done.
        if req.kind == "audio" && !autotag.interactive {
            autotag_file(&path, autotag.fetch_lyrics).await;
        }
        emit(&tx, &ctx, Evt::Done(path));
    }
}

/// Run the auto-tag cascade for a freshly downloaded audio file: identify the
/// best catalogue match, apply its tags, and (when enabled) fetch + embed lyrics.
/// The autotag source is read server-side; this only orchestrates the calls.
async fn autotag_file(path: &str, fetch_lyrics: bool) {
    let client = reqwest::Client::new();
    // 1. Identify: the server guesses artist/title from the filename and searches
    //    the configured catalogue, returning ranked candidates.
    let results: Option<Value> = match client
        .post(format!("{}/api/autotag/identify", http_base()))
        .json(&serde_json::json!({ "path": path }))
        .send()
        .await
    {
        Ok(r) => r.json().await.ok(),
        Err(_) => return,
    };
    let best = results
        .as_ref()
        .and_then(|v| v.get("results"))
        .and_then(Value::as_array)
        .and_then(|a| a.first());
    let Some(best) = best else { return }; // no match → leave the file untagged

    // 2. Apply the top candidate's tags (+ cover, .nfo, relocation server-side).
    let _ = client
        .post(format!("{}/api/autotag/apply", http_base()))
        .json(&serde_json::json!({
            "path": path,
            "title": best.get("title"),
            "artist": best.get("artist"),
            "album": best.get("album"),
            "year": best.get("year"),
            "genre": best.get("genre"),
            "track_number": best.get("track_number"),
            "cover_url": best.get("cover_url"),
        }))
        .send()
        .await;

    // 3. Lyrics (opt-in): fetch from LRCLIB and embed into the file.
    if fetch_lyrics {
        let title = best.get("title").and_then(Value::as_str).unwrap_or("");
        let artist = best.get("artist").and_then(Value::as_str).unwrap_or("");
        if !title.is_empty() {
            let _ = client
                .post(format!("{}/api/autotag/lyrics", http_base()))
                .json(&serde_json::json!({
                    "title": title,
                    "artist": artist,
                    "album": best.get("album"),
                    "path": path,
                }))
                .send()
                .await;
        }
    }
}

/// Parse a `{ "results": [TagCandidate] }` autotag response body.
async fn tag_results(res: reqwest::Result<reqwest::Response>) -> Vec<TagCandidate> {
    if let Ok(r) = res {
        if let Ok(v) = r.json::<Value>().await {
            if let Some(arr) = v.get("results").and_then(Value::as_array) {
                return arr
                    .iter()
                    .filter_map(|c| serde_json::from_value(c.clone()).ok())
                    .collect();
            }
        }
    }
    Vec::new()
}

/// Identify catalogue matches for a downloaded audio file (filename-based).
async fn identify_tags(path: &str) -> Vec<TagCandidate> {
    let res = reqwest::Client::new()
        .post(format!("{}/api/autotag/identify", http_base()))
        .json(&serde_json::json!({ "path": path }))
        .send()
        .await;
    tag_results(res).await
}

/// Manual catalogue search for the tag panel.
async fn search_tags(artist: &str, title: &str) -> Vec<TagCandidate> {
    let res = reqwest::Client::new()
        .post(format!("{}/api/autotag/search", http_base()))
        .json(&serde_json::json!({ "artist": artist, "title": title }))
        .send()
        .await;
    tag_results(res).await
}

/// Write the chosen tags (+ cover, + lyrics when asked) to the file.
async fn apply_tags(a: ApplyArgs, tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let client = reqwest::Client::new();
    let ok = client
        .post(format!("{}/api/autotag/apply", http_base()))
        .json(&serde_json::json!({
            "path": a.path,
            "title": a.title,
            "artist": a.artist,
            "album": a.album,
            "year": a.year,
            "genre": a.genre,
            "track_number": a.track_number,
            "cover_url": a.cover_url,
        }))
        .send()
        .await
        .map(|r| r.status().is_success())
        .unwrap_or(false);
    if a.embed_lyrics && !a.title.is_empty() {
        let _ = client
            .post(format!("{}/api/autotag/lyrics", http_base()))
            .json(&serde_json::json!({
                "title": a.title,
                "artist": a.artist,
                "album": a.album,
                "path": a.path,
            }))
            .send()
            .await;
    }
    emit(&tx, &ctx, Evt::AutotagApplied { ok });
}

/// Open the download WebSocket, stream `Progress` events, and return the final
/// filepath (emitting `DownloadErr` on failure). The caller decides what "done"
/// means — a plain download emits `Done`; a music import tags first.
async fn run_ws_download(
    req: &DownloadReq,
    tx: &std::sync::mpsc::Sender<Evt>,
    ctx: &egui::Context,
) -> Option<String> {
    let url = format!("ws://127.0.0.1:{}/api/ws/download", port());
    let (mut ws, _) = match tokio_tungstenite::connect_async(&url).await {
        Ok(s) => s,
        Err(e) => {
            emit(tx, ctx, Evt::DownloadErr(format!("ws connect failed: {e}")));
            return None;
        }
    };
    let payload = serde_json::to_string(req).unwrap_or_default();
    if let Err(e) = ws.send(Message::Text(payload)).await {
        emit(tx, ctx, Evt::DownloadErr(format!("ws send failed: {e}")));
        return None;
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
                tx,
                ctx,
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
                return Some(path);
            }
            Some("error") => {
                let msg = v
                    .get("message")
                    .and_then(Value::as_str)
                    .unwrap_or("download failed");
                emit(tx, ctx, Evt::DownloadErr(msg.to_string()));
                return None;
            }
            _ => {}
        }
    }
    // The socket closed (backend crashed/restarted, or a mid-download drop)
    // without a terminal `completed`/`error`. Surface it so the UI clears the
    // active download instead of wedging the whole queue forever.
    emit(tx, ctx, Evt::DownloadErr("connection closed".into()));
    None
}

async fn search(
    query: String,
    source: String,
    tx: std::sync::mpsc::Sender<Evt>,
    ctx: egui::Context,
) {
    #[derive(Deserialize)]
    struct Resp {
        #[serde(default)]
        results: Vec<SearchItem>,
    }
    let res = reqwest::Client::new()
        .get(format!("{}/api/search", http_base()))
        .query(&[("q", query.as_str()), ("source", source.as_str())])
        .send()
        .await;
    // Always emit (empty on failure), so the UI's search spinner never hangs.
    let items = match res {
        Ok(r) => r
            .json::<Resp>()
            .await
            .map(|r| r.results)
            .unwrap_or_default(),
        Err(_) => Vec::new(),
    };
    emit(&tx, &ctx, Evt::SearchResults { query, items });
}

async fn resolve_music(url: String, tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    emit(&tx, &ctx, Evt::Analyzing);
    let res = reqwest::Client::new()
        .post(format!("{}/api/music/resolve", http_base()))
        .json(&serde_json::json!({ "url": url }))
        .send()
        .await;
    match res {
        Ok(r) if r.status().is_success() => match r.json::<MusicInfo>().await {
            Ok(info) => emit(&tx, &ctx, Evt::Music(Box::new(info))),
            Err(e) => emit(
                &tx,
                &ctx,
                Evt::AnalyzeErr(format!("bad music response: {e}")),
            ),
        },
        Ok(r) => emit(
            &tx,
            &ctx,
            Evt::AnalyzeErr(format!("music resolve returned {}", r.status())),
        ),
        Err(e) => emit(
            &tx,
            &ctx,
            Evt::AnalyzeErr(format!("cannot reach backend: {e}")),
        ),
    }
}

/// Import one track: match it on YouTube, download the audio, then tag it with the
/// exact source metadata (title/artist/album/year/cover/ISRC).
async fn import_track(track: MusicTrack, tx: std::sync::mpsc::Sender<Evt>, ctx: egui::Context) {
    let client = reqwest::Client::new();
    // 1. Match on YouTube (spotDL-ported scorer, server-side).
    let matched = client
        .post(format!("{}/api/music/match", http_base()))
        .json(&track)
        .send()
        .await
        .ok();
    let matched: Option<Value> = match matched {
        Some(r) => r.json().await.ok(),
        None => None,
    };
    let yt = matched
        .as_ref()
        .and_then(|m| m.get("youtube_url"))
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty());
    let Some(yt) = yt else {
        return emit(&tx, &ctx, Evt::DownloadErr("no YouTube match".into()));
    };
    let isrc = matched
        .as_ref()
        .and_then(|m| m.get("isrc"))
        .and_then(Value::as_str)
        .map(str::to_string)
        .or_else(|| track.isrc.clone());

    // 2. Download the audio (default mp3).
    let req = DownloadReq {
        url: yt.to_string(),
        kind: "audio".into(),
        quality: None,
        container: "mp4".into(),
        audio_format: "mp3".into(),
        ..Default::default()
    };
    let Some(path) = run_ws_download(&req, &tx, &ctx).await else {
        return; // error already emitted
    };

    // 3. Tag with the exact source metadata.
    let _ = client
        .post(format!("{}/api/autotag/apply", http_base()))
        .json(&serde_json::json!({
            "path": path,
            "title": track.title,
            "artist": track.artists,
            "album": track.album,
            "year": track.year,
            "isrc": isrc,
            "cover_url": track.cover_url,
        }))
        .send()
        .await;
    emit(&tx, &ctx, Evt::Done(path));
}

#[cfg(test)]
mod update_sig_tests {
    use super::{verify_update_signature, UPDATE_PUBKEY};

    // The embedded key parses, and a wrong/garbage signature is rejected
    // (fail-closed). The format was validated out-of-band against a real Tauri
    // `latest.json` signature over the published AppImage (minisign-verify accepts
    // it and rejects a tampered file).
    #[test]
    fn pubkey_parses_and_bad_sig_rejected() {
        assert!(minisign_verify::PublicKey::from_base64(UPDATE_PUBKEY).is_ok());
        let f = std::env::temp_dir().join("yoink-sig-test.bin");
        std::fs::write(&f, b"x").unwrap();
        // Not base64 / not a signature → rejected, never a panic.
        assert!(verify_update_signature(&f, "not-a-signature").is_err());
        assert!(verify_update_signature(&f, "").is_err());
        let _ = std::fs::remove_file(&f);
    }
}
