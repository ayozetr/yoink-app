// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! The egui application: the tabbed shell and the download screen. This is the
//! native replacement for the React UI; it drives the same `yoink-core` backend
//! over the REST/WS contract (see [`crate::api`]).

use egui::RichText;

use crate::api::{
    is_music_url, Backend, Cmd, DownloadReq, Evt, HistoryEntry, MusicInfo, MusicTrack, SearchItem,
    Settings, VideoLite,
};
use crate::i18n::{tl, Lang};
use crate::theme;

#[derive(PartialEq, Clone, Copy)]
enum Tab {
    Inicio,
    Cola,
    Historial,
    Ajustes,
    Logs,
}

enum Preview {
    None,
    Video(VideoLite),
    Playlist { title: String, count: usize },
    Music(MusicInfo),
}

enum Status {
    Idle,
    Analyzing,
    Downloading,
    Done(String),
    Error(String),
}

/// Which download owns the single in-flight slot (the backend serves one at a
/// time, so the UI gates on this).
#[derive(Clone, Copy, PartialEq)]
enum ActiveDl {
    Inicio,
    Queue(u64),
}

enum QStatus {
    Pending,
    Downloading,
    Done,
    Error(String),
}

/// How the UI theme is chosen: follow the OS, or a fixed dark/light.
#[derive(Clone, Copy, PartialEq, Eq)]
enum ThemeMode {
    System,
    Dark,
    Light,
}

impl ThemeMode {
    fn as_str(self) -> &'static str {
        match self {
            ThemeMode::System => "system",
            ThemeMode::Dark => "dark",
            ThemeMode::Light => "light",
        }
    }
    fn from_str(s: &str) -> ThemeMode {
        match s {
            "dark" => ThemeMode::Dark,
            "light" => ThemeMode::Light,
            _ => ThemeMode::System,
        }
    }
}

/// Local UI preferences persisted outside the backend settings (the web keeps
/// these in `localStorage`): the theme choice and the language override.
#[derive(serde::Serialize, serde::Deserialize, Default)]
struct UiPrefs {
    #[serde(default)]
    theme: String,
    /// `None` = follow the OS language; otherwise a [`Lang::code`].
    #[serde(default)]
    lang: Option<String>,
}

/// Where UI prefs live (`<config>/yoink/ui.json`).
fn prefs_path() -> Option<std::path::PathBuf> {
    let base = std::env::var("XDG_CONFIG_HOME")
        .ok()
        .filter(|s| !s.is_empty())
        .or_else(|| std::env::var("HOME").ok().map(|h| format!("{h}/.config")))?;
    Some(std::path::PathBuf::from(base).join("yoink").join("ui.json"))
}

fn load_prefs() -> UiPrefs {
    prefs_path()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save_prefs(theme_mode: ThemeMode, lang_mode: Option<Lang>) {
    let prefs = UiPrefs {
        theme: theme_mode.as_str().to_string(),
        lang: lang_mode.map(|l| l.code().to_string()),
    };
    if let Some(path) = prefs_path() {
        if let Some(dir) = path.parent() {
            let _ = std::fs::create_dir_all(dir);
        }
        if let Ok(json) = serde_json::to_string_pretty(&prefs) {
            let _ = std::fs::write(path, json);
        }
    }
}

/// A saved format preset: a named bundle of the advanced selectors, applied to
/// the current media in one click. Local convenience state, persisted as JSON.
#[derive(Clone, serde::Serialize, serde::Deserialize)]
struct Preset {
    name: String,
    kind: String,
    quality: String,
    container: String,
    audio_format: String,
    bitrate: String,
    codec: String,
    #[serde(default)]
    embed_subs: bool,
    #[serde(default)]
    embed_chapters: bool,
}

/// Where presets live (`<config>/yoink/presets.json`).
fn presets_path() -> Option<std::path::PathBuf> {
    let base = std::env::var("XDG_CONFIG_HOME")
        .ok()
        .filter(|s| !s.is_empty())
        .or_else(|| std::env::var("HOME").ok().map(|h| format!("{h}/.config")))?;
    Some(
        std::path::PathBuf::from(base)
            .join("yoink")
            .join("presets.json"),
    )
}

/// Load saved presets (empty on any problem).
fn load_presets() -> Vec<Preset> {
    presets_path()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

/// Persist presets to disk (best-effort).
fn save_presets(presets: &[Preset]) {
    if let Some(path) = presets_path() {
        if let Some(dir) = path.parent() {
            let _ = std::fs::create_dir_all(dir);
        }
        if let Ok(json) = serde_json::to_string_pretty(presets) {
            let _ = std::fs::write(path, json);
        }
    }
}

/// What a queue item downloads: a plain URL (yt-dlp) or a resolved music track
/// (match → download → tag).
enum QSource {
    Url(String),
    Music(Box<MusicTrack>),
}

struct QueueItem {
    id: u64,
    label: String,
    kind: String,
    quality: String,
    container: String,
    audio: String,
    bitrate: String,
    source: QSource,
    status: QStatus,
    progress: f32,
}

pub struct App {
    backend: Backend,
    minter: crate::minter::Minter,
    dark: bool,
    theme_mode: ThemeMode,
    os_dark: Option<bool>,                 // last probed OS light/dark preference
    theme_probe: std::time::Instant,       // throttles re-probing the OS theme
    os_dark_tx: std::sync::mpsc::Sender<Option<bool>>, // background OS-theme probe result
    os_dark_rx: std::sync::mpsc::Receiver<Option<bool>>,
    os_probe_inflight: bool,               // a background OS-theme probe is running
    lang: Lang,                            // the resolved UI language
    lang_mode: Option<Lang>,               // None = follow the OS language
    template_custom: bool,                 // filename template: custom (free-text) vs a preset
    tab: Tab,
    url: String,
    kind: String,
    quality: String,
    container: String,
    audio_format: String,
    // Advanced options (single download).
    codec: String,   // any | h264 | h265 | vp9 | av1
    bitrate: String, // best | 320 | 256 | 192 | 128
    trim_start: String,
    trim_end: String,
    embed_subs: bool,
    subtitle_lang: String,
    embed_chapters: bool,
    source: String, // "youtube" | "soundcloud" for the search selector
    search_results: Vec<SearchItem>,
    search_pending: Option<std::time::Instant>,
    last_query: String,
    preview: Preview,
    status: Status,
    progress: f32,
    speed: Option<String>,
    eta: Option<String>,
    settings: Option<Settings>,
    settings_note: Option<String>,
    settings_scroll_to: Option<String>,
    settings_failed: bool, // the backend never answered the settings request
    active_section: String, // settings section currently in view (for the nav scrollspy)
    history: Vec<HistoryEntry>,
    history_loaded: bool,
    hist_query: String,
    logs_text: String,
    logs_path: String,
    logs_loaded: bool,
    active: Option<ActiveDl>,
    queue: Vec<QueueItem>,
    queue_url: String,
    next_qid: u64,
    queue_started: bool,
    q_kind: String,
    q_quality: String,
    q_container: String,
    q_audio: String,
    q_bitrate: String,
    advanced_open: bool,
    supported_open: bool,
    presets: Vec<Preset>,
    preset_naming: bool,
    preset_name: String,
    update_available: Option<String>,
    update_asset_url: Option<String>,
    update_signature: Option<String>,
    update_progress: Option<f32>,
    update_error: Option<String>,
    update_dismissed: bool,
    update_checking: bool, // a manual "check for updates" is in flight
    update_checked: bool,  // a check has completed (so we can show "up to date")
    startup_update_checked: bool, // the one-time startup check has been triggered
    whatsnew: Vec<(String, String)>,
    whatsnew_open: bool,
    terms_open: bool,
    licenses_open: bool,
    deeplink_rx: std::sync::mpsc::Receiver<String>,
    tray_rx: std::sync::mpsc::Receiver<crate::tray::TrayMsg>,
    shot: Option<(String, std::time::Instant)>, // (output path, started) for YOINK_SHOT
    focus_url: bool, // a pending Ctrl+L: focus the URL field next frame
}

/// The OS light/dark preference, or `None` if it can't be determined. Tries
/// egui's own `system_theme` first (set by the windowing layer on macOS/Windows),
/// then the XDG desktop portal (`dark-light`), which is what works on Wayland/KDE.
fn detect_os_dark(ctx: &egui::Context) -> Option<bool> {
    if let Some(t) = ctx.system_theme() {
        return Some(t == egui::Theme::Dark);
    }
    match dark_light::detect() {
        dark_light::Mode::Dark => Some(true),
        dark_light::Mode::Light => Some(false),
        dark_light::Mode::Default => None,
    }
}

impl App {
    pub fn new(
        cc: &eframe::CreationContext<'_>,
        pending: Option<String>,
        deeplink_rx: std::sync::mpsc::Receiver<String>,
        tray_rx: std::sync::mpsc::Receiver<crate::tray::TrayMsg>,
    ) -> App {
        // Default to following the OS; resolve the initial value from it (dark if
        // the system theme isn't known yet). The per-frame check in `ui` keeps it
        // in sync afterwards.
        let prefs = load_prefs();
        let theme_mode = if prefs.theme.is_empty() {
            ThemeMode::System
        } else {
            ThemeMode::from_str(&prefs.theme)
        };
        let lang_mode = prefs.lang.as_deref().and_then(crate::i18n::Lang::from_code);
        let os_dark = detect_os_dark(&cc.egui_ctx);
        let (os_dark_tx, os_dark_rx) = std::sync::mpsc::channel::<Option<bool>>();
        let dark = match theme_mode {
            ThemeMode::System => os_dark.unwrap_or(true),
            ThemeMode::Dark => true,
            ThemeMode::Light => false,
        };
        crate::fonts::install(&cc.egui_ctx);
        theme::apply(&cc.egui_ctx, dark);
        // The web UI renders at a more generous scale; match it so controls and
        // text feel as spacious (overridable via YOINK_ZOOM for tuning).
        let zoom = std::env::var("YOINK_ZOOM")
            .ok()
            .and_then(|z| z.parse().ok())
            .unwrap_or(1.2_f32);
        cc.egui_ctx.set_zoom_factor(zoom);
        // Enables egui::Image to load remote thumbnails (JPEG/PNG/WebP over http).
        egui_extras::install_image_loaders(&cc.egui_ctx);
        let mut app = App {
            backend: Backend::spawn(cc.egui_ctx.clone()),
            minter: crate::minter::Minter::new(crate::api::port()),
            dark,
            theme_mode,
            os_dark,
            theme_probe: std::time::Instant::now(),
            os_dark_tx,
            os_dark_rx,
            os_probe_inflight: false,
            lang: lang_mode.unwrap_or_else(crate::i18n::detect),
            lang_mode,
            template_custom: false,
            tab: Tab::Inicio,
            url: String::new(),
            kind: "video".into(),
            quality: "best".into(),
            container: "mp4".into(),
            audio_format: "mp3".into(),
            codec: "any".into(),
            bitrate: "best".into(),
            trim_start: String::new(),
            trim_end: String::new(),
            embed_subs: false,
            subtitle_lang: String::new(),
            embed_chapters: false,
            source: "youtube".into(),
            search_results: Vec::new(),
            search_pending: None,
            last_query: String::new(),
            preview: Preview::None,
            status: Status::Idle,
            progress: 0.0,
            speed: None,
            eta: None,
            settings: None,
            settings_note: None,
            settings_scroll_to: None,
            settings_failed: false,
            active_section: "sec.general".into(),
            history: Vec::new(),
            history_loaded: false,
            hist_query: String::new(),
            logs_text: String::new(),
            logs_path: String::new(),
            logs_loaded: false,
            active: None,
            queue: Vec::new(),
            queue_url: String::new(),
            next_qid: 0,
            queue_started: false,
            q_kind: "video".into(),
            q_quality: "best".into(),
            q_container: "mp4".into(),
            q_audio: "mp3".into(),
            q_bitrate: "best".into(),
            advanced_open: false,
            supported_open: false,
            presets: load_presets(),
            preset_naming: false,
            preset_name: String::new(),
            update_available: None,
            update_asset_url: None,
            update_signature: None,
            update_progress: None,
            update_error: None,
            update_dismissed: false,
            update_checking: false,
            update_checked: false,
            startup_update_checked: false,
            whatsnew: Vec::new(),
            whatsnew_open: false,
            terms_open: false,
            licenses_open: false,
            deeplink_rx,
            tray_rx,
            shot: std::env::var("YOINK_SHOT")
                .ok()
                .filter(|s| !s.is_empty())
                .map(|p| (p, std::time::Instant::now())),
            focus_url: false,
        };
        // A link the app was launched with (yoink://…) analyzes straight away.
        if let Some(url) = pending {
            app.url = url;
            app.analyze();
        }
        if std::env::var("YOINK_FAKE_UPDATE").is_ok() {
            app.update_available = Some("4.5.0".into());
            app.update_asset_url = Some("https://example.invalid/Yoink.AppImage".into());
            app.update_signature = Some("fake".into());
            if let Ok(p) = std::env::var("YOINK_FAKE_UPDATE_PROGRESS") {
                app.update_progress = p.parse().ok();
            }
        }
        // First launch after an update: fetch "what's new" since the last-seen version.
        let marker = whatsnew_marker();
        let last = marker
            .as_ref()
            .and_then(|m| std::fs::read_to_string(m).ok())
            .unwrap_or_default();
        let current = env!("CARGO_PKG_VERSION");
        if last.trim() != current {
            app.backend.send(Cmd::LoadWhatsNew {
                since: last.trim().to_string(),
            });
            if let Some(m) = &marker {
                if let Some(dir) = m.parent() {
                    let _ = std::fs::create_dir_all(dir);
                }
                let _ = std::fs::write(m, current);
            }
        }
        // Screenshot helpers (YOINK_SHOT): pick a tab / pre-analyze a URL to capture.
        if let Ok(t) = std::env::var("YOINK_SHOT_TAB") {
            app.tab = match t.as_str() {
                "cola" => Tab::Cola,
                "historial" => Tab::Historial,
                "ajustes" => Tab::Ajustes,
                "logs" => Tab::Logs,
                _ => Tab::Inicio,
            };
        }
        if std::env::var("YOINK_SHOT_LIGHT").is_ok() {
            app.theme_mode = ThemeMode::Light;
        }
        if let Ok(u) = std::env::var("YOINK_SHOT_URL") {
            if !u.is_empty() {
                app.url = u.clone();
                if is_url(&u) {
                    app.analyze();
                } else {
                    app.last_query = u.clone();
                    app.backend.send(Cmd::Search {
                        query: u,
                        source: app.source.clone(),
                    });
                }
            }
        }
        if std::env::var("YOINK_SHOT_ADV").is_ok() {
            app.advanced_open = true;
        }
        if std::env::var("YOINK_SHOT_PREVIEW").is_ok() {
            // Seed a fake video preview so the preview + advanced panel render
            // without hitting the network.
            app.preview = Preview::Video(VideoLite {
                title: "Big Buck Bunny — Official Blender Foundation Short Film".into(),
                thumbnail_url: None,
                uploader: Some("Blender Foundation".into()),
                duration_string: Some("9:56".into()),
                has_audio: true,
                is_vr: false,
                subtitle_langs: vec!["en".into(), "es".into()],
                has_chapters: true,
                formats: vec![crate::api::FmtLite {
                    resolution: Some("2160p".into()),
                    filesize: Some(734_003_200),
                }],
            });
            app.status = Status::Idle;
        }
        if std::env::var("YOINK_SHOT_SITES").is_ok() {
            app.supported_open = true;
        }
        if let Ok(sec) = std::env::var("YOINK_SHOT_SCROLL") {
            app.tab = Tab::Ajustes;
            app.settings_scroll_to = Some(sec);
        }
        if std::env::var("YOINK_SHOT_QUEUE").is_ok() {
            app.tab = Tab::Cola;
            let mk = |id, label: &str, kind: &str, st, pr| QueueItem {
                id,
                label: label.into(),
                kind: kind.into(),
                quality: "best".into(),
                container: "mp4".into(),
                audio: "mp3".into(),
                bitrate: "best".into(),
                source: QSource::Url("https://www.youtube.com/watch?v=x".into()),
                status: st,
                progress: pr,
            };
            app.queue = vec![
                mk(
                    1,
                    "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film",
                    "video",
                    QStatus::Downloading,
                    0.42,
                ),
                mk(2, "Never Gonna Give You Up", "audio", QStatus::Pending, 0.0),
                mk(
                    3,
                    "Together Forever (Official Video)",
                    "video",
                    QStatus::Done,
                    1.0,
                ),
            ];
        }
        if std::env::var("YOINK_SHOT_WHATSNEW").is_ok() {
            app.whatsnew = vec![(
                "v4.5.0".into(),
                "## Novedades de la cola\n- Cada elemento guarda su propio formato\n- Barras de progreso por descarga\n\nTambién se pulió el modal de webs soportadas y los ajustes.".into(),
            )];
            app.whatsnew_open = true;
        }
        app
    }

    fn drain_events(&mut self) {
        while let Ok(evt) = self.backend.rx.try_recv() {
            match evt {
                Evt::Settings(s) => {
                    self.minter.set_auto(s.po_token_mode == "auto");
                    // A loaded template that isn't one of the presets is a custom one.
                    self.template_custom = !TEMPLATE_PRESETS.iter().any(|(v, _)| *v == s.filename_template);
                    // Run the one-time startup update check now that we know the
                    // user's preference (honouring the "check for updates" setting).
                    if !self.startup_update_checked {
                        self.startup_update_checked = true;
                        if s.check_updates {
                            self.backend.send(Cmd::CheckUpdate);
                        }
                    }
                    self.settings_failed = false;
                    self.settings = Some(*s);
                }
                Evt::SettingsLoadFailed => self.settings_failed = true,
                Evt::SettingsSaved => self.settings_note = Some("Guardado".into()),
                Evt::UpdateAvailable {
                    version,
                    asset_url,
                    signature,
                } => {
                    self.update_available = Some(version);
                    self.update_asset_url = asset_url;
                    self.update_signature = signature;
                    self.update_checking = false;
                    self.update_checked = true;
                }
                Evt::UpToDate => {
                    self.update_checking = false;
                    self.update_checked = true;
                }
                Evt::UpdateProgress(pct) => self.update_progress = Some(pct),
                Evt::UpdateInstalled(path) => {
                    // The binary is swapped — relaunch it and exit this process.
                    self.minter.shutdown();
                    let _ = std::process::Command::new(&path).spawn();
                    std::process::exit(0);
                }
                Evt::UpdateError(e) => {
                    self.update_progress = None;
                    self.update_error = Some(e);
                }
                Evt::WhatsNew(entries) => {
                    if !entries.is_empty() {
                        self.whatsnew = entries;
                        // Don't pop it over a screenshot capture (unless forced).
                        self.whatsnew_open =
                            self.shot.is_none() || std::env::var("YOINK_SHOT_WHATSNEW").is_ok();
                    }
                }
                Evt::History(h) => {
                    self.history = h;
                    // Prefetched at startup — don't refetch when the tab opens.
                    self.history_loaded = true;
                }
                Evt::Logs { path, content } => {
                    self.logs_path = path;
                    self.logs_text = content;
                    self.logs_loaded = true;
                }
                Evt::Analyzing => self.status = Status::Analyzing,
                Evt::Info(v) => {
                    self.preview = Preview::Video(v);
                    self.status = Status::Idle;
                    self.search_results.clear();
                }
                Evt::SearchResults { query, items } => {
                    // Drop results for a stale query (a slower earlier request must
                    // not overwrite the current one).
                    if query == self.last_query {
                        self.search_results = items;
                    }
                }
                Evt::Playlist { title, count } => {
                    self.preview = Preview::Playlist { title, count };
                    self.status = Status::Idle;
                }
                Evt::Music(info) => {
                    self.preview = Preview::Music(*info);
                    self.status = Status::Idle;
                }
                Evt::AnalyzeErr(e) => {
                    self.preview = Preview::None;
                    self.status = Status::Error(e);
                }
                Evt::Progress {
                    percent,
                    speed,
                    eta,
                } => {
                    let frac = (percent / 100.0).clamp(0.0, 1.0);
                    match self.active {
                        Some(ActiveDl::Queue(id)) => {
                            if let Some(it) = self.queue.iter_mut().find(|i| i.id == id) {
                                it.progress = frac;
                            }
                        }
                        _ => {
                            self.status = Status::Downloading;
                            self.progress = frac;
                            self.speed = speed;
                            self.eta = eta;
                        }
                    }
                }
                Evt::Done(path) => {
                    if self.settings.as_ref().is_some_and(|s| s.notify_on_complete) {
                        notify_done(tl(self.lang, "inicio.downloaded"), &path);
                    }
                    match self.active.take() {
                        Some(ActiveDl::Queue(id)) => {
                            if let Some(it) = self.queue.iter_mut().find(|i| i.id == id) {
                                it.progress = 1.0;
                                it.status = QStatus::Done;
                            }
                        }
                        _ => {
                            self.progress = 1.0;
                            self.status = Status::Done(path);
                        }
                    }
                }
                Evt::DownloadErr(e) => match self.active.take() {
                    Some(ActiveDl::Queue(id)) => {
                        if let Some(it) = self.queue.iter_mut().find(|i| i.id == id) {
                            it.status = QStatus::Error(e);
                        }
                    }
                    _ => self.status = Status::Error(e),
                },
            }
        }
    }

    /// Start the next queued item when the queue is running and nothing else is.
    fn pump_queue(&mut self) {
        if self.active.is_some() || !self.queue_started {
            return;
        }
        let Some(it) = self
            .queue
            .iter_mut()
            .find(|i| matches!(i.status, QStatus::Pending))
        else {
            return;
        };
        it.status = QStatus::Downloading;
        it.progress = 0.0;
        let id = it.id;
        self.active = Some(ActiveDl::Queue(id));
        match &it.source {
            QSource::Url(url) => {
                let kind = it.kind.clone();
                let is_audio = kind == "audio";
                self.backend.send(Cmd::Download(DownloadReq {
                    url: url.clone(),
                    quality: (!is_audio).then(|| it.quality.clone()),
                    kind,
                    container: it.container.clone(),
                    audio_format: it.audio.clone(),
                    audio_bitrate: (is_audio && it.bitrate != "best")
                        .then(|| it.bitrate.clone()),
                    ..Default::default()
                }));
            }
            QSource::Music(track) => {
                self.backend.send(Cmd::ImportTrack(track.clone()));
            }
        }
    }

    fn queue_add(&mut self) {
        let url = self.queue_url.trim().to_string();
        if url.is_empty() {
            return;
        }
        self.queue.push(QueueItem {
            id: self.next_qid,
            label: url.clone(),
            kind: self.q_kind.clone(),
            quality: self.q_quality.clone(),
            container: self.q_container.clone(),
            audio: self.q_audio.clone(),
            bitrate: self.q_bitrate.clone(),
            source: QSource::Url(url),
            status: QStatus::Pending,
            progress: 0.0,
        });
        self.next_qid += 1;
        self.queue_url.clear();
    }

    /// Enqueue every track of a resolved music import (match → download → tag).
    fn enqueue_music(&mut self, info: &MusicInfo) {
        for t in &info.tracks {
            self.queue.push(QueueItem {
                id: self.next_qid,
                label: format!("{} — {}", t.artists, t.title),
                kind: "music".into(),
                quality: "best".into(),
                container: "mp4".into(),
                audio: "mp3".into(),
                bitrate: "best".into(),
                source: QSource::Music(Box::new(t.clone())),
                status: QStatus::Pending,
                progress: 0.0,
            });
            self.next_qid += 1;
        }
        self.queue_started = true; // music import starts immediately
    }

    fn analyze(&mut self) {
        let url = self.url.trim().to_string();
        if url.is_empty() {
            return;
        }
        self.preview = Preview::None;
        self.status = Status::Analyzing;
        self.search_results.clear();
        self.search_pending = None;
        if is_music_url(&url) {
            self.backend.send(Cmd::ResolveMusic(url));
        } else {
            self.backend.send(Cmd::Analyze(url));
        }
    }

    /// Analyze a picked search result.
    fn pick(&mut self, url: String) {
        self.url = url;
        self.analyze();
    }

    fn start_download(&mut self) {
        if self.active.is_some() {
            return; // one download at a time
        }
        self.active = Some(ActiveDl::Inicio);
        self.progress = 0.0;
        self.speed = None;
        self.eta = None;
        self.status = Status::Downloading;
        let video = self.kind == "video";
        self.backend.send(Cmd::Download(DownloadReq {
            url: self.url.trim().to_string(),
            kind: self.kind.clone(),
            quality: video.then(|| self.quality.clone()),
            container: self.container.clone(),
            audio_format: self.audio_format.clone(),
            video_codec: (video && self.codec != "any").then(|| self.codec.clone()),
            audio_bitrate: (!video && self.bitrate != "best").then(|| self.bitrate.clone()),
            embed_subs: video && self.embed_subs,
            subtitle_lang: (video && self.embed_subs && !self.subtitle_lang.is_empty())
                .then(|| self.subtitle_lang.clone()),
            embed_chapters: video && self.embed_chapters,
            trim_start: parse_timecode(&self.trim_start),
            trim_end: parse_timecode(&self.trim_end),
        }));
    }
}

/// The shared frame for a custom modal panel (surface fill, rounded, bordered,
/// with a soft drop shadow).
fn modal_frame(p: theme::Palette) -> egui::Frame {
    egui::Frame::new()
        .fill(p.surface)
        .corner_radius(16)
        .stroke(egui::Stroke::new(1.0, p.line))
        .shadow(egui::epaint::Shadow {
            offset: [0, 12],
            blur: 48,
            spread: 0,
            color: egui::Color32::from_black_alpha(140),
        })
        .inner_margin(egui::Margin::same(22))
}

/// A modal close button (an X that lights up on hover). Returns its response.
fn close_button(ui: &mut egui::Ui, p: theme::Palette) -> egui::Response {
    let (rect, resp) = ui.allocate_exact_size(egui::vec2(30.0, 30.0), egui::Sense::click());
    let hov = resp.hovered();
    if hov {
        ui.painter().rect_filled(rect, 8.0, p.surface_hi);
        ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
    }
    let col = if hov { p.fg } else { p.fg_dim };
    let irect = egui::Rect::from_center_size(rect.center(), egui::vec2(16.0, 16.0));
    crate::icons::img("x", 16.0, col).paint_at(ui, irect);
    resp
}

/// A small square icon button (26×26) that lights up on hover. Returns true when
/// clicked. Used for the queue row's remove/reorder controls.
fn icon_btn(ui: &mut egui::Ui, p: theme::Palette, icon: &str) -> bool {
    let (rect, resp) = ui.allocate_exact_size(egui::vec2(26.0, 26.0), egui::Sense::click());
    let hov = resp.hovered();
    if hov {
        ui.painter().rect_filled(rect, 7.0, p.surface_hi);
        ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
    }
    let col = if hov { p.fg } else { p.fg_dim };
    let ir = egui::Rect::from_center_size(rect.center(), egui::vec2(14.0, 14.0));
    crate::icons::img(icon, 14.0, col).paint_at(ui, ir);
    resp.clicked()
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum WinBtn {
    Minimize,
    Maximize,
    Close,
}

/// A custom window-control button (minimize / maximize / close). On hover the
/// glyph lights up instead of drawing a background: brighter for minimize and
/// maximize, red for close. The glyphs are drawn directly so they stay crisp.
fn win_btn(ui: &mut egui::Ui, p: theme::Palette, kind: WinBtn) -> egui::Response {
    let (rect, resp) = ui.allocate_exact_size(egui::vec2(44.0, 34.0), egui::Sense::click());
    let hov = resp.hovered();
    if hov {
        ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
    }
    let col = if hov {
        if kind == WinBtn::Close {
            egui::Color32::from_rgb(237, 80, 80)
        } else {
            // Full-contrast foreground (works in both light and dark themes).
            p.fg
        }
    } else {
        p.fg_dim
    };
    let c = rect.center();
    let painter = ui.painter();
    let stroke = egui::Stroke::new(1.3, col);
    let h = 5.0; // half-extent of each glyph
    match kind {
        WinBtn::Minimize => {
            painter.line_segment([egui::pos2(c.x - h, c.y), egui::pos2(c.x + h, c.y)], stroke);
        }
        WinBtn::Maximize => {
            let r = egui::Rect::from_center_size(c, egui::vec2(h * 2.0, h * 2.0));
            painter.rect_stroke(r, 1.0, stroke, egui::StrokeKind::Inside);
        }
        WinBtn::Close => {
            painter.line_segment(
                [egui::pos2(c.x - h, c.y - h), egui::pos2(c.x + h, c.y + h)],
                stroke,
            );
            painter.line_segment(
                [egui::pos2(c.x - h, c.y + h), egui::pos2(c.x + h, c.y - h)],
                stroke,
            );
        }
    }
    resp
}

/// Edge/corner resize handles for the borderless window — thin interactive strips
/// in a foreground layer that start a compositor resize on drag (elsewhere the
/// pointer falls through to the UI below).
fn resize_handles(ctx: &egui::Context) {
    use egui::{CursorIcon as Cur, ResizeDirection as Dir};
    let r = ctx.content_rect();
    let b = 6.0;
    let rect =
        |x0: f32, y0: f32, x1: f32, y1: f32| egui::Rect::from_min_max(egui::pos2(x0, y0), egui::pos2(x1, y1));
    let handles = [
        // Edges first, then corners (corners are added later so they win overlap).
        ("rz_n", rect(r.left() + b, r.top(), r.right() - b, r.top() + b), Dir::North, Cur::ResizeVertical),
        ("rz_s", rect(r.left() + b, r.bottom() - b, r.right() - b, r.bottom()), Dir::South, Cur::ResizeVertical),
        ("rz_w", rect(r.left(), r.top() + b, r.left() + b, r.bottom() - b), Dir::West, Cur::ResizeHorizontal),
        ("rz_e", rect(r.right() - b, r.top() + b, r.right(), r.bottom() - b), Dir::East, Cur::ResizeHorizontal),
        ("rz_nw", rect(r.left(), r.top(), r.left() + b, r.top() + b), Dir::NorthWest, Cur::ResizeNwSe),
        ("rz_ne", rect(r.right() - b, r.top(), r.right(), r.top() + b), Dir::NorthEast, Cur::ResizeNeSw),
        ("rz_sw", rect(r.left(), r.bottom() - b, r.left() + b, r.bottom()), Dir::SouthWest, Cur::ResizeNeSw),
        ("rz_se", rect(r.right() - b, r.bottom() - b, r.right(), r.bottom()), Dir::SouthEast, Cur::ResizeNwSe),
    ];
    egui::Area::new(egui::Id::unique("resize-handles"))
        .order(egui::Order::Foreground)
        .fixed_pos(r.min)
        .show(ctx, |ui| {
            for (id, hr, dir, cur) in handles {
                let resp = ui.interact(hr, egui::Id::unique(id), egui::Sense::drag());
                if resp.hovered() {
                    ui.ctx().set_cursor_icon(cur);
                }
                if resp.drag_started() {
                    ui.ctx().send_viewport_cmd(egui::ViewportCommand::BeginResize(dir));
                }
            }
        });
}

/// Dim the app behind a modal with a *rounded* overlay, painted on a layer above
/// the UI but below the modal. A modal's own backdrop is a full rectangle that
/// would paint over (and square off) the window's transparent rounded corners,
/// so modals set their backdrop transparent and call this instead.
fn rounded_backdrop(ctx: &egui::Context) {
    ctx.layer_painter(egui::LayerId::new(
        egui::Order::Middle,
        egui::Id::unique("modal-backdrop"),
    ))
    .rect_filled(
        ctx.content_rect(),
        WINDOW_RADIUS,
        egui::Color32::from_black_alpha(170),
    );
}

/// Open a URL in the user's default browser (fire-and-forget).
fn open_url(url: &str) {
    #[cfg(target_os = "linux")]
    let _ = std::process::Command::new("xdg-open").arg(url).spawn();
    #[cfg(target_os = "macos")]
    let _ = std::process::Command::new("open").arg(url).spawn();
    #[cfg(target_os = "windows")]
    let _ = std::process::Command::new("cmd")
        .args(["/C", "start", "", url])
        .spawn();
}

/// Max width of the centered content container (header + body share it), so the
/// brand, tabs and content all line up — the web UI's `max-w` container.
const CONTENT_W: f32 = 860.0;

/// Width of the Settings right rail ("on this page" index) panel.
const SETTINGS_RAIL_W: f32 = 210.0;

/// The manually-verified sites shown in the "supported sites" dialog
/// (slug for the bundled logo, display name, homepage).
const SUPPORTED_SITES: &[(&str, &str, &str)] = &[
    ("youtube", "YouTube", "https://youtube.com"),
    ("dailymotion", "Dailymotion", "https://dailymotion.com"),
    ("tiktok", "TikTok", "https://tiktok.com"),
    ("facebook", "Facebook", "https://facebook.com"),
    ("instagram", "Instagram", "https://instagram.com"),
    ("threads", "Threads", "https://threads.com"),
    ("x", "X (Twitter)", "https://x.com"),
    ("reddit", "Reddit", "https://reddit.com"),
    ("bluesky", "Bluesky", "https://bsky.app"),
    ("pinterest", "Pinterest", "https://pinterest.com"),
    ("vk", "VK", "https://vk.com"),
    ("vimeo", "Vimeo", "https://vimeo.com"),
    ("twitch", "Twitch", "https://twitch.tv"),
    ("kick", "Kick", "https://kick.com"),
    ("medal", "Medal", "https://medal.tv"),
    ("youtubemusic", "YouTube Music", "https://music.youtube.com"),
    ("spotify", "Spotify", "https://spotify.com"),
    ("deezer", "Deezer", "https://deezer.com"),
    ("applemusic", "Apple Music", "https://music.apple.com"),
    ("tidal", "Tidal", "https://tidal.com"),
    ("amazonmusic", "Amazon Music", "https://music.amazon.com"),
    ("soundcloud", "SoundCloud", "https://soundcloud.com"),
    ("bandlab", "BandLab", "https://bandlab.com"),
    ("bandcamp", "Bandcamp", "https://bandcamp.com"),
];

/// A friendly source label for a queue item (the platform for a URL, else music).
fn queue_source(it: &QueueItem, lang: Lang) -> String {
    match &it.source {
        QSource::Music(_) => tl(lang, "kind.audio").to_string(),
        QSource::Url(u) => {
            let host = u
                .split("://")
                .nth(1)
                .unwrap_or(u)
                .split('/')
                .next()
                .unwrap_or("")
                .trim_start_matches("www.");
            let key = host.split('.').next().unwrap_or(host);
            match key {
                "youtube" | "youtu" => "YouTube".to_string(),
                "soundcloud" => "SoundCloud".to_string(),
                "music" => "YouTube Music".to_string(),
                "" => cap_first(&it.kind),
                other => cap_first(other),
            }
        }
    }
}

/// Capitalise the first letter ("spotify" -> "Spotify").
fn cap_first(s: &str) -> String {
    let mut c = s.chars();
    match c.next() {
        Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
        None => String::new(),
    }
}

/// Format a millisecond duration as "m:ss".
fn fmt_ms(ms: i64) -> String {
    let total = ms / 1000;
    format!("{}:{:02}", total / 60, total % 60)
}

/// Parse a "m:ss" / "h:mm:ss" / plain-seconds timecode into seconds.
fn parse_timecode(s: &str) -> Option<f64> {
    let s = s.trim();
    if s.is_empty() {
        return None;
    }
    let mut secs = 0.0;
    for part in s.split(':') {
        secs = secs * 60.0 + part.trim().parse::<f64>().ok()?;
    }
    Some(secs)
}

/// Corner radius of the (borderless, transparent) window.
const WINDOW_RADIUS: f32 = 11.0;

impl eframe::App for App {
    // Transparent framebuffer so the window corners we don't paint stay clear.
    fn clear_color(&self, _visuals: &egui::Visuals) -> [f32; 4] {
        [0.0, 0.0, 0.0, 0.0]
    }

    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        // Poll a little even when idle, so deep links handed over by another launch
        // are picked up promptly (and progress bars stay smooth).
        ctx.request_repaint_after(std::time::Duration::from_millis(400));

        // Tray menu clicks.
        while let Ok(msg) = self.tray_rx.try_recv() {
            match msg {
                crate::tray::TrayMsg::Show => {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Visible(true));
                    ctx.send_viewport_cmd(egui::ViewportCommand::Focus);
                }
                crate::tray::TrayMsg::Quit => {
                    self.minter.shutdown();
                    std::process::exit(0);
                }
            }
        }
        // Close-to-tray when the setting is on: hide instead of quitting.
        if ctx.input(|i| i.viewport().close_requested())
            && self
                .settings
                .as_ref()
                .map(|s| s.minimize_to_tray)
                .unwrap_or(false)
        {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            ctx.send_viewport_cmd(egui::ViewportCommand::Visible(false));
        }

        self.drain_events();
        // A yoink:// link handed over by another launch: analyze it and raise.
        while let Ok(url) = self.deeplink_rx.try_recv() {
            self.url = url;
            self.tab = Tab::Inicio;
            self.analyze();
            ctx.send_viewport_cmd(egui::ViewportCommand::Focus);
        }
        self.pump_queue();

        // Keyboard shortcuts (documented in Ajustes → Atajos). COMMAND is Ctrl on
        // Linux/Windows, ⌘ on macOS.
        let sc_focus = egui::KeyboardShortcut::new(egui::Modifiers::COMMAND, egui::Key::L);
        let sc_settings = egui::KeyboardShortcut::new(egui::Modifiers::COMMAND, egui::Key::Comma);
        if ctx.input_mut(|i| i.consume_shortcut(&sc_focus)) {
            self.tab = Tab::Inicio;
            self.focus_url = true;
        }
        if ctx.input_mut(|i| i.consume_shortcut(&sc_settings)) {
            self.tab = if self.tab == Tab::Ajustes {
                Tab::Inicio
            } else {
                Tab::Ajustes
            };
        }

        // Resolve the effective theme (System follows the OS) and re-apply on change.
        if self.theme_mode == ThemeMode::System {
            // winit's system_theme is cheap and on-thread; use it when available.
            if let Some(t) = ctx.system_theme() {
                self.os_dark = Some(t == egui::Theme::Dark);
            } else {
                // Otherwise probe the XDG portal — but OFF the UI thread (the DBus
                // call can block). Poll the last result, and re-probe every ~2s.
                while let Ok(v) = self.os_dark_rx.try_recv() {
                    self.os_dark = v;
                    self.os_probe_inflight = false;
                }
                if !self.os_probe_inflight && self.theme_probe.elapsed().as_secs_f32() > 2.0 {
                    self.os_probe_inflight = true;
                    self.theme_probe = std::time::Instant::now();
                    let tx = self.os_dark_tx.clone();
                    let ctx2 = ctx.clone();
                    std::thread::spawn(move || {
                        let v = match dark_light::detect() {
                            dark_light::Mode::Dark => Some(true),
                            dark_light::Mode::Light => Some(false),
                            dark_light::Mode::Default => None,
                        };
                        let _ = tx.send(v);
                        ctx2.request_repaint();
                    });
                }
            }
        }
        let want_dark = match self.theme_mode {
            ThemeMode::System => self.os_dark.unwrap_or(self.dark),
            ThemeMode::Dark => true,
            ThemeMode::Light => false,
        };
        if want_dark != self.dark {
            self.dark = want_dark;
            theme::apply(&ctx, want_dark);
        }

        // System language follows the OS locale live.
        if self.lang_mode.is_none() {
            let detected = crate::i18n::detect();
            if detected != self.lang {
                self.lang = detected;
            }
        }

        // Debounced search: fire once the typed query settles.
        if let Some(at) = self.search_pending {
            if at.elapsed().as_millis() > 350 {
                self.search_pending = None;
                let q = self.url.trim().to_string();
                if !q.is_empty() && !is_url(&q) {
                    self.last_query = q.clone();
                    self.backend.send(Cmd::Search {
                        query: q,
                        source: self.source.clone(),
                    });
                }
            }
        }
        // Lazy-load the history the first time its tab is opened.
        if self.tab == Tab::Historial && !self.history_loaded {
            self.history_loaded = true;
            self.backend.send(Cmd::LoadHistory);
        }
        if self.tab == Tab::Logs && !self.logs_loaded {
            self.logs_loaded = true;
            self.backend.send(Cmd::LoadLogs);
        }
        let p = theme::palette(self.dark);
        let lang = self.lang;

        // The window is borderless and transparent: paint a single rounded
        // background behind everything, and keep every panel's fill transparent,
        // so the four corners outside this rounded rect stay clear — rounded
        // window corners that we control, consistent across platforms.
        ui.painter().rect_filled(
            ctx.content_rect(),
            WINDOW_RADIUS,
            p.canvas,
        );

        // Our own title bar (native decoration is off): a flat AMOLED strip with
        // the window controls on the right. The empty area drags the window; a
        // double-click toggles maximize. No right margin, so the close button's
        // hover fill reaches the window edge.
        egui::Panel::top("titlebar")
            .show_separator_line(false)
            .exact_size(34.0)
            .frame(egui::Frame::new().fill(egui::Color32::TRANSPARENT).inner_margin(egui::Margin {
                left: 12,
                right: 0,
                top: 0,
                bottom: 0,
            }))
            .show(ui, |ui| {
                let bar = ui.max_rect();
                let drag = ui.interact(
                    bar,
                    egui::Id::unique("titlebar_drag"),
                    egui::Sense::click_and_drag(),
                );
                if drag.double_clicked() {
                    let maxed = ui.input(|i| i.viewport().maximized).unwrap_or(false);
                    ctx.send_viewport_cmd(egui::ViewportCommand::Maximized(!maxed));
                } else if drag.drag_started_by(egui::PointerButton::Primary) {
                    ctx.send_viewport_cmd(egui::ViewportCommand::StartDrag);
                }
                // Just the window controls on the right — no icon or wordmark here
                // (the brand sits right below); the rest of the strip drags.
                ui.horizontal_centered(|ui| {
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if win_btn(ui, p, WinBtn::Close).clicked() {
                            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                        }
                        if win_btn(ui, p, WinBtn::Maximize).clicked() {
                            let maxed = ui.input(|i| i.viewport().maximized).unwrap_or(false);
                            ctx.send_viewport_cmd(egui::ViewportCommand::Maximized(!maxed));
                        }
                        if win_btn(ui, p, WinBtn::Minimize).clicked() {
                            ctx.send_viewport_cmd(egui::ViewportCommand::Minimized(true));
                        }
                    });
                });
            });

        egui::Panel::top("topbar")
            .show_separator_line(false)
            .frame(
                // Same AMOLED canvas as the body — a seamless header, no gray band
                // or dividing line (matches the flat web UI).
                egui::Frame::new()
                    .fill(egui::Color32::TRANSPARENT)
                    .inner_margin(egui::Margin {
                        left: 20,
                        right: 20,
                        top: 12,
                        bottom: 10,
                    }),
            )
            .show(ui, |ui| {
                let avail = ui.available_width();
                let pad = ((avail - CONTENT_W.min(avail)) / 2.0).max(0.0);
                ui.horizontal(|ui| {
                    ui.add_space(pad);
                    ui.vertical(|ui| {
                        // Brand: the real Yoink logo (the gradient tile with the
                        // music-note + play mark, the same image the web UI and the
                        // title bar use) + the Gloock wordmark.
                        ui.horizontal(|ui| {
                            ui.add(
                                egui::Image::from_bytes(
                                    "bytes://brand-logo",
                                    include_bytes!("../assets/icon.png") as &[u8],
                                )
                                .fit_to_exact_size(egui::vec2(28.0, 28.0))
                                .corner_radius(8),
                            );
                            ui.add_space(9.0);
                            ui.label(
                                RichText::new("Yoink")
                                    .size(20.0)
                                    .family(crate::fonts::display())
                                    .color(p.fg),
                            );
                        });
                        ui.add_space(8.0);
                        // Pill tabs with icons (compact).
                        ui.horizontal(|ui| {
                            ui.spacing_mut().button_padding = egui::vec2(9.0, 5.0);
                            ui.spacing_mut().item_spacing.x = 5.0;
                            for (tab, key, ic) in [
                                (Tab::Inicio, "tab.inicio", "home"),
                                (Tab::Cola, "tab.cola", "queue"),
                                (Tab::Historial, "tab.historial", "history"),
                                (Tab::Ajustes, "tab.ajustes", "settings"),
                                (Tab::Logs, "tab.logs", "logs"),
                            ] {
                                let active = self.tab == tab;
                                let (fg, fill) = if active {
                                    (p.accent_fg, p.accent)
                                } else {
                                    (p.fg_dim, egui::Color32::TRANSPARENT)
                                };
                                // The Queue tab shows a live item count, like the web.
                                let text = if tab == Tab::Cola && !self.queue.is_empty() {
                                    format!("{} · {}", tl(lang, key), self.queue.len())
                                } else {
                                    tl(lang, key).to_string()
                                };
                                let btn = egui::Button::image_and_text(
                                    crate::icons::img(ic, 14.0, fg),
                                    RichText::new(text).size(13.0).color(fg),
                                )
                                .fill(fill)
                                .corner_radius(7);
                                if ui.add(btn).clicked() {
                                    self.tab = tab;
                                }
                            }
                        });
                    });
                });
            });

        // Update banner.
        let show_update = self.update_available.is_some()
            && !self.update_dismissed
            && self
                .settings
                .as_ref()
                .map(|s| s.check_updates)
                .unwrap_or(true);
        if show_update {
            let version = self.update_available.clone().unwrap_or_default();
            egui::Panel::top("update")
                .show_separator_line(false)
                .frame(
                    egui::Frame::new()
                        .fill(p.accent.gamma_multiply(0.18))
                        .inner_margin(egui::Margin::symmetric(16, 8)),
                )
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        crate::icons::show(ui, "download", 15.0, p.accent);
                        ui.add_space(6.0);
                        // While downloading, show progress; after a failure, show
                        // the error. Otherwise the "new version" message.
                        if let Some(pct) = self.update_progress {
                            ui.label(
                                RichText::new(format!(
                                    "{} {}%",
                                    tl(lang, "update.downloading"),
                                    (pct * 100.0) as u32
                                ))
                                .color(p.fg),
                            );
                            ui.add_space(10.0);
                            ui.add(
                                egui::ProgressBar::new(pct)
                                    .desired_width(160.0)
                                    .desired_height(6.0)
                                    .corner_radius(3),
                            );
                        } else if self.update_error.is_some() {
                            ui.label(
                                RichText::new(tl(lang, "update.failed")).color(p.fg),
                            );
                        } else {
                            ui.label(
                                RichText::new(format!(
                                    "{} {version}",
                                    tl(lang, "update.available")
                                ))
                                .color(p.fg),
                            );
                        }

                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if self.update_progress.is_some() {
                                // Mid-download: no controls, just the bar.
                                return;
                            }
                            if ui
                                .add(
                                    egui::Button::image(crate::icons::img("x", 14.0, p.fg_dim))
                                        .frame(false),
                                )
                                .clicked()
                            {
                                self.update_dismissed = true;
                            }
                            ui.add_space(8.0);
                            // In-place update when we can replace the binary (an
                            // AppImage or the Windows .exe) and the release has a
                            // matching asset; otherwise fall back to the releases
                            // page. A prior failure also falls back.
                            let can_self_update = self.update_error.is_none()
                                && crate::api::self_update_target().is_some()
                                && self.update_asset_url.is_some()
                                && self.update_signature.is_some();
                            let label = if can_self_update {
                                tl(lang, "update.install")
                            } else {
                                tl(lang, "update.view")
                            };
                            if ui
                                .add(
                                    egui::Button::new(RichText::new(label).color(p.accent_fg))
                                        .fill(p.accent)
                                        .corner_radius(8),
                                )
                                .clicked()
                            {
                                if can_self_update {
                                    self.update_progress = Some(0.0);
                                    self.backend.send(Cmd::SelfUpdate {
                                        url: self.update_asset_url.clone().unwrap_or_default(),
                                        signature: self
                                            .update_signature
                                            .clone()
                                            .unwrap_or_default(),
                                    });
                                } else {
                                    open_url(
                                        "https://github.com/ayozetr/yoink-app/releases/latest",
                                    );
                                }
                            }
                        });
                    });
                });
        }

        // Settings "on this page" nav (sticky right column).
        if self.tab == Tab::Ajustes {
            egui::Panel::right("settings-nav")
                .resizable(false)
                .show_separator_line(false)
                .exact_size(SETTINGS_RAIL_W)
                .frame(
                    egui::Frame::new()
                        .fill(egui::Color32::TRANSPARENT)
                        .inner_margin(egui::Margin::symmetric(20, 24)),
                )
                .show(ui, |ui| {
                    // A compact "on this page" index with a hairline on its left
                    // that spans only the list (header + items), like the web rail.
                    let full_w = ui.available_width();
                    let origin = ui.cursor().min;
                    let line_x = origin.x;
                    let text_x = origin.x + 14.0;
                    let mut y = origin.y;

                    ui.painter().text(
                        egui::pos2(text_x, y),
                        egui::Align2::LEFT_TOP,
                        tl(lang, "set.onpage"),
                        egui::FontId::proportional(10.5),
                        p.fg_dim.gamma_multiply(0.75),
                    );
                    y += 22.0;

                    let item_h = 23.0;
                    for (key, label) in [
                        // Same sections, in the same order, as the web's rail.
                        ("sec.general", "set.general"),
                        ("sec.downloads", "set.downloads"),
                        ("sec.quality", "set.quality"),
                        ("sec.options", "set.options"),
                        ("sec.sponsorblock", "set.sponsorblock"),
                        ("sec.network", "set.network"),
                        ("sec.shortcuts", "set.shortcuts"),
                        ("sec.extension", "set.extension"),
                        ("sec.about", "set.about"),
                    ] {
                        let rect = egui::Rect::from_min_size(
                            egui::pos2(line_x, y),
                            egui::vec2(full_w, item_h),
                        );
                        let resp = ui.interact(rect, egui::Id::unique(key), egui::Sense::click());
                        let hov = resp.hovered();
                        let active = self.active_section == key;
                        let col = if active {
                            p.accent
                        } else if hov {
                            p.fg
                        } else {
                            p.fg_dim
                        };
                        if hov {
                            ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
                        }
                        ui.painter().text(
                            egui::pos2(text_x, rect.center().y),
                            egui::Align2::LEFT_CENTER,
                            tl(lang, label),
                            egui::FontId::proportional(13.0),
                            col,
                        );
                        if resp.clicked() {
                            self.settings_scroll_to = Some(key.to_string());
                        }
                        y += item_h;
                    }

                    // The hairline on the left, spanning header + items only.
                    ui.painter().rect_filled(
                        egui::Rect::from_min_max(
                            egui::pos2(line_x, origin.y),
                            egui::pos2(line_x + 1.0, y),
                        ),
                        0.0,
                        p.line,
                    );
                    ui.allocate_space(egui::vec2(full_w, y - origin.y));
                });
        }

        egui::CentralPanel::default()
            .frame(
                egui::Frame::new()
                    .fill(egui::Color32::TRANSPARENT)
                    .inner_margin(egui::Margin {
                        left: 20,
                        right: 20,
                        top: 10,
                        bottom: 20,
                    }),
            )
            .show(ui, |ui| {
                egui::ScrollArea::vertical()
                    .scroll_bar_visibility(egui::scroll_area::ScrollBarVisibility::AlwaysHidden)
                    .show(ui, |ui| {
                        // A centered container (the same width the header uses), so
                        // the content lines up with the brand/tabs, like the web UI.
                        let avail = ui.available_width();
                        let (pad, w) = if self.tab == Tab::Ajustes {
                            // Settings has a right rail (a separate panel), which
                            // shrinks this area. Align the left edge with the brand
                            // anyway — the brand centers over the full width, rail
                            // included — then run the column up to the rail.
                            let full = avail + SETTINGS_RAIL_W;
                            let container = CONTENT_W.min(full - 8.0);
                            let pad = ((full - container) / 2.0).max(0.0);
                            (pad, (avail - pad - 16.0).max(200.0))
                        } else {
                            let w = CONTENT_W.min(avail - 8.0);
                            (((avail - w) / 2.0).max(0.0), w)
                        };
                        ui.horizontal_top(|ui| {
                            ui.add_space(pad);
                            ui.vertical(|ui| {
                                ui.set_width(w);
                                match self.tab {
                                    Tab::Inicio => self.ui_inicio(ui, p),
                                    Tab::Historial => self.ui_historial(ui, p),
                                    Tab::Ajustes => self.ui_ajustes(ui, p),
                                    Tab::Cola => self.ui_cola(ui, p),
                                    Tab::Logs => self.ui_logs(ui, p),
                                }
                            });
                        });
                    });
            });

        // Supported-sites dialog — an egui Modal (it dims only the background and
        // closes on backdrop click / Escape), with a custom title-bar-less panel.
        if self.supported_open {
            rounded_backdrop(&ctx);
            // Cap the dialog to the window so a short window never clips it; the
            // grid scrolls inside if it doesn't fit.
            let grid_max_h = (ctx.content_rect().height() - 210.0).max(200.0);
            let resp = egui::Modal::new(egui::Id::unique("sites_modal"))
                .frame(modal_frame(p))
                .backdrop_color(egui::Color32::TRANSPARENT)
                .show(&ctx, |ui| {
                    ui.set_width(560.0);
                    // Header: globe + title (left), close (right).
                    ui.horizontal(|ui| {
                        crate::icons::show(ui, "globe", 18.0, p.accent);
                        ui.add_space(8.0);
                        ui.label(
                            RichText::new(tl(lang, "sites.title"))
                                .size(19.0)
                                .family(crate::fonts::display())
                                .color(p.fg),
                        );
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if close_button(ui, p).clicked() {
                                self.supported_open = false;
                            }
                        });
                    });
                    ui.add_space(6.0);
                    ui.label(RichText::new(tl(lang, "sites.intro")).color(p.fg_dim));
                    ui.add_space(16.0);
                    // A 4-column grid of clickable logo + name tiles, each
                    // lightening and gaining an accent border on hover. It scrolls
                    // inside the capped height so a short window never clips it.
                    let lighten = |c: egui::Color32, d: u8| {
                        egui::Color32::from_rgb(
                            c.r().saturating_add(d),
                            c.g().saturating_add(d),
                            c.b().saturating_add(d),
                        )
                    };
                    let cols = 4;
                    egui::ScrollArea::vertical()
                        .max_height(grid_max_h)
                        .auto_shrink([false, true])
                        .scroll_bar_visibility(
                            egui::scroll_area::ScrollBarVisibility::AlwaysHidden,
                        )
                        .show(ui, |ui| {
                    for row in SUPPORTED_SITES.chunks(cols) {
                        ui.columns(cols, |c| {
                            for (i, (slug, name, url)) in row.iter().enumerate() {
                                let col = &mut c[i];
                                let w = col.available_width();
                                let (rect, resp) = col
                                    .allocate_exact_size(egui::vec2(w, 76.0), egui::Sense::click());
                                let hov = resp.hovered();
                                let fill = if hov {
                                    lighten(p.surface_hi, 16)
                                } else {
                                    p.surface_hi
                                };
                                let border = if hov { p.accent } else { p.line };
                                col.painter().rect_filled(rect, 12.0, fill);
                                col.painter().rect_stroke(
                                    rect,
                                    12.0,
                                    egui::Stroke::new(1.0, border),
                                    egui::StrokeKind::Inside,
                                );
                                let mut cui = col.new_child(
                                    egui::UiBuilder::new()
                                        .max_rect(rect)
                                        .layout(egui::Layout::top_down(egui::Align::Center)),
                                );
                                cui.add_space(16.0);
                                crate::icons::show_site(&mut cui, slug, 22.0, p.fg);
                                cui.add_space(9.0);
                                cui.label(RichText::new(*name).small().color(p.fg));
                                if hov {
                                    col.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
                                }
                                if resp.clicked() {
                                    open_url(url);
                                }
                            }
                        });
                        ui.add_space(8.0);
                    }
                        });
                    ui.add_space(10.0);
                    ui.vertical_centered(|ui| {
                        ui.label(
                            RichText::new(tl(lang, "sites.footer"))
                                .small()
                                .color(p.fg_dim),
                        );
                    });
                });
            if resp.should_close() {
                self.supported_open = false;
            }
        }

        // "What's new" popup after an update — same custom modal look as the
        // supported-sites dialog (dimmed backdrop + title-bar-less panel).
        if self.whatsnew_open {
            rounded_backdrop(&ctx);
            let resp = egui::Modal::new(egui::Id::unique("whatsnew_modal"))
                .frame(modal_frame(p))
                .backdrop_color(egui::Color32::TRANSPARENT)
                .show(&ctx, |ui| {
                    ui.set_width(520.0);
                    ui.horizontal(|ui| {
                        crate::icons::show(ui, "sparkles", 18.0, p.accent);
                        ui.add_space(8.0);
                        // The version lives in the title (e.g. "Novedades · v4.4.0");
                        // the newest entry names it. With several versions the
                        // per-version heading below keeps them apart.
                        let title = match self.whatsnew.first() {
                            Some((ver, _)) => format!("{} · {}", tl(lang, "whatsnew.title"), ver),
                            None => tl(lang, "whatsnew.title").to_string(),
                        };
                        ui.label(
                            RichText::new(title)
                                .size(19.0)
                                .family(crate::fonts::display())
                                .color(p.fg),
                        );
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if close_button(ui, p).clicked() {
                                self.whatsnew_open = false;
                            }
                        });
                    });
                    ui.add_space(12.0);
                    egui::ScrollArea::vertical()
                        .max_height(360.0)
                        .auto_shrink([false, true])
                        .scroll_bar_visibility(
                            egui::scroll_area::ScrollBarVisibility::VisibleWhenNeeded,
                        )
                        .show(ui, |ui| {
                            // Only label each version when several are shown at once;
                            // a single version is already named in the modal title.
                            let multi = self.whatsnew.len() > 1;
                            for (ver, notes) in &self.whatsnew {
                                if multi {
                                    ui.label(
                                        RichText::new(ver)
                                            .size(17.0)
                                            .family(crate::fonts::display())
                                            .color(p.fg),
                                    );
                                    ui.add_space(6.0);
                                }
                                render_markdown(ui, p, notes);
                                ui.add_space(14.0);
                            }
                        });
                    ui.add_space(14.0);
                    let btn = egui::Button::new(
                        RichText::new(format!("  {}  ", tl(lang, "whatsnew.close")))
                            .color(p.accent_fg),
                    )
                    .fill(p.accent)
                    .corner_radius(9)
                    .min_size(egui::vec2(0.0, 36.0));
                    if ui.add(btn).clicked() {
                        self.whatsnew_open = false;
                    }
                });
            if resp.should_close() {
                self.whatsnew_open = false;
            }
        }

        // Terms of Use and Open-source licenses — scrollable text modals, same
        // look as the other dialogs, filled from the bundled Markdown.
        for (open, title_key, body) in [
            (&mut self.terms_open, "about.terms", DISCLAIMER_MD),
            (&mut self.licenses_open, "about.licenses", LICENSES_MD),
        ] {
            if !*open {
                continue;
            }
            rounded_backdrop(&ctx);
            let mut close = false;
            let resp = egui::Modal::new(egui::Id::unique(title_key))
                .frame(modal_frame(p))
                .backdrop_color(egui::Color32::TRANSPARENT)
                .show(&ctx, |ui| {
                    ui.set_width(560.0);
                    ui.horizontal(|ui| {
                        crate::icons::show(ui, "logs", 18.0, p.accent);
                        ui.add_space(8.0);
                        ui.label(
                            RichText::new(tl(lang, title_key))
                                .size(19.0)
                                .family(crate::fonts::display())
                                .color(p.fg),
                        );
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if close_button(ui, p).clicked() {
                                close = true;
                            }
                        });
                    });
                    ui.add_space(12.0);
                    egui::ScrollArea::vertical()
                        .max_height(420.0)
                        .auto_shrink([false, true])
                        .scroll_bar_visibility(
                            egui::scroll_area::ScrollBarVisibility::VisibleWhenNeeded,
                        )
                        .show(ui, |ui| {
                            render_markdown(ui, p, body);
                        });
                });
            if close || resp.should_close() {
                *open = false;
            }
        }

        // Borderless window: our own edge/corner resize handles.
        resize_handles(&ctx);

        self.maybe_screenshot(&ctx);
    }
}

impl App {
    /// YOINK_SHOT mode: after a few frames (so fonts/SVGs/thumbnails have loaded),
    /// capture the framebuffer to a PNG and exit — a way to see the UI headlessly.
    fn maybe_screenshot(&mut self, ctx: &egui::Context) {
        let Some((path, started)) = self.shot.as_ref() else {
            return;
        };
        ctx.request_repaint();
        let delay = std::env::var("YOINK_SHOT_MS")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(700);
        if started.elapsed().as_millis() as u64 >= delay {
            let path = path.clone();
            self.shot = None; // fire once
            ctx.send_viewport_cmd(egui::ViewportCommand::Screenshot(
                egui::ScreenshotCallback::new(move |img: std::sync::Arc<egui::ColorImage>| {
                    let [w, h] = img.size;
                    let mut buf = Vec::with_capacity(w * h * 4);
                    for px in &img.pixels {
                        buf.extend_from_slice(&[px.r(), px.g(), px.b(), px.a()]);
                    }
                    if let Some(rgba) = image::RgbaImage::from_raw(w as u32, h as u32, buf) {
                        let _ = rgba.save(&path);
                    }
                    std::process::exit(0);
                }),
            ));
        }
    }

    fn ui_inicio(&mut self, ui: &mut egui::Ui, p: theme::Palette) {
        let lang = self.lang;
        ui.add_space(6.0);

        // URL bar: a rounded pill field + a soft-violet Analyze button to the right.
        let analyzing = matches!(self.status, Status::Analyzing);
        ui.horizontal(|ui| {
            let total = ui.available_width();
            let pill = egui::Frame::new()
                .fill(p.surface_hi)
                .stroke(egui::Stroke::new(1.0, p.line))
                .corner_radius(10)
                .inner_margin(egui::Margin::symmetric(10, 7))
                .show(ui, |ui| {
                    ui.set_width(total - 128.0);
                    ui.horizontal(|ui| {
                        // Fix the row height up front so every item (glyph, combo,
                        // divider, field) centers on the SAME height. Without this,
                        // egui centers the first item (the glyph) on the row height
                        // known so far, before the taller combo grows the row — so
                        // the glyph ends up sitting too high.
                        ui.set_min_height(26.0);
                        // A small, subtle brand glyph for the selected source,
                        // integrated with the picker, then a faint divider — like
                        // the web (not a big saturated logo).
                        let slug = if self.source == "soundcloud" {
                            "soundcloud"
                        } else {
                            "youtube"
                        };
                        // Paint the glyph with a small downward nudge so its center
                        // matches the combo label's optical center (text ink sits
                        // below the geometric row center, so a centered glyph looks
                        // high).
                        let (grect, _) =
                            ui.allocate_exact_size(egui::vec2(14.0, 26.0), egui::Sense::hover());
                        crate::icons::site_img(slug, 14.0, p.fg_dim).paint_at(
                            ui,
                            egui::Rect::from_center_size(
                                grect.center() + egui::vec2(0.0, 3.5),
                                egui::vec2(14.0, 14.0),
                            ),
                        );
                        ui.add_space(4.0);
                        // egui strokes this combo's border with a 1px line. At a
                        // fractional pixels_per_point (a 1.15 desktop scale × our 1.2
                        // zoom ≈ 1.38) that stroke straddles the physical pixel grid and
                        // the bottom edge renders blurry/thin — it looks "cut". So mute
                        // egui's own border and paint our own, snapped to whole physical
                        // pixels and drawn inside the rect, so all four edges are crisp.
                        crisp_combo(ui, p, |ui| {
                            egui::ComboBox::from_id_salt("source")
                                .popup_style(hide_combo_scrollbar.into())
                                .selected_text(if self.source == "soundcloud" {
                                    "SoundCloud"
                                } else {
                                    "YouTube"
                                })
                                .show_ui(ui, |ui| {
                                    style_combo_items(ui);
                                    ui.selectable_value(
                                        &mut self.source,
                                        "youtube".into(),
                                        "YouTube",
                                    );
                                    ui.selectable_value(
                                        &mut self.source,
                                        "soundcloud".into(),
                                        "SoundCloud",
                                    );
                                })
                                .response
                        });
                        ui.add_space(8.0);
                        // Faint vertical divider between the source picker and input.
                        let (dr, _) =
                            ui.allocate_exact_size(egui::vec2(1.0, 22.0), egui::Sense::hover());
                        ui.painter().rect_filled(dr, 0.0, p.line);
                        ui.add_space(8.0);
                        let resp = ui.add(
                            egui::TextEdit::singleline(&mut self.url)
                                .id(egui::Id::unique("url_field"))
                                .hint_text(tl(lang, "inicio.url_hint"))
                                .frame(egui::Frame::NONE)
                                .desired_width(ui.available_width() - 26.0),
                        );
                        if self.focus_url {
                            self.focus_url = false;
                            resp.request_focus();
                        }
                        if resp.changed() {
                            let q = self.url.trim();
                            if q.is_empty() || is_url(q) {
                                self.search_results.clear();
                                self.search_pending = None;
                            } else {
                                self.search_pending = Some(std::time::Instant::now());
                            }
                        }
                        if resp.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) {
                            self.analyze();
                        }
                        let _ = ui.add(
                            egui::Button::image(crate::icons::img("paste", 15.0, p.fg_dim))
                                .frame(false),
                        );
                    });
                });
            ui.add_space(8.0);
            // Match the Analyze button's height to the input pill beside it.
            let btn = egui::Button::image_and_text(
                crate::icons::img("search", 15.0, p.accent),
                RichText::new(tl(lang, "inicio.analyze")).color(p.accent),
            )
            .fill(p.accent.gamma_multiply(0.18))
            .corner_radius(10)
            .min_size(egui::vec2(104.0, pill.response.rect.height()));
            if ui.add_enabled(!analyzing, btn).clicked() {
                self.analyze();
            }
        });
        // "Supported sites" hint, right-aligned under the bar (fixed height so it
        // doesn't grab the column's remaining vertical space).
        ui.add_space(3.0);
        ui.allocate_ui_with_layout(
            egui::vec2(ui.available_width(), 16.0),
            egui::Layout::right_to_left(egui::Align::Center),
            |ui| {
                ui.add_space(112.0);
                // Clickable hint that lights up on hover (dim → full foreground).
                let txt = tl(lang, "inicio.supported").to_string();
                let font = egui::TextStyle::Small.resolve(ui.style());
                let galley =
                    ui.painter()
                        .layout_no_wrap(txt.clone(), font.clone(), p.fg_dim);
                let (rect, resp) =
                    ui.allocate_exact_size(galley.size(), egui::Sense::click());
                let col = if resp.hovered() {
                    ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
                    p.fg
                } else {
                    p.fg_dim
                };
                ui.painter()
                    .text(rect.min, egui::Align2::LEFT_TOP, &txt, font, col);
                if resp.clicked() {
                    self.supported_open = true;
                }
            },
        );

        // Search results dropdown (when typing a query, not a URL).
        if !self.search_results.is_empty() && matches!(self.preview, Preview::None) {
            ui.add_space(8.0);
            let mut picked: Option<String> = None;
            egui::Frame::new()
                .fill(p.surface)
                .corner_radius(10)
                .inner_margin(egui::Margin::same(6))
                .show(ui, |ui| {
                    for r in self.search_results.iter().take(8) {
                        let mut sub = r.uploader.clone().unwrap_or_default();
                        if let Some(d) = r.duration_string.as_deref().filter(|d| !d.is_empty()) {
                            if !sub.is_empty() {
                                sub.push_str("  ·  ");
                            }
                            sub.push_str(d);
                        }
                        let full = ui.available_width();
                        let resp =
                            ui.allocate_response(egui::vec2(full, 44.0), egui::Sense::click());
                        if resp.hovered() {
                            ui.painter().rect_filled(resp.rect, 6.0, p.surface_hi);
                        }
                        let mut inner = ui.new_child(
                            egui::UiBuilder::new()
                                .max_rect(resp.rect.shrink2(egui::vec2(8.0, 6.0)))
                                .layout(egui::Layout::left_to_right(egui::Align::Center)),
                        );
                        if let Some(t) = r.thumbnail_url.as_deref().filter(|s| !s.is_empty()) {
                            inner.add(
                                egui::Image::from_uri(t.to_string())
                                    .fit_to_exact_size(egui::vec2(54.0, 31.0))
                                    .corner_radius(4),
                            );
                            inner.add_space(10.0);
                        }
                        inner.vertical(|ui| {
                            ui.label(RichText::new(&r.title).color(p.fg));
                            if !sub.is_empty() {
                                ui.label(RichText::new(&sub).small().color(p.fg_dim));
                            }
                        });
                        if resp.clicked() {
                            picked = Some(r.url.clone());
                        }
                    }
                });
            if let Some(u) = picked {
                self.pick(u);
            }
        }

        // Status line.
        match &self.status {
            Status::Analyzing => {
                ui.add_space(10.0);
                ui.horizontal(|ui| {
                    ui.spinner();
                    ui.label(RichText::new(tl(lang, "inicio.analyzing")).color(p.fg_dim));
                });
            }
            Status::Error(e) => {
                ui.add_space(10.0);
                ui.label(RichText::new(format!("⚠ {e}")).color(p.err));
            }
            _ => {}
        }

        // Empty state: a centered icon + prompt when nothing is loaded.
        if matches!(self.preview, Preview::None)
            && !matches!(self.status, Status::Analyzing | Status::Error(_))
        {
            ui.add_space(40.0);
            ui.vertical_centered(|ui| {
                crate::icons::show(ui, "cloud", 44.0, p.fg_dim);
                ui.add_space(12.0);
                ui.label(
                    RichText::new(tl(lang, "inicio.empty_title"))
                        .strong()
                        .color(p.fg),
                );
                ui.add_space(2.0);
                ui.label(
                    RichText::new(tl(lang, "inicio.empty_sub"))
                        .small()
                        .color(p.fg_dim),
                );
            });
        }

        // Preview + download controls.
        match &self.preview {
            Preview::Video(v) => {
                let v = v.clone();
                ui.add_space(20.0);
                ui.label(
                    RichText::new(tl(lang, "inicio.preview"))
                        .small()
                        .color(p.fg_dim),
                );
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    if let Some(thumb) = v.thumbnail_url.as_deref().filter(|s| !s.is_empty()) {
                        ui.add(
                            egui::Image::from_uri(thumb.to_string())
                                .fit_to_exact_size(egui::vec2(116.0, 65.0))
                                .corner_radius(6),
                        );
                        ui.add_space(14.0);
                    }
                    ui.vertical(|ui| {
                        ui.label(
                            RichText::new(&v.title)
                                .size(19.0)
                                .family(crate::fonts::display())
                                .color(p.fg),
                        );
                        ui.add_space(4.0);
                        let mut meta = Vec::new();
                        if let Some(u) = &v.uploader {
                            meta.push(u.clone());
                        }
                        // The best available resolution, like the web ("2160p available"),
                        // falling back to the duration when formats carry no height.
                        if let Some(h) = v.best_height() {
                            meta.push(format!("{h}p {}", tl(lang, "inicio.available")));
                        } else if let Some(d) = &v.duration_string {
                            meta.push(d.clone());
                        }
                        if v.is_vr {
                            meta.push("VR".into());
                        }
                        ui.label(RichText::new(meta.join("  ·  ")).small().color(p.fg_dim));
                    });
                });
                ui.add_space(16.0);
                let (ha, bh, bs) = (v.has_audio, v.best_height(), v.best_filesize());
                let (hs, hc) = (!v.subtitle_langs.is_empty(), v.has_chapters);
                self.ui_download_controls(ui, p, ha, bh, bs, hs, hc);
                self.ui_progress(ui, p);
            }
            Preview::Playlist { title, count } => {
                let (title, count) = (title.clone(), *count);
                ui.add_space(14.0);
                card(ui, p, |ui| {
                    ui.label(RichText::new(&title).size(17.0).strong().color(p.fg));
                    ui.label(
                        RichText::new(format!(
                            "{} · {count} {}",
                            tl(lang, "inicio.playlist"),
                            tl(lang, "inicio.playlist_items")
                        ))
                        .color(p.fg_dim),
                    );
                    ui.add_space(6.0);
                    ui.label(
                        RichText::new(tl(lang, "inicio.playlist_soon"))
                            .small()
                            .color(p.fg_dim),
                    );
                });
            }
            Preview::Music(info) => {
                let info = info.clone();
                let single = info.tracks.len() == 1;
                ui.add_space(14.0);
                let mut import = false;
                // "IMPORT" eyebrow, like the web.
                ui.horizontal(|ui| {
                    crate::icons::show(ui, "music", 12.0, p.accent);
                    ui.add_space(4.0);
                    ui.label(
                        RichText::new(tl(lang, "music.label"))
                            .small()
                            .color(p.accent),
                    );
                });
                ui.add_space(8.0);
                ui.horizontal_top(|ui| {
                    // A larger, square cover (track cover for a single, else the set's).
                    let cover = if single {
                        info.tracks[0].cover_url.as_deref()
                    } else {
                        info.cover_url.as_deref()
                    }
                    .filter(|s| !s.is_empty())
                    .or(info.cover_url.as_deref());
                    if let Some(c) = cover.filter(|s| !s.is_empty()) {
                        ui.add(
                            egui::Image::from_uri(c.to_string())
                                .fit_to_exact_size(egui::vec2(132.0, 132.0))
                                .corner_radius(8),
                        );
                        ui.add_space(14.0);
                    }
                    ui.vertical(|ui| {
                        let title = if single {
                            &info.tracks[0].title
                        } else {
                            &info.name
                        };
                        ui.label(
                            RichText::new(title)
                                .size(21.0)
                                .family(crate::fonts::display())
                                .color(p.fg),
                        );
                        if single {
                            ui.add_space(2.0);
                            ui.label(
                                RichText::new(&info.tracks[0].artists)
                                    .size(14.0)
                                    .color(p.fg),
                            );
                        }
                        ui.add_space(4.0);
                        let mut meta = vec![cap_first(&info.source)];
                        if single {
                            let t = &info.tracks[0];
                            if let Some(y) = t.year.as_deref().filter(|y| !y.is_empty()) {
                                meta.push(y.to_string());
                            }
                            if let Some(ms) = t.duration_ms {
                                meta.push(fmt_ms(ms));
                            }
                        } else {
                            if let Some(sub) = info.subtitle.as_deref().filter(|s| !s.is_empty()) {
                                meta.push(sub.to_string());
                            }
                            meta.push(format!("{} {}", info.tracks.len(), tl(lang, "music.songs")));
                        }
                        ui.label(RichText::new(meta.join("  ·  ")).small().color(p.fg_dim));
                        if !single {
                            ui.add_space(8.0);
                            for t in info.tracks.iter().take(6) {
                                ui.label(
                                    RichText::new(format!("•  {} — {}", t.artists, t.title))
                                        .small()
                                        .color(p.fg_dim),
                                );
                            }
                            if info.tracks.len() > 6 {
                                ui.label(RichText::new("…").small().color(p.fg_dim));
                            }
                        }
                    });
                });
                // Info note (why the audio is matched, not pulled from the source).
                ui.add_space(12.0);
                ui.horizontal(|ui| {
                    crate::icons::show(ui, "help", 13.0, p.fg_dim);
                    ui.add_space(5.0);
                    ui.label(
                        RichText::new(tl(lang, "music.hint"))
                            .small()
                            .color(p.fg_dim),
                    );
                });
                ui.add_space(12.0);
                // Wide import button.
                let label = if single {
                    tl(lang, "music.download").to_string()
                } else {
                    format!("{} ({})", tl(lang, "music.import"), info.tracks.len())
                };
                let btn = egui::Button::image_and_text(
                    crate::icons::img("download", 15.0, p.accent_fg),
                    RichText::new(label).color(p.accent_fg),
                )
                .fill(p.accent)
                .corner_radius(10)
                .min_size(egui::vec2(ui.available_width(), 44.0));
                if ui.add(btn).clicked() {
                    import = true;
                }
                if import {
                    self.enqueue_music(&info);
                    self.tab = Tab::Cola;
                    self.preview = Preview::None;
                }
            }
            Preview::None => {}
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn ui_download_controls(
        &mut self,
        ui: &mut egui::Ui,
        p: theme::Palette,
        has_audio: bool,
        best_h: Option<u32>,
        best_size: Option<i64>,
        has_subs: bool,
        has_chapters: bool,
    ) {
        let lang = self.lang;
        ui.horizontal(|ui| {
            // Video / Audio segmented pills.
            for (k, key, enabled) in [
                ("video", "kind.video", true),
                ("audio", "kind.audio", has_audio),
            ] {
                let active = self.kind == k;
                let (fg, fill) = if active {
                    (p.accent_fg, p.accent)
                } else {
                    (p.fg_dim, p.surface_hi)
                };
                ui.add_enabled_ui(enabled, |ui| {
                    if ui
                        .add(
                            egui::Button::new(RichText::new(tl(lang, key)).color(fg))
                                .fill(fill)
                                .corner_radius(8)
                                .min_size(egui::vec2(72.0, 34.0)),
                        )
                        .clicked()
                    {
                        self.kind = k.to_string();
                    }
                });
            }
            ui.add_space(10.0);
            // Wide Download button, with the chosen format summarised — the way
            // the web does it: "2160p · MP4 · ≈ 1.3 GB" when "best" resolves to a
            // concrete height, plus a rough size estimate.
            let summary = if self.kind == "video" {
                let q = match best_h {
                    Some(h) if self.quality == "best" => format!("{h}p"),
                    _ => opt_label(lang, &self.quality),
                };
                let mut s = format!("{q} · {}", opt_label(lang, &self.container));
                if let Some(sz) = best_size {
                    s.push_str(&format!(" · ≈ {}", human_bytes(sz)));
                }
                s
            } else {
                opt_label(lang, &self.audio_format)
            };
            let busy = self.active.is_some();
            let label = format!("{}   ·  {summary}", tl(lang, "action.download"));
            let btn = egui::Button::image_and_text(
                crate::icons::img("download", 16.0, p.accent_fg),
                RichText::new(label).color(p.accent_fg),
            )
            .fill(p.accent)
            .corner_radius(10)
            .min_size(egui::vec2(ui.available_width(), 38.0));
            if ui.add_enabled(!busy, btn).clicked() {
                self.start_download();
            }
        });

        // Add to queue · Advanced options (subtle link row).
        ui.add_space(10.0);
        ui.horizontal(|ui| {
            if ui
                .add(
                    egui::Button::image_and_text(
                        crate::icons::img("add", 14.0, p.fg_dim),
                        RichText::new(tl(lang, "inicio.add_queue"))
                            .small()
                            .color(p.fg_dim),
                    )
                    .frame(false),
                )
                .clicked()
            {
                self.q_kind = self.kind.clone();
                self.q_quality = self.quality.clone();
                self.q_container = self.container.clone();
                self.q_audio = self.audio_format.clone();
                self.q_bitrate = self.bitrate.clone();
                self.queue_url = self.url.clone();
                self.queue_add();
            }
            ui.add_space(14.0);
            if ui
                .add(
                    egui::Button::image_and_text(
                        crate::icons::img("options", 14.0, p.fg_dim),
                        RichText::new(tl(lang, "inicio.advanced"))
                            .small()
                            .color(p.fg_dim),
                    )
                    .frame(false),
                )
                .clicked()
            {
                self.advanced_open = !self.advanced_open;
            }
        });

        // Collapsible advanced options: FORMAT (+ codec/bitrate), subtitles /
        // chapters when the source has them, and a trim range — like the web.
        if self.advanced_open {
            ui.add_space(10.0);
            ui.separator();
            ui.add_space(8.0);

            // Presets: apply a saved format bundle, or save the current one.
            adv_row(ui, p, tl(lang, "preset.plural"), |ui| {
                let presets = self.presets.clone();
                let mut apply: Option<usize> = None;
                let mut del: Option<usize> = None;
                for (i, pr) in presets.iter().enumerate() {
                    egui::Frame::new()
                        .fill(p.surface)
                        .corner_radius(8)
                        .stroke(egui::Stroke::new(1.0, p.line))
                        .inner_margin(egui::Margin {
                            left: 10,
                            right: 4,
                            top: 2,
                            bottom: 2,
                        })
                        .show(ui, |ui| {
                            if ui
                                .add(
                                    egui::Button::new(RichText::new(&pr.name).small().color(p.fg))
                                        .frame(false),
                                )
                                .clicked()
                            {
                                apply = Some(i);
                            }
                            let (xr, xresp) = ui
                                .allocate_exact_size(egui::vec2(18.0, 18.0), egui::Sense::click());
                            let hov = xresp.hovered();
                            if hov {
                                ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
                            }
                            let xc = if hov { p.err } else { p.fg_dim };
                            crate::icons::img("x", 11.0, xc).paint_at(
                                ui,
                                egui::Rect::from_center_size(xr.center(), egui::vec2(11.0, 11.0)),
                            );
                            if xresp.clicked() {
                                del = Some(i);
                            }
                        });
                }
                if self.preset_naming {
                    let r = ui.add(
                        egui::TextEdit::singleline(&mut self.preset_name)
                            .hint_text(tl(lang, "preset.name"))
                            .desired_width(120.0),
                    );
                    let enter = r.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter));
                    if ui.input(|i| i.key_pressed(egui::Key::Escape)) {
                        self.preset_naming = false;
                        self.preset_name.clear();
                    } else if (ui
                        .add(
                            egui::Button::new(
                                RichText::new(tl(lang, "action.save")).small().color(p.accent),
                            )
                            .fill(p.accent.gamma_multiply(0.16))
                            .corner_radius(8),
                        )
                        .clicked()
                        || enter)
                        && !self.preset_name.trim().is_empty()
                    {
                        self.presets.push(Preset {
                            name: self.preset_name.trim().to_string(),
                            kind: self.kind.clone(),
                            quality: self.quality.clone(),
                            container: self.container.clone(),
                            audio_format: self.audio_format.clone(),
                            bitrate: self.bitrate.clone(),
                            codec: self.codec.clone(),
                            embed_subs: self.embed_subs,
                            embed_chapters: self.embed_chapters,
                        });
                        save_presets(&self.presets);
                        self.preset_naming = false;
                        self.preset_name.clear();
                    }
                } else if ui
                    .add(
                        egui::Button::image_and_text(
                            crate::icons::img("plus", 12.0, p.fg_dim),
                            RichText::new(tl(lang, "preset.save_current")).small().color(p.fg_dim),
                        )
                        .frame(false),
                    )
                    .clicked()
                {
                    self.preset_naming = true;
                    self.preset_name.clear();
                }
                if let Some(i) = apply {
                    let pr = &self.presets[i];
                    self.kind = pr.kind.clone();
                    self.quality = pr.quality.clone();
                    self.container = pr.container.clone();
                    self.audio_format = pr.audio_format.clone();
                    self.bitrate = pr.bitrate.clone();
                    self.codec = pr.codec.clone();
                    self.embed_subs = pr.embed_subs;
                    self.embed_chapters = pr.embed_chapters;
                }
                if let Some(i) = del {
                    self.presets.remove(i);
                    save_presets(&self.presets);
                }
            });

            let kind = self.kind.clone();
            adv_row(ui, p, tl(lang, "adv.format"), |ui| {
                if kind == "video" {
                    combo_bare(
                        ui,
                        lang,
                        "aq",
                        &mut self.quality,
                        &["best", "2160", "1440", "1080", "720", "480"],
                    );
                    combo_bare(
                        ui,
                        lang,
                        "ac",
                        &mut self.container,
                        &["mp4", "mov", "mkv", "webm"],
                    );
                    combo_bare(
                        ui,
                        lang,
                        "acd",
                        &mut self.codec,
                        &["any", "h264", "h265", "vp9", "av1"],
                    );
                } else {
                    combo_bare(
                        ui,
                        lang,
                        "af",
                        &mut self.audio_format,
                        &["mp3", "m4a", "opus", "flac", "wav"],
                    );
                    combo_bare(
                        ui,
                        lang,
                        "abr",
                        &mut self.bitrate,
                        &["best", "320", "256", "192", "128"],
                    );
                }
            });
            if kind == "video" && has_subs {
                adv_row(ui, p, tl(lang, "field.subs"), |ui| {
                    toggle(ui, &mut self.embed_subs, p);
                });
            }
            if kind == "video" && has_chapters {
                adv_row(ui, p, tl(lang, "field.chapters"), |ui| {
                    toggle(ui, &mut self.embed_chapters, p);
                });
            }
            adv_row(ui, p, tl(lang, "adv.trim"), |ui| {
                let field = |ui: &mut egui::Ui, v: &mut String, hint: &str| {
                    ui.add(
                        egui::TextEdit::singleline(v)
                            .hint_text(hint)
                            .desired_width(88.0),
                    );
                };
                field(ui, &mut self.trim_start, "0:00");
                ui.label(RichText::new("→").color(p.fg_dim));
                field(ui, &mut self.trim_end, "m:ss");
            });
        }
    }

    fn ui_progress(&mut self, ui: &mut egui::Ui, p: theme::Palette) {
        match &self.status {
            Status::Downloading => {
                ui.add_space(12.0);
                let mut extra = Vec::new();
                if let Some(s) = &self.speed {
                    extra.push(s.clone());
                }
                if let Some(e) = &self.eta {
                    extra.push(format!("ETA {e}"));
                }
                ui.add(
                    egui::ProgressBar::new(self.progress)
                        .show_percentage()
                        .text(extra.join("  ·  ")),
                );
            }
            Status::Done(path) => {
                ui.add_space(12.0);
                let label = tl(self.lang, "inicio.downloaded");
                ui.label(RichText::new(format!("✓ {label}: {path}")).color(p.ok));
            }
            _ => {}
        }
    }

    fn ui_historial(&mut self, ui: &mut egui::Ui, p: theme::Palette) {
        let lang = self.lang;
        ui.add_space(16.0);

        // Stat header: big Gloock numbers + a Refrescar action.
        let count = self.history.len();
        let total: i64 = self.history.iter().filter_map(|e| e.filesize).sum();
        ui.horizontal(|ui| {
            ui.vertical(|ui| {
                ui.horizontal(|ui| {
                    big_stat(ui, p, &count.to_string(), tl(lang, "hist.downloads"));
                    ui.add_space(36.0);
                    big_stat(ui, p, &human_bytes(total), tl(lang, "hist.transferred"));
                });
            });
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui
                    .add(
                        egui::Button::image_and_text(
                            crate::icons::img("history", 14.0, p.fg_dim),
                            RichText::new(tl(lang, "action.refresh"))
                                .small()
                                .color(p.fg_dim),
                        )
                        .frame(false),
                    )
                    .clicked()
                {
                    self.backend.send(Cmd::LoadHistory);
                }
            });
        });
        ui.add_space(12.0);

        if self.history.is_empty() {
            ui.add_space(24.0);
            ui.label(RichText::new(tl(lang, "hist.empty")).color(p.fg_dim));
            return;
        }

        // Search filter.
        egui::Frame::new()
            .fill(p.surface_hi)
            .corner_radius(10)
            .inner_margin(egui::Margin::symmetric(12, 8))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    crate::icons::show(ui, "search", 15.0, p.fg_dim);
                    ui.add_space(6.0);
                    ui.add(
                        egui::TextEdit::singleline(&mut self.hist_query)
                            .hint_text(tl(lang, "hist.search"))
                            .frame(egui::Frame::NONE)
                            .desired_width(f32::INFINITY),
                    );
                });
            });
        ui.add_space(8.0);

        let q = self.hist_query.to_lowercase();
        // "This week" section label.
        ui.add_space(4.0);
        ui.label(
            RichText::new(tl(lang, "hist.thisweek"))
                .small()
                .color(p.fg_dim),
        );

        let mut open_path: Option<String> = None;
        for e in self
            .history
            .iter()
            .filter(|e| q.is_empty() || e.title.to_lowercase().contains(&q))
        {
            // The whole row is a hover-highlighted click target that opens the file.
            let resp = egui::Frame::new()
                .inner_margin(egui::Margin::symmetric(6, 8))
                .corner_radius(8)
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        fmt_badge(ui, p, &badge_label(e));
                        ui.add_space(12.0);
                        ui.vertical(|ui| {
                            ui.set_width(ui.available_width() - 90.0);
                            ui.label(RichText::new(&e.title).strong().color(p.fg));
                            ui.add_space(3.0);
                            ui.horizontal(|ui| {
                                if e.status == "completed" {
                                    crate::icons::show(ui, "check", 13.0, p.ok);
                                    ui.add_space(2.0);
                                } else if e.status == "error" {
                                    crate::icons::show(ui, "x", 13.0, p.err);
                                    ui.add_space(2.0);
                                }
                                let mut meta = Vec::new();
                                if let Some(q) = e.quality.as_deref().filter(|q| !q.is_empty()) {
                                    meta.push(q.to_string());
                                }
                                if let Some(sz) = e.filesize {
                                    meta.push(human_bytes(sz));
                                }
                                ui.label(RichText::new(meta.join("  ·  ")).small().color(p.fg_dim));
                            });
                        });
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            ui.label(
                                RichText::new(relative(&e.created_at, lang))
                                    .small()
                                    .color(p.fg_dim),
                            );
                        });
                    });
                })
                .response
                .interact(egui::Sense::click());
            if resp.clicked() {
                if let Some(path) = e.filepath.clone().filter(|_| e.status == "completed") {
                    open_path = Some(path);
                }
            }
        }
        if let Some(path) = open_path {
            self.backend.send(Cmd::Open(path));
        }
    }

    fn ui_cola(&mut self, ui: &mut egui::Ui, p: theme::Palette) {
        let lang = self.lang;
        ui.add_space(16.0);
        ui.label(
            RichText::new(tl(lang, "tab.cola"))
                .size(26.0)
                .family(crate::fonts::display())
                .color(p.fg),
        );
        ui.add_space(12.0);

        // Add box: a pill field + an Add button.
        ui.horizontal(|ui| {
            let total = ui.available_width();
            egui::Frame::new()
                .fill(p.surface_hi)
                .corner_radius(10)
                .inner_margin(egui::Margin::symmetric(14, 9))
                .show(ui, |ui| {
                    ui.set_width(total - 100.0);
                    let resp = ui.add(
                        egui::TextEdit::singleline(&mut self.queue_url)
                            .hint_text(tl(lang, "cola.add_hint"))
                            .frame(egui::Frame::NONE)
                            .desired_width(f32::INFINITY),
                    );
                    if resp.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) {
                        self.queue_add();
                    }
                });
            ui.add_space(8.0);
            if ui
                .add(
                    egui::Button::image_and_text(
                        crate::icons::img("add", 15.0, p.fg_dim),
                        RichText::new(tl(lang, "action.add")).color(p.fg_dim),
                    )
                    .fill(p.surface_hi)
                    .corner_radius(10)
                    .min_size(egui::vec2(84.0, 38.0)),
                )
                .clicked()
            {
                self.queue_add();
            }
        });

        // FORMAT row: the pickers used for new URL items + a Start button.
        ui.add_space(10.0);
        ui.horizontal(|ui| {
            // Fix the row height first so the label centers on the full (combo)
            // height instead of being laid out high before the combo grows the row.
            ui.set_min_height(34.0);
            ui.label(
                RichText::new(tl(lang, "cola.format"))
                    .small()
                    .color(p.fg_dim),
            );
            ui.add_space(6.0);
            combo_bare(ui, lang, "q.kind", &mut self.q_kind, &["video", "audio"]);
            // Order: Type → Format → Quality, the same for video and audio.
            if self.q_kind == "video" {
                combo_bare(
                    ui,
                    lang,
                    "q.c",
                    &mut self.q_container,
                    &["mp4", "mov", "mkv", "webm"],
                );
                combo_bare(
                    ui,
                    lang,
                    "q.q",
                    &mut self.q_quality,
                    &["best", "2160", "1440", "1080", "720", "480"],
                );
            } else {
                combo_bare(
                    ui,
                    lang,
                    "q.a",
                    &mut self.q_audio,
                    &["mp3", "m4a", "opus", "flac", "wav"],
                );
                // Audio quality (bitrate), the counterpart to video resolution.
                combo_bare(
                    ui,
                    lang,
                    "q.br",
                    &mut self.q_bitrate,
                    &["best", "320", "256", "192", "128"],
                );
            }
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                let running = self.queue_started && self.active.is_some();
                let label = if running {
                    tl(lang, "cola.running")
                } else {
                    tl(lang, "action.start")
                };
                if ui
                    .add_enabled(
                        !self.queue.is_empty(),
                        egui::Button::image_and_text(
                            crate::icons::img("play", 14.0, p.accent),
                            RichText::new(label).color(p.accent),
                        )
                        .fill(p.accent.gamma_multiply(0.18))
                        .corner_radius(9)
                        .min_size(egui::vec2(0.0, 34.0)),
                    )
                    .clicked()
                {
                    self.queue_started = true;
                }
            });
        });

        if self.queue.is_empty() {
            ui.add_space(40.0);
            ui.vertical_centered(|ui| {
                ui.label(RichText::new(tl(lang, "cola.empty")).color(p.fg_dim));
            });
            return;
        }

        // Overall progress summary + a full-width bar, like the web.
        let total = self.queue.len();
        let done = self
            .queue
            .iter()
            .filter(|i| matches!(i.status, QStatus::Done))
            .count();
        let cur = self
            .queue
            .iter()
            .find(|i| matches!(i.status, QStatus::Downloading))
            .map(|i| i.progress)
            .unwrap_or(0.0);
        let overall = if total == 0 {
            0.0
        } else {
            ((done as f32 + cur) / total as f32).clamp(0.0, 1.0)
        };
        ui.add_space(12.0);
        ui.horizontal(|ui| {
            ui.label(
                RichText::new(format!(
                    "{done} {} {total} {}",
                    tl(lang, "cola.of"),
                    tl(lang, "cola.downloaded")
                ))
                .small()
                .color(p.fg_dim),
            );
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ui.label(
                    RichText::new(format!("{:.0}%", overall * 100.0))
                        .small()
                        .color(p.fg_dim),
                );
                if done > 0 {
                    ui.add_space(14.0);
                    if ui
                        .add(
                            egui::Button::new(
                                RichText::new(tl(lang, "cola.clear_done"))
                                    .small()
                                    .color(p.fg_dim),
                            )
                            .frame(false),
                        )
                        .clicked()
                    {
                        self.queue.retain(|i| !matches!(i.status, QStatus::Done));
                    }
                }
            });
        });
        ui.add_space(6.0);
        ui.add(
            egui::ProgressBar::new(overall)
                .desired_height(4.0)
                .corner_radius(2.0)
                .fill(p.accent),
        );
        ui.add_space(8.0);

        let mut remove: Option<u64> = None;
        let mut swap: Option<(usize, usize)> = None;
        let n = self.queue.len();
        for (idx, it) in self.queue.iter().enumerate() {
            let resp = egui::Frame::new()
                .inner_margin(egui::Margin::symmetric(6, 9))
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        // Status dot.
                        let dot = match &it.status {
                            QStatus::Pending => p.fg_dim,
                            QStatus::Downloading => p.accent,
                            QStatus::Done => p.ok,
                            QStatus::Error(_) => p.err,
                        };
                        let (r, _) =
                            ui.allocate_exact_size(egui::vec2(14.0, 14.0), egui::Sense::hover());
                        ui.painter().circle_filled(r.center(), 4.0, dot);
                        ui.add_space(6.0);
                        ui.vertical(|ui| {
                            ui.set_width(ui.available_width() - 44.0);
                            let label: String = it.label.chars().take(72).collect();
                            ui.label(RichText::new(label).color(p.fg));
                            ui.add_space(2.0);
                            let (extra, col) = match &it.status {
                                QStatus::Pending => (String::new(), p.fg_dim),
                                QStatus::Downloading => {
                                    (format!("  ·  {:.0}%", it.progress * 100.0), p.accent)
                                }
                                QStatus::Done => (format!("  ·  {}", tl(lang, "cola.done")), p.ok),
                                QStatus::Error(e) => (format!("  ·  {e}"), p.err),
                            };
                            ui.label(
                                RichText::new(format!("{}{extra}", queue_source(it, lang)))
                                    .small()
                                    .color(col),
                            );
                        });
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if !matches!(it.status, QStatus::Downloading) {
                                // Remove, then the reorder arrows (right-to-left:
                                // X rightmost, then ↓, then ↑).
                                if icon_btn(ui, p, "x") {
                                    remove = Some(it.id);
                                }
                                if idx + 1 < n && icon_btn(ui, p, "chevron") {
                                    swap = Some((idx, idx + 1));
                                }
                                if idx > 0 && icon_btn(ui, p, "chevron-up") {
                                    swap = Some((idx, idx - 1));
                                }
                            }
                        });
                    });
                })
                .response;
            let _ = resp;
        }
        if let Some((a, b)) = swap {
            self.queue.swap(a, b);
        }
        if let Some(id) = remove {
            self.queue.retain(|i| i.id != id);
        }
    }

    fn ui_logs(&mut self, ui: &mut egui::Ui, p: theme::Palette) {
        let lang = self.lang;
        ui.add_space(16.0);
        ui.horizontal(|ui| {
            ui.label(
                RichText::new(tl(lang, "tab.logs"))
                    .size(26.0)
                    .family(crate::fonts::display())
                    .color(p.fg),
            );
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                let txt_btn = |ui: &mut egui::Ui, icon: &str, label: &str| {
                    ui.add(
                        egui::Button::image_and_text(
                            crate::icons::img(icon, 14.0, p.fg_dim),
                            RichText::new(label).small().color(p.fg_dim),
                        )
                        .frame(false),
                    )
                    .clicked()
                };
                // Right-to-left: added rightmost-first, so this reads
                // "Refresh · Copy · Export" left-to-right, like the web.
                if txt_btn(ui, "download", tl(lang, "action.export")) && !self.logs_path.is_empty()
                {
                    self.backend.send(Cmd::Open(self.logs_path.clone()));
                }
                ui.add_space(12.0);
                if txt_btn(ui, "paste", tl(lang, "action.copy")) {
                    ui.ctx().copy_text(self.logs_text.clone());
                }
                ui.add_space(12.0);
                if txt_btn(ui, "history", tl(lang, "action.refresh")) {
                    self.backend.send(Cmd::LoadLogs);
                }
            });
        });
        ui.add_space(4.0);
        let lines = self.logs_text.lines().count();
        let sub = if self.logs_path.is_empty() {
            String::new()
        } else {
            format!("{}  ·  {lines}", self.logs_path)
        };
        ui.label(RichText::new(sub).small().color(p.fg_dim));
        ui.add_space(10.0);
        egui::Frame::new()
            .fill(p.surface)
            .corner_radius(10)
            .inner_margin(egui::Margin::same(12))
            .show(ui, |ui| {
                egui::ScrollArea::vertical()
                    .max_height(560.0)
                    .auto_shrink([false, false])
                    .stick_to_bottom(true)
                    .show(ui, |ui| {
                        ui.add(
                            egui::Label::new(
                                RichText::new(&self.logs_text)
                                    .monospace()
                                    .size(11.0)
                                    .color(p.fg_dim),
                            )
                            .wrap(),
                        );
                    });
            });
    }

    fn ui_ajustes(&mut self, ui: &mut egui::Ui, p: theme::Palette) {
        let lang = self.lang;
        ui.add_space(16.0);

        let Some(mut s) = self.settings.clone() else {
            ui.add_space(24.0);
            if self.settings_failed {
                ui.label(RichText::new(tl(lang, "state.load_failed")).color(p.err));
                ui.add_space(8.0);
                if ui
                    .add(
                        egui::Button::new(
                            RichText::new(format!("  {}  ", tl(lang, "action.retry")))
                                .color(p.accent),
                        )
                        .fill(p.accent.gamma_multiply(0.16))
                        .corner_radius(9)
                        .min_size(egui::vec2(0.0, 32.0)),
                    )
                    .clicked()
                {
                    self.settings_failed = false;
                    self.backend.send(Cmd::ReloadSettings);
                }
            } else {
                ui.horizontal(|ui| {
                    ui.spinner();
                    ui.label(RichText::new(tl(lang, "state.loading")).color(p.fg_dim));
                });
            }
            return;
        };
        let mut lang_sel = self.lang_mode; // None = follow the OS
        let scroll_to = self.settings_scroll_to.take();
        // Scrollspy: the deepest section whose heading has reached the viewport top
        // is the active one — the right-rail nav paints it in the accent colour.
        let active = std::cell::RefCell::new(self.active_section.clone());

        let heading = |ui: &mut egui::Ui, sec: &str, key: &str| {
            settings_section();
            ui.add_space(10.0);
            let r = ui.label(
                RichText::new(tl(lang, key))
                    .size(26.0)
                    .family(crate::fonts::display())
                    .color(p.fg),
            );
            if scroll_to.as_deref() == Some(sec) {
                r.scroll_to_me(Some(egui::Align::TOP));
            }
            if r.rect.top() <= ui.clip_rect().top() + 90.0 {
                *active.borrow_mut() = sec.to_string();
            }
            ui.add_space(2.0);
        };

        // General.
        heading(ui, "sec.general", "set.general");
        setting_row(ui, p, tl(lang, "set.language"), |ui| {
            crisp_combo(ui, p, |ui| {
                egui::ComboBox::from_id_salt("lang")
                    .popup_style(hide_combo_scrollbar.into())
                    .width(CTRL_COMBO_W)
                    .selected_text(match self.lang_mode {
                        None => tl(lang, "lang.system"),
                        Some(l) => l.label(),
                    })
                    .show_ui(ui, |ui| {
                        style_combo_items(ui);
                        ui.selectable_value(&mut lang_sel, None, tl(lang, "lang.system"));
                        for l in Lang::ALL {
                            ui.selectable_value(&mut lang_sel, Some(l), l.label());
                        }
                    })
                    .response
            });
        });
        let mut mode = self.theme_mode;
        let mode_label = |m: ThemeMode| match m {
            ThemeMode::System => tl(lang, "theme.system"),
            ThemeMode::Dark => tl(lang, "theme.dark"),
            ThemeMode::Light => tl(lang, "theme.light"),
        };
        setting_row(ui, p, tl(lang, "set.theme"), |ui| {
            crisp_combo(ui, p, |ui| {
                egui::ComboBox::from_id_salt("theme")
                    .popup_style(hide_combo_scrollbar.into())
                    .width(CTRL_COMBO_W)
                    .selected_text(mode_label(mode))
                    .show_ui(ui, |ui| {
                        style_combo_items(ui);
                        ui.selectable_value(
                            &mut mode,
                            ThemeMode::System,
                            mode_label(ThemeMode::System),
                        );
                        ui.selectable_value(&mut mode, ThemeMode::Dark, mode_label(ThemeMode::Dark));
                        ui.selectable_value(
                            &mut mode,
                            ThemeMode::Light,
                            mode_label(ThemeMode::Light),
                        );
                    })
                    .response
            });
        });
        if mode != self.theme_mode {
            self.theme_mode = mode;
            // Apply immediately; the per-frame resolver keeps System in sync.
            let dark = match mode {
                ThemeMode::System => {
                    self.os_dark = detect_os_dark(&ui.ctx().clone());
                    self.theme_probe = std::time::Instant::now();
                    self.os_dark.unwrap_or(self.dark)
                }
                ThemeMode::Dark => true,
                ThemeMode::Light => false,
            };
            self.dark = dark;
            theme::apply(&ui.ctx().clone(), dark);
            save_prefs(self.theme_mode, self.lang_mode);
        }
        setting_row(ui, p, tl(lang, "set.updates"), |ui| {
            toggle(ui, &mut s.check_updates, p);
        });
        setting_row(ui, p, tl(lang, "set.notify"), |ui| {
            toggle(ui, &mut s.notify_on_complete, p);
        });
        setting_row(ui, p, tl(lang, "set.tray"), |ui| {
            toggle(ui, &mut s.minimize_to_tray, p);
        });
        setting_row(ui, p, tl(lang, "set.autostart"), |ui| {
            toggle(ui, &mut s.launch_at_startup, p);
        });

        // Downloads.
        ui.add_space(20.0);
        heading(ui, "sec.downloads", "set.downloads");
        ui.add_space(12.0);
        ui.label(RichText::new(tl(lang, "set.dir")).small().color(p.fg_dim));
        ui.add_space(3.0);
        if path_field(ui, p, &mut s.download_dir) {
            let mut dlg = rfd::FileDialog::new();
            if !s.download_dir.is_empty() {
                dlg = dlg.set_directory(&s.download_dir);
            }
            if let Some(dir) = dlg.pick_folder() {
                s.download_dir = dir.to_string_lossy().into_owned();
            }
        }
        settings_row_rendered();
        setting_row(ui, p, tl(lang, "field.kind"), |ui| {
            combo_bare(
                ui,
                lang,
                "set.kind",
                &mut s.default_kind,
                &["video", "audio"],
            );
        });
        setting_row(ui, p, tl(lang, "field.quality"), |ui| {
            combo_bare(
                ui,
                lang,
                "set.q",
                &mut s.default_quality,
                &["best", "2160", "1440", "1080", "720", "480"],
            );
        });
        setting_row(ui, p, tl(lang, "field.container"), |ui| {
            combo_bare(
                ui,
                lang,
                "set.c",
                &mut s.default_container,
                &["mp4", "mov", "mkv", "webm"],
            );
        });
        setting_row(ui, p, tl(lang, "field.audio"), |ui| {
            combo_bare(
                ui,
                lang,
                "set.a",
                &mut s.default_audio_format,
                &["mp3", "m4a", "opus", "flac", "wav"],
            );
        });
        ui.add_space(10.0);
        ui.label(
            RichText::new(tl(lang, "set.filename"))
                .small()
                .color(p.fg_dim),
        );
        ui.add_space(3.0);
        // A preset picker (plus a "Custom…" entry) like the web — the raw templates
        // were lost in the port. The selected text shows the preset's friendly label.
        let cur_label = if self.template_custom {
            tl(lang, "set.filename_custom").to_string()
        } else {
            TEMPLATE_PRESETS
                .iter()
                .find(|(v, _)| *v == s.filename_template)
                .map(|(_, l)| l.to_string())
                .unwrap_or_else(|| s.filename_template.clone())
        };
        let tpl_w = (ui.available_width() - 2.0).max(200.0);
        crisp_combo(ui, p, |ui| {
            egui::ComboBox::from_id_salt("filename_tpl")
                .popup_style(hide_combo_scrollbar.into())
                .width(tpl_w)
                .selected_text(cur_label)
                .show_ui(ui, |ui| {
                    style_combo_items(ui);
                    for (val, label) in TEMPLATE_PRESETS {
                        if ui
                            .selectable_label(
                                !self.template_custom && s.filename_template == val,
                                label,
                            )
                            .clicked()
                        {
                            self.template_custom = false;
                            s.filename_template = val.to_string();
                        }
                    }
                    if ui
                        .selectable_label(self.template_custom, tl(lang, "set.filename_custom"))
                        .clicked()
                    {
                        self.template_custom = true;
                    }
                })
                .response
        });
        if self.template_custom {
            ui.add_space(4.0);
            ui.add(
                egui::TextEdit::singleline(&mut s.filename_template)
                    .hint_text("%(title)s")
                    .font(egui::TextStyle::Monospace)
                    .desired_width(f32::INFINITY)
                    .margin(egui::Margin::symmetric(10, 7)),
            );
        }
        // Live example of the resulting filename.
        ui.add_space(4.0);
        let ext = if s.default_kind == "audio" {
            s.default_audio_format.clone()
        } else {
            s.default_container.clone()
        };
        ui.horizontal(|ui| {
            crate::icons::show(ui, "chevron-right", 12.0, p.fg_dim);
            ui.add_space(2.0);
            ui.label(
                RichText::new(template_example(&s.filename_template, &ext))
                    .monospace()
                    .small()
                    .color(p.fg_dim),
            );
        });
        setting_row(ui, p, tl(lang, "set.embed_subs"), |ui| {
            toggle(ui, &mut s.default_embed_subs, p);
        });
        setting_row(ui, p, tl(lang, "set.embed_chapters"), |ui| {
            toggle(ui, &mut s.default_embed_chapters, p);
        });

        // Quality.
        ui.add_space(20.0);
        heading(ui, "sec.quality", "set.quality");
        setting_row(ui, p, tl(lang, "set.bitrate"), |ui| {
            combo_bare(
                ui,
                lang,
                "set.br",
                &mut s.audio_bitrate,
                &["best", "320", "256", "192", "128"],
            );
        });
        setting_row(ui, p, tl(lang, "set.vcodec"), |ui| {
            combo_bare(
                ui,
                lang,
                "set.vc",
                &mut s.video_codec,
                &["any", "h264", "h265", "vp9", "av1"],
            );
        });

        // Processing.
        ui.add_space(20.0);
        heading(ui, "sec.options", "set.options");
        setting_row(ui, p, tl(lang, "set.autotag"), |ui| {
            combo_bare(
                ui,
                lang,
                "set.at",
                &mut s.autotag_source,
                &["auto", "apple", "deezer", "musicbrainz"],
            );
        });
        ui.label(
            RichText::new(tl(lang, "set.autotag_desc"))
                .small()
                .color(p.fg_dim),
        );
        ui.add_space(6.0);
        setting_row(ui, p, tl(lang, "set.normalize"), |ui| {
            toggle(ui, &mut s.normalize_audio, p);
        });
        // Loudness target slider, shown only while normalization is on.
        if s.normalize_audio {
            // The note names the well-known standard only when the value lands on it,
            // instead of always reading "Spotify/YouTube".
            let note = match s.normalize_lufs {
                -23 => "EBU R128",
                -16 => "Apple Music",
                -14 => "Spotify/YouTube",
                _ => "",
            };
            egui::Frame::new()
                .fill(p.surface)
                .corner_radius(10)
                .inner_margin(egui::Margin::symmetric(12, 10))
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        ui.label(RichText::new(tl(lang, "set.loudness")).small().color(p.fg));
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            ui.label(
                                RichText::new(format!("{} LUFS", s.normalize_lufs))
                                    .small()
                                    .strong()
                                    .color(p.accent),
                            );
                            if !note.is_empty() {
                                ui.add_space(6.0);
                                ui.label(RichText::new(format!("· {note}")).small().color(p.fg_dim));
                            }
                        });
                    });
                    ui.add_space(8.0);
                    // A cleaner handle: a filled accent track up to a solid accent dot,
                    // on a slim rail (instead of egui's grey default).
                    ui.scope(|ui| {
                        let v = ui.visuals_mut();
                        v.widgets.inactive.bg_fill = p.accent;
                        v.widgets.inactive.bg_stroke = egui::Stroke::NONE;
                        v.widgets.hovered.bg_fill = p.accent;
                        v.widgets.hovered.bg_stroke = egui::Stroke::new(3.0, p.accent.gamma_multiply(0.3));
                        v.widgets.active.bg_fill = p.accent;
                        v.widgets.active.bg_stroke = egui::Stroke::new(3.0, p.accent.gamma_multiply(0.4));
                        v.selection.bg_fill = p.accent;
                        v.handle_shape = egui::style::HandleShape::Circle;
                        ui.spacing_mut().slider_width = ui.available_width() - 6.0;
                        ui.spacing_mut().slider_rail_height = 5.0;
                        ui.add(
                            egui::Slider::new(&mut s.normalize_lufs, -23..=-9)
                                .trailing_fill(true)
                                .show_value(false),
                        );
                    });
                });
            ui.add_space(6.0);
        }
        setting_row(ui, p, tl(lang, "set.nfo"), |ui| {
            toggle(ui, &mut s.nfo_sidecars, p);
        });
        setting_row(ui, p, tl(lang, "set.music_folders"), |ui| {
            toggle(ui, &mut s.music_folders, p);
        });
        setting_row(ui, p, tl(lang, "set.prefer_lossless"), |ui| {
            toggle(ui, &mut s.prefer_soundcloud_lossless, p);
        });
        setting_row(ui, p, tl(lang, "set.lyrics"), |ui| {
            toggle(ui, &mut s.fetch_lyrics, p);
        });

        // SponsorBlock.
        ui.add_space(20.0);
        heading(ui, "sec.sponsorblock", "set.sponsorblock");
        setting_row(ui, p, tl(lang, "set.sb_enabled"), |ui| {
            toggle(ui, &mut s.sponsorblock_enabled, p);
        });
        if s.sponsorblock_enabled {
            setting_row(ui, p, tl(lang, "set.sb_action"), |ui| {
                combo_bare(
                    ui,
                    lang,
                    "set.sba",
                    &mut s.sponsorblock_action,
                    &["remove", "mark"],
                );
            });
        }

        // Network & access.
        ui.add_space(20.0);
        heading(ui, "sec.network", "set.network");
        setting_row(ui, p, tl(lang, "set.proxy"), |ui| {
            let mut v = s.proxy.clone().unwrap_or_default();
            if ui
                .add(
                    egui::TextEdit::singleline(&mut v)
                        .hint_text("http://…")
                        .desired_width(220.0),
                )
                .changed()
            {
                s.proxy = (!v.is_empty()).then_some(v);
            }
        });
        setting_row(ui, p, tl(lang, "set.ratelimit"), |ui| {
            let mut v = s.rate_limit.clone().unwrap_or_default();
            if ui
                .add(
                    egui::TextEdit::singleline(&mut v)
                        .hint_text("1M")
                        .desired_width(220.0),
                )
                .changed()
            {
                s.rate_limit = (!v.is_empty()).then_some(v);
            }
        });
        setting_row(ui, p, tl(lang, "set.cookies"), |ui| {
            let mut v = s.cookies_from_browser.clone().unwrap_or_default();
            combo_bare(
                ui,
                lang,
                "set.ck",
                &mut v,
                &["", "chrome", "firefox", "chromium", "edge", "brave"],
            );
            s.cookies_from_browser = (!v.is_empty()).then_some(v);
        });
        // YouTube PO token — part of network access, as in the web UI.
        setting_row(ui, p, tl(lang, "set.potoken"), |ui| {
            combo_bare(
                ui,
                lang,
                "set.mode",
                &mut s.po_token_mode,
                &["off", "manual", "auto"],
            );
        });
        ui.label(
            RichText::new(tl(lang, "set.potoken_desc"))
                .small()
                .color(p.fg_dim),
        );
        ui.add_space(6.0);

        // Shortcuts.
        ui.add_space(20.0);
        heading(ui, "sec.shortcuts", "set.shortcuts");
        ui.add_space(8.0);
        let shortcuts: [(&str, &[&str]); 4] = [
            ("sc.focus_url", &["Ctrl", "L"]),
            ("sc.settings", &["Ctrl", ","]),
            ("sc.analyze", &["Enter"]),
            ("sc.close", &["Esc"]),
        ];
        for (key, keys) in shortcuts {
            ui.add_space(7.0);
            ui.horizontal(|ui| {
                ui.label(RichText::new(tl(lang, key)).color(p.fg));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    for k in keys.iter().rev() {
                        kbd_chip(ui, p, k);
                    }
                });
            });
        }
        ui.add_space(10.0);
        ui.label(RichText::new(tl(lang, "sc.note")).small().color(p.fg_dim));

        // Extension.
        ui.add_space(20.0);
        heading(ui, "sec.extension", "set.extension");
        ui.add_space(4.0);
        ui.label(RichText::new(tl(lang, "ext.intro")).color(p.fg_dim));
        if ext_row(ui, p, lang, "Firefox", "Mozilla Add-ons") {
            open_url("https://addons.mozilla.org/firefox/addon/send-to-yoink/");
        }
        if ext_row(ui, p, lang, "Chrome", "Chrome Web Store") {
            open_url("https://chromewebstore.google.com/detail/ccbngfpojjboddajeialdgppooagdhkp");
        }
        ui.add_space(10.0);
        ui.horizontal(|ui| {
            ui.label(RichText::new(tl(lang, "ext.other")).color(p.fg_dim));
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui
                    .add(egui::Button::new(RichText::new(tl(lang, "ext.manual")).small().color(p.accent)).frame(false))
                    .clicked()
                {
                    open_url("https://github.com/ayozetr/yoink-app/releases/tag/ext-latest");
                }
            });
        });
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            crate::icons::show(ui, "check", 15.0, p.accent);
            ui.add_space(4.0);
            ui.label(RichText::new(tl(lang, "ext.usage")).small().color(p.fg_dim));
        });

        // About.
        ui.add_space(20.0);
        heading(ui, "sec.about", "set.about");
        ui.add_space(12.0);
        ui.horizontal(|ui| {
            ui.add(
                egui::Image::from_bytes(
                    "bytes://app-icon.png",
                    include_bytes!("../assets/icon.png") as &[u8],
                )
                .fit_to_exact_size(egui::vec2(54.0, 54.0))
                .corner_radius(14),
            );
            ui.add_space(12.0);
            ui.vertical(|ui| {
                ui.label(RichText::new("Yoink").size(19.0).strong().color(p.fg));
                ui.label(RichText::new(tl(lang, "about.subtitle")).small().color(p.fg_dim));
                ui.label(
                    RichText::new(format!("v{}", env!("CARGO_PKG_VERSION")))
                        .monospace()
                        .size(11.0)
                        .color(p.fg_dim),
                );
            });
        });
        ui.add_space(14.0);
        // A full-width row: the label on the left, the update control pinned to the
        // right edge via an exact rect (egui's right_to_left layout misbehaves in
        // this section, so place the control explicitly).
        let mut recheck = false;
        let row_h = 30.0;
        let (row, _) =
            ui.allocate_exact_size(egui::vec2(ui.available_width(), row_h), egui::Sense::hover());
        // The row is laid out wider than the scroll viewport's clip rect, so pin the
        // control to the visible (clipped) right edge, not the row's right edge.
        let rx = row.right().min(ui.clip_rect().right() - 2.0);
        ui.painter().text(
            egui::pos2(row.left(), row.center().y),
            egui::Align2::LEFT_CENTER,
            tl(lang, "about.updates"),
            egui::FontId::proportional(14.0),
            p.fg,
        );
        if let Some(v) = self.update_available.clone() {
            let text = format!("  {} {v}  ", tl(lang, "about.view_release"));
            let galley = ui.painter().layout_no_wrap(
                text.clone(),
                egui::FontId::proportional(12.0),
                p.accent,
            );
            let bw = galley.size().x + 8.0;
            let br = egui::Rect::from_min_size(
                egui::pos2(rx - bw, row.center().y - 14.0),
                egui::vec2(bw, 28.0),
            );
            if ui
                .put(
                    br,
                    egui::Button::new(RichText::new(text).small().color(p.accent))
                        .fill(p.accent.gamma_multiply(0.16))
                        .corner_radius(255),
                )
                .clicked()
            {
                open_url("https://github.com/ayozetr/yoink-app/releases/latest");
            }
        } else if self.update_checking {
            ui.painter().text(
                egui::pos2(rx, row.center().y),
                egui::Align2::RIGHT_CENTER,
                tl(lang, "about.checking"),
                egui::FontId::proportional(12.0),
                p.fg_dim,
            );
        } else if self.update_checked {
            // "✓ al día", clickable to re-check.
            let text = tl(lang, "about.uptodate");
            let galley =
                ui.painter()
                    .layout_no_wrap(text.to_owned(), egui::FontId::proportional(12.0), p.ok);
            let tw = galley.size().x;
            let hit = egui::Rect::from_min_size(
                egui::pos2(rx - tw - 20.0, row.top()),
                egui::vec2(tw + 20.0, row_h),
            );
            let resp = ui.interact(hit, egui::Id::unique("recheck"), egui::Sense::click());
            if resp.hovered() {
                ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
            }
            ui.painter().text(
                egui::pos2(rx, row.center().y),
                egui::Align2::RIGHT_CENTER,
                text,
                egui::FontId::proportional(12.0),
                p.ok,
            );
            crate::icons::img("check", 14.0, p.ok).paint_at(
                ui,
                egui::Rect::from_min_size(
                    egui::pos2(rx - tw - 18.0, row.center().y - 7.0),
                    egui::vec2(14.0, 14.0),
                ),
            );
            recheck = resp.clicked();
        } else {
            let text = format!("  {}  ", tl(lang, "about.check"));
            let galley = ui.painter().layout_no_wrap(
                text.clone(),
                egui::FontId::proportional(12.0),
                p.fg,
            );
            let bw = galley.size().x + 8.0;
            let br = egui::Rect::from_min_size(
                egui::pos2(rx - bw, row.center().y - 14.0),
                egui::vec2(bw, 28.0),
            );
            recheck = ui
                .put(
                    br,
                    egui::Button::new(RichText::new(text).small().color(p.fg))
                        .stroke(egui::Stroke::new(1.0, p.line))
                        .fill(egui::Color32::TRANSPARENT)
                        .corner_radius(255),
                )
                .clicked();
        }
        if recheck {
            self.update_checking = true;
            self.backend.send(Cmd::CheckUpdate);
        }
        ui.add_space(8.0);
        if about_link_row(
            ui,
            p,
            "sparkles",
            RichText::new(tl(lang, "whatsnew.title")),
            None,
        ) {
            if self.whatsnew.is_empty() {
                self.backend.send(Cmd::LoadWhatsNew {
                    since: String::new(),
                });
            } else {
                self.whatsnew_open = true;
            }
        }
        if about_link_row(
            ui,
            p,
            "github",
            RichText::new(format!("{} ", tl(lang, "about.developed"))),
            Some("ayozetr"),
        ) {
            open_url("https://github.com/ayozetr");
        }
        if about_link_row(ui, p, "coffee", RichText::new(tl(lang, "about.donate")), None) {
            open_url("https://ko-fi.com/ayozetr");
        }
        ui.add_space(12.0);
        ui.horizontal(|ui| {
            if small_link(ui, p, tl(lang, "about.licenses")) {
                self.licenses_open = true;
            }
            ui.add_space(14.0);
            if small_link(ui, p, tl(lang, "about.terms")) {
                self.terms_open = true;
            }
        });

        ui.add_space(22.0);
        ui.horizontal(|ui| {
            let label = format!("  {}  ", tl(lang, "action.save"));
            let btn = egui::Button::new(RichText::new(label).color(p.accent_fg))
                .fill(p.accent)
                .corner_radius(9)
                .min_size(egui::vec2(0.0, 34.0));
            if ui.add(btn).clicked() {
                self.settings_note = None;
                set_autostart(s.launch_at_startup);
                self.backend.send(Cmd::SaveSettings(Box::new(s.clone())));
            }
            if self.settings_note.is_some() {
                ui.label(RichText::new(format!("✓ {}", tl(lang, "state.saved"))).color(p.ok));
            }
        });
        ui.add_space(20.0);

        if lang_sel != self.lang_mode {
            self.lang_mode = lang_sel;
            self.lang = lang_sel.unwrap_or_else(crate::i18n::detect);
            save_prefs(self.theme_mode, self.lang_mode);
        }
        self.active_section = active.into_inner();
        // Keep edits in memory until saved.
        self.settings = Some(s);
    }
}

/// Where the last-seen app version is recorded (for the "what's new" popup).
fn whatsnew_marker() -> Option<std::path::PathBuf> {
    let base = std::env::var("XDG_CONFIG_HOME")
        .ok()
        .filter(|s| !s.is_empty())
        .or_else(|| std::env::var("HOME").ok().map(|h| format!("{h}/.config")))?;
    Some(
        std::path::PathBuf::from(base)
            .join("yoink")
            .join("last-version"),
    )
}

/// Create or remove the XDG autostart entry for launch-at-startup.
fn set_autostart(enabled: bool) {
    let base = std::env::var("XDG_CONFIG_HOME")
        .ok()
        .filter(|s| !s.is_empty())
        .or_else(|| std::env::var("HOME").ok().map(|h| format!("{h}/.config")));
    let Some(base) = base else { return };
    let dir = std::path::PathBuf::from(base).join("autostart");
    let path = dir.join("yoink.desktop");
    if enabled {
        // The real launchable path, not a bare name: the AppImage ($APPIMAGE), or
        // this executable — `yoink-desktop` isn't on $PATH for a portable build.
        let exec = std::env::var_os("APPIMAGE")
            .map(std::path::PathBuf::from)
            .or_else(|| std::env::current_exe().ok())
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_else(|| "yoink-desktop".into());
        let _ = std::fs::create_dir_all(&dir);
        let _ = std::fs::write(
            &path,
            format!(
                "[Desktop Entry]\nType=Application\nName=Yoink\nExec={exec} %u\n\
                 Icon=yoink\nTerminal=false\nX-GNOME-Autostart-enabled=true\n"
            ),
        );
    } else {
        let _ = std::fs::remove_file(&path);
    }
}

/// Fire a desktop notification for a finished download (off the UI thread, since
/// the D-Bus call can block briefly).
fn notify_done(verb: &str, path: &str) {
    let name = std::path::Path::new(path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("")
        .to_string();
    let body = format!("{verb}: {name}");
    std::thread::spawn(move || {
        let _ = notify_rust::Notification::new()
            .summary("Yoink")
            .body(&body)
            .show();
    });
}

/// A relative time ("hace 3 h" / "3 h ago") from an RFC3339 timestamp.
fn relative(iso: &str, lang: Lang) -> String {
    use chrono::{DateTime, Utc};
    let Ok(dt) = DateTime::parse_from_rfc3339(iso) else {
        return iso.chars().take(10).collect();
    };
    let s = (Utc::now() - dt.with_timezone(&Utc)).num_seconds().max(0);
    match (s, lang) {
        (s, _) if s < 60 => tl(lang, "time.now").to_string(),
        (s, Lang::Es) if s < 3600 => format!("hace {} min", s / 60),
        (s, Lang::En) if s < 3600 => format!("{} min ago", s / 60),
        (s, Lang::Es) if s < 86400 => format!("hace {} h", s / 3600),
        (s, Lang::En) if s < 86400 => format!("{} h ago", s / 3600),
        (s, Lang::Es) if s < 604800 => format!("hace {} d", s / 86400),
        (s, Lang::En) if s < 604800 => format!("{} d ago", s / 86400),
        _ => iso.chars().take(10).collect(),
    }
}

/// Heuristic: looks like a link (so analyze it) rather than a search query.
fn is_url(s: &str) -> bool {
    let s = s.trim();
    s.starts_with("http")
        || s.contains("://")
        || (s.contains('.') && !s.contains(' ') && s.len() > 3)
}

fn human_bytes(n: i64) -> String {
    const U: [&str; 5] = ["B", "KB", "MB", "GB", "TB"];
    let mut v = n as f64;
    let mut i = 0;
    while v >= 1024.0 && i < U.len() - 1 {
        v /= 1024.0;
        i += 1;
    }
    if i == 0 {
        format!("{n} B")
    } else {
        format!("{v:.1} {}", U[i])
    }
}

/// A pill switch (the settings toggle), violet when on.
fn toggle(ui: &mut egui::Ui, on: &mut bool, p: theme::Palette) -> egui::Response {
    let (rect, mut resp) = ui.allocate_exact_size(egui::vec2(38.0, 22.0), egui::Sense::click());
    if resp.clicked() {
        *on = !*on;
        resp.mark_changed();
    }
    let bg = if *on { p.accent } else { p.surface_hi };
    ui.painter().rect_filled(rect, 11.0, bg);
    let knob_x = if *on {
        rect.right() - 11.0
    } else {
        rect.left() + 11.0
    };
    ui.painter().circle_filled(
        egui::pos2(knob_x, rect.center().y),
        8.0,
        egui::Color32::WHITE,
    );
    resp
}

thread_local! {
    // True when the next `setting_row` is the first in its section (so it draws
    // no divider above it). `settings_section` resets it.
    static SETTINGS_FIRST_ROW: std::cell::Cell<bool> = const { std::cell::Cell::new(true) };
}

/// Call at the start of each settings section so its first row skips the divider.
fn settings_section() {
    SETTINGS_FIRST_ROW.with(|f| f.set(true));
}

/// Mark that a custom (non-`setting_row`) row was rendered, so the next
/// `setting_row` draws a divider above it.
fn settings_row_rendered() {
    SETTINGS_FIRST_ROW.with(|f| f.set(false));
}

/// A settings row: label on the left, control on the right, with a hairline
/// divider above it (skipped for the first row of a section).
fn setting_row(ui: &mut egui::Ui, p: theme::Palette, label: &str, add: impl FnOnce(&mut egui::Ui)) {
    // A hairline between rows (as in the web), skipped for the first row of a
    // section.
    if !SETTINGS_FIRST_ROW.with(|f| f.replace(false)) {
        ui.add_space(4.0);
        let (sep, _) =
            ui.allocate_exact_size(egui::vec2(ui.available_width(), 1.0), egui::Sense::hover());
        ui.painter().rect_filled(sep, 0.0, p.line.gamma_multiply(0.5));
    }
    ui.add_space(12.0);
    ui.horizontal(|ui| {
        // Give the row some height so a control (a combo) is centered with room
        // above and below, instead of filling the row flush to the clip edge
        // where its focused/hovered border would be cut.
        ui.set_min_height(34.0);
        ui.label(RichText::new(label).color(p.fg));
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), add);
    });
}

/// A small keycap chip (monospace key name on a rounded inset), as in the web's
/// Shortcuts list. Laid out right-to-left, so callers add keys in reverse.
fn kbd_chip(ui: &mut egui::Ui, p: theme::Palette, label: &str) {
    let font = egui::FontId::new(11.0, egui::FontFamily::Monospace);
    let galley = ui
        .painter()
        .layout_no_wrap(label.to_string(), font.clone(), p.fg_dim);
    let w = (galley.size().x + 14.0).max(22.0);
    let (rect, _) = ui.allocate_exact_size(egui::vec2(w, 22.0), egui::Sense::hover());
    ui.painter().rect_filled(rect, 6.0, p.surface_hi);
    ui.painter().rect_stroke(
        rect,
        6.0,
        egui::Stroke::new(1.0, p.line),
        egui::StrokeKind::Inside,
    );
    ui.painter()
        .text(rect.center(), egui::Align2::CENTER_CENTER, label, font, p.fg);
    ui.add_space(5.0);
}

/// An extension row: a browser name + store caption on the left, an "Install"
/// pill on the right. Returns true when the pill is clicked.
fn ext_row(ui: &mut egui::Ui, p: theme::Palette, lang: Lang, name: &str, store: &str) -> bool {
    let mut clicked = false;
    ui.add_space(10.0);
    ui.horizontal(|ui| {
        ui.vertical(|ui| {
            ui.label(RichText::new(name).color(p.fg));
            ui.label(RichText::new(store).small().color(p.fg_dim));
        });
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            let btn = egui::Button::image_and_text(
                crate::icons::img("download", 13.0, p.accent),
                RichText::new(tl(lang, "ext.get")).small().color(p.accent),
            )
            .fill(p.accent.gamma_multiply(0.16))
            .corner_radius(255)
            .min_size(egui::vec2(0.0, 28.0));
            clicked = ui.add(btn).clicked();
        });
    });
    ui.add_space(4.0);
    let (sep, _) = ui.allocate_exact_size(egui::vec2(ui.available_width(), 1.0), egui::Sense::hover());
    ui.painter().rect_filled(sep, 0.0, p.line.gamma_multiply(0.5));
    clicked
}

/// An "About" link row: an accent icon, a label, and a chevron that nudges right
/// on hover. Returns true when clicked.
fn about_link_row(
    ui: &mut egui::Ui,
    p: theme::Palette,
    icon: &str,
    text: RichText,
    bold_tail: Option<&str>,
) -> bool {
    let w = ui.available_width();
    let (rect, resp) = ui.allocate_exact_size(egui::vec2(w, 40.0), egui::Sense::click());
    let hov = resp.hovered();
    if hov {
        ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
    }
    let tcol = if hov { p.accent } else { p.fg };
    let ir = egui::Rect::from_min_size(
        egui::pos2(rect.left(), rect.center().y - 8.0),
        egui::vec2(16.0, 16.0),
    );
    crate::icons::img(icon, 16.0, p.accent).paint_at(ui, ir);
    let main = ui.painter().text(
        egui::pos2(rect.left() + 26.0, rect.center().y),
        egui::Align2::LEFT_CENTER,
        text.text(),
        egui::FontId::proportional(14.0),
        tcol,
    );
    // An emphasized trailing word (e.g. the developer's handle), in semibold.
    if let Some(tail) = bold_tail {
        ui.painter().text(
            egui::pos2(main.right() + 5.0, rect.center().y),
            egui::Align2::LEFT_CENTER,
            tail,
            egui::FontId::new(14.0, crate::fonts::semibold()),
            tcol,
        );
    }
    let chev = rect.right() - 14.0 + if hov { 2.0 } else { 0.0 };
    crate::icons::img("chevron", 14.0, p.fg_dim).paint_at(
        ui,
        egui::Rect::from_min_size(egui::pos2(chev, rect.center().y - 7.0), egui::vec2(14.0, 14.0)),
    );
    // Hairline separator, centered in the inter-row gap (egui adds item_spacing
    // above this rect) so the row's text sits centered between two separators.
    let sep_y = rect.top() - ui.spacing().item_spacing.y / 2.0;
    ui.painter().rect_filled(
        egui::Rect::from_min_size(egui::pos2(rect.left(), sep_y), egui::vec2(w, 1.0)),
        0.0,
        p.line.gamma_multiply(0.5),
    );
    resp.clicked()
}

/// A small inline text link that brightens from dim to full on hover.
fn small_link(ui: &mut egui::Ui, p: theme::Palette, text: &str) -> bool {
    let font = egui::FontId::proportional(12.0);
    let galley = ui
        .painter()
        .layout_no_wrap(text.to_owned(), font.clone(), p.fg_dim);
    let (rect, resp) =
        ui.allocate_exact_size(galley.size() + egui::vec2(2.0, 6.0), egui::Sense::click());
    let hov = resp.hovered();
    if hov {
        ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
    }
    ui.painter().text(
        rect.left_center() + egui::vec2(1.0, 0.0),
        egui::Align2::LEFT_CENTER,
        text,
        font,
        if hov { p.fg } else { p.fg_dim },
    );
    resp.clicked()
}

/// Render a small subset of Markdown (headings, bullets, paragraphs) as egui
/// labels — enough for the release notes and the legal/licenses text.
fn render_markdown(ui: &mut egui::Ui, p: theme::Palette, body: &str) {
    // Strip the inline markers we don't render (bold/code) so they don't show raw.
    let clean = |s: &str| s.replace("**", "").replace('`', "");
    for line in body.lines() {
        let t = line.trim();
        if let Some(h) = t.strip_prefix("## ").or_else(|| t.strip_prefix("### ")) {
            ui.add_space(6.0);
            ui.label(
                RichText::new(clean(h))
                    .family(crate::fonts::semibold())
                    .color(p.fg),
            );
            ui.add_space(2.0);
        } else if let Some(h) = t.strip_prefix("# ") {
            ui.add_space(6.0);
            ui.label(
                RichText::new(clean(h))
                    .size(15.0)
                    .family(crate::fonts::semibold())
                    .color(p.fg),
            );
            ui.add_space(2.0);
        } else if let Some(b) = t.strip_prefix("- ").or_else(|| t.strip_prefix("* ")) {
            ui.label(RichText::new(format!("•  {}", clean(b))).color(p.fg_dim));
        } else if !t.is_empty() {
            // A line that is entirely bold reads as emphasis.
            if t.len() > 4 && t.starts_with("**") && t.ends_with("**") {
                ui.label(
                    RichText::new(clean(t))
                        .family(crate::fonts::semibold())
                        .color(p.fg),
                );
            } else {
                ui.label(RichText::new(clean(t)).color(p.fg_dim));
            }
        } else {
            ui.add_space(4.0);
        }
    }
}

/// A big Gloock number with a small uppercase caption, as in the history header.
fn big_stat(ui: &mut egui::Ui, p: theme::Palette, value: &str, label: &str) {
    ui.vertical(|ui| {
        ui.label(
            RichText::new(value)
                .size(28.0)
                .family(crate::fonts::display())
                .color(p.fg),
        );
        ui.label(
            RichText::new(label.to_uppercase())
                .size(10.0)
                .color(p.fg_dim),
        );
    });
}

/// The format label for a history row's badge (file extension, else the kind).
fn badge_label(e: &HistoryEntry) -> String {
    e.filepath
        .as_deref()
        .and_then(|p| std::path::Path::new(p).extension())
        .and_then(|x| x.to_str())
        .map(str::to_uppercase)
        .unwrap_or_else(|| e.kind.to_uppercase())
}

/// A small violet rounded badge with the format label (e.g. MP3), as in history.
fn fmt_badge(ui: &mut egui::Ui, p: theme::Palette, label: &str) {
    let (rect, _) = ui.allocate_exact_size(egui::vec2(42.0, 42.0), egui::Sense::hover());
    ui.painter()
        .rect_filled(rect, 9.0, p.accent.gamma_multiply(0.85));
    ui.painter().text(
        rect.center(),
        egui::Align2::CENTER_CENTER,
        label,
        egui::FontId::new(10.0, egui::FontFamily::Proportional),
        p.accent_fg,
    );
}

/// A raised surface card with padding and a hairline border.
/// A flat, de-boxed content block (the v4 look): no border or fill, just a little
/// vertical breathing room. Grouping comes from whitespace, not boxes.
fn card(ui: &mut egui::Ui, _p: theme::Palette, add: impl FnOnce(&mut egui::Ui)) {
    egui::Frame::new()
        .inner_margin(egui::Margin::symmetric(0, 6))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            add(ui);
        });
}

/// A labelled dropdown bound to a string from a fixed option list. `id` is a
/// stable salt so the widget keeps its identity when the label is translated.
/// Just the dropdown (no label), for the right slot of a settings row.
/// A human label for a raw selector value (formats upper-cased, qualities as
/// "1080p"/"320 kbps", the special ones translated) — so no combo shows a bare
/// backend token like "best" or "mp4".
fn opt_label(lang: Lang, v: &str) -> String {
    let t =
        |en: &'static str, es: &'static str| (if lang == Lang::En { en } else { es }).to_string();
    match v {
        "" => t("None", "Ninguna"),
        "video" => tl(lang, "kind.video").to_string(),
        "audio" => tl(lang, "kind.audio").to_string(),
        "best" => t("Best available", "Mejor disponible"),
        "off" => t("Off", "Desactivado"),
        "manual" => "Manual".to_string(),
        "auto" => t("Auto", "Automático"),
        "any" => t("Any", "Cualquiera"),
        "remove" => t("Remove", "Eliminar"),
        "mark" => t("Mark as chapters", "Marcar como capítulos"),
        "apple" => "Apple Music".to_string(),
        "deezer" => "Deezer".to_string(),
        "musicbrainz" => "MusicBrainz".to_string(),
        "chrome" => "Chrome".to_string(),
        "firefox" => "Firefox".to_string(),
        "chromium" => "Chromium".to_string(),
        "edge" => "Edge".to_string(),
        "brave" => "Brave".to_string(),
        "mp4" => "MP4".to_string(),
        "mov" => "MOV".to_string(),
        "mkv" => "MKV".to_string(),
        "webm" => "WebM".to_string(),
        "mp3" => "MP3".to_string(),
        "m4a" => "M4A".to_string(),
        "opus" => "Opus".to_string(),
        "flac" => "FLAC".to_string(),
        "wav" => "WAV".to_string(),
        "h264" => "H.264".to_string(),
        "h265" => "H.265".to_string(),
        "vp9" => "VP9".to_string(),
        "av1" => "AV1".to_string(),
        "2160" | "1440" | "1080" | "720" | "480" | "360" => format!("{v}p"),
        "320" | "256" | "192" | "128" => format!("{v} kbps"),
        _ => v.to_string(),
    }
}

/// An advanced-options row: a small uppercase label on the left, controls on
/// the right (the web's "FORMAT / TRIM / …" rows).
fn adv_row(ui: &mut egui::Ui, p: theme::Palette, label: &str, content: impl FnOnce(&mut egui::Ui)) {
    ui.horizontal(|ui| {
        ui.allocate_ui_with_layout(
            egui::vec2(88.0, 24.0),
            egui::Layout::left_to_right(egui::Align::Center),
            |ui| {
                ui.label(RichText::new(label.to_uppercase()).small().color(p.fg_dim));
            },
        );
        ui.add_space(10.0);
        content(ui);
    });
    ui.add_space(10.0);
}

/// A consistent width for Settings dropdowns, so the select column lines up
/// (like the web's fixed-width control column) instead of hugging each label.
const CTRL_COMBO_W: f32 = 168.0;

/// Legal/attribution text shown in the About modals, bundled from the repo root
/// (English is the canonical version, as on the web).
const DISCLAIMER_MD: &str = include_str!("../../DISCLAIMER.md");
const LICENSES_MD: &str = include_str!("../../OPEN_SOURCE_LICENSES.md");

/// Filename-template presets as `(yt-dlp value, display label)`, mirroring the web.
/// The `%(autotag...)s` sentinels are renamed to the tagged metadata by the backend.
const TEMPLATE_PRESETS: [(&str, &str); 6] = [
    ("%(title)s", "%(title)s"),
    ("%(uploader)s - %(title)s", "%(uploader)s - %(title)s"),
    ("%(upload_date)s - %(title)s", "%(upload_date)s - %(title)s"),
    ("%(title)s [%(id)s]", "%(title)s [%(id)s]"),
    ("%(autotag)s", "%(artist)s - %(title)s (auto-tag)"),
    ("%(autotag_ta)s", "%(title)s - %(artist)s (auto-tag)"),
];

/// Render a yt-dlp output template as a concrete sample filename for a live preview.
fn template_example(tpl: &str, ext: &str) -> String {
    match tpl {
        "%(autotag)s" => "The Notorious B.I.G. - Big Poppa.mp3".to_string(),
        "%(autotag_ta)s" => "Big Poppa - The Notorious B.I.G..mp3".to_string(),
        _ => {
            let sample = |k: &str| match k {
                "title" => "Big Poppa (Official Music Video)",
                "uploader" => "The Notorious B.I.G.",
                "upload_date" => "20110906",
                "id" => "phaJXp_zMYM",
                "playlist_index" => "01",
                "ext" => "mp3",
                _ => "",
            };
            // Replace each %(key)s token; leave unknown keys as-is.
            let mut out = String::new();
            let mut rest = if tpl.is_empty() { "%(title)s" } else { tpl };
            while let Some(start) = rest.find("%(") {
                out.push_str(&rest[..start]);
                rest = &rest[start..];
                if let Some(end) = rest.find(")s") {
                    let key = &rest[2..end];
                    let v = sample(key);
                    if v.is_empty() {
                        out.push_str(&rest[..end + 2]);
                    } else {
                        out.push_str(v);
                    }
                    rest = &rest[end + 2..];
                } else {
                    break;
                }
            }
            out.push_str(rest);
            format!("{out}.{ext}")
        }
    }
}

/// A text field for a filesystem path with a folder-picker button inside it (right
/// edge), opening the OS directory chooser. Returns true when the button is clicked.
fn path_field(ui: &mut egui::Ui, p: theme::Palette, value: &mut String) -> bool {
    let mut pick = false;
    egui::Frame::new()
        .fill(p.surface_hi)
        .stroke(egui::Stroke::new(1.0, p.line))
        .corner_radius(8)
        .inner_margin(egui::Margin::symmetric(10, 7))
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.set_min_height(22.0);
                let avail = ui.available_width();
                ui.add_sized(
                    [avail - 26.0, 22.0],
                    egui::TextEdit::singleline(value).frame(egui::Frame::NONE),
                );
                let r = ui.add(
                    crate::icons::img("folder", 18.0, p.fg_dim).sense(egui::Sense::click()),
                );
                if r.hovered() {
                    ui.ctx().set_cursor_icon(egui::CursorIcon::PointingHand);
                }
                pick = r.clicked();
            });
        });
    pick
}

/// Make a combo popup's scrollbar invisible (the list still scrolls by wheel),
/// matching the web's borderless selects. Applied per-combo via `popup_style`, so
/// other scroll areas (history, logs, the what's-new modal) keep their scrollbar.
fn hide_combo_scrollbar(style: &mut egui::Style) {
    style.spacing.scroll.dormant_handle_opacity = 0.0;
    style.spacing.scroll.interact_handle_opacity = 0.0;
    style.spacing.scroll.active_handle_opacity = 0.0;
}

/// Run a combo with egui's own 1px border muted, then paint our own border
/// snapped to whole physical pixels and drawn inside the rect. egui's stroke
/// straddles the pixel grid, so at a fractional pixels_per_point (e.g. a 1.15
/// desktop scale × our 1.2 zoom ≈ 1.38) one edge renders blurry/thin and the
/// border looks "cut"; a snapped inside-stroke keeps all four edges crisp.
fn crisp_combo(
    ui: &mut egui::Ui,
    p: theme::Palette,
    show: impl FnOnce(&mut egui::Ui) -> egui::Response,
) {
    ui.scope(|ui| {
        let w = &mut ui.visuals_mut().widgets;
        w.inactive.bg_stroke = egui::Stroke::NONE;
        w.hovered.bg_stroke = egui::Stroke::NONE;
        w.active.bg_stroke = egui::Stroke::NONE;
        w.open.bg_stroke = egui::Stroke::NONE;
        let r = show(ui);
        let ppp = ui.ctx().pixels_per_point();
        let snap = |v: f32| (v * ppp).round() / ppp;
        let rect = egui::Rect::from_min_max(
            egui::pos2(snap(r.rect.min.x), snap(r.rect.min.y)),
            egui::pos2(snap(r.rect.max.x), snap(r.rect.max.y)),
        );
        let col = if r.hovered() || r.has_focus() {
            p.accent
        } else {
            p.line
        };
        ui.painter().rect_stroke(
            rect,
            6.0,
            egui::Stroke::new(1.0, col),
            egui::StrokeKind::Inside,
        );
    });
}

/// Style a combo's open popup like the web's Select menu: each option highlights
/// with a fill only (selected = accent tint, hovered = a lighter surface) and no
/// 1px outline. An outline's stroke straddles the physical pixel grid at a
/// fractional pixels_per_point and renders one edge thin, so some options looked
/// "cut"; a fill has no edge to cut. Call at the top of a combo's `show_ui`.
fn style_combo_items(ui: &mut egui::Ui) {
    let p = theme::palette(ui.visuals().dark_mode);
    ui.visuals_mut().selection.stroke = egui::Stroke::NONE;
    ui.visuals_mut().selection.bg_fill = p.accent.gamma_multiply(0.15);
    let w = &mut ui.visuals_mut().widgets;
    w.inactive.bg_stroke = egui::Stroke::NONE;
    w.hovered.bg_stroke = egui::Stroke::NONE;
    w.hovered.bg_fill = p.surface_hi;
    w.hovered.weak_bg_fill = p.surface_hi;
    w.active.bg_stroke = egui::Stroke::NONE;
    w.active.bg_fill = p.surface_hi;
    w.active.weak_bg_fill = p.surface_hi;
}

fn combo_bare(ui: &mut egui::Ui, lang: Lang, id: &str, value: &mut String, options: &[&str]) {
    let p = theme::palette(ui.visuals().dark_mode);
    crisp_combo(ui, p, |ui| {
        egui::ComboBox::from_id_salt(id)
            .popup_style(hide_combo_scrollbar.into())
            .width(CTRL_COMBO_W)
            .selected_text(opt_label(lang, value))
            .show_ui(ui, |ui| {
                style_combo_items(ui);
                for opt in options {
                    ui.selectable_value(value, opt.to_string(), opt_label(lang, opt));
                }
            })
            .response
    });
}
