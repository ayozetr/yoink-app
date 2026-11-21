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
    source: QSource,
    status: QStatus,
    progress: f32,
}

pub struct App {
    backend: Backend,
    minter: crate::minter::Minter,
    dark: bool,
    lang: Lang,
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
    advanced_open: bool,
    supported_open: bool,
    update_available: Option<String>,
    update_dismissed: bool,
    whatsnew: Vec<(String, String)>,
    whatsnew_open: bool,
    deeplink_rx: std::sync::mpsc::Receiver<String>,
    tray_rx: std::sync::mpsc::Receiver<crate::tray::TrayMsg>,
    shot: Option<(String, std::time::Instant)>, // (output path, started) for YOINK_SHOT
}

impl App {
    pub fn new(
        cc: &eframe::CreationContext<'_>,
        pending: Option<String>,
        deeplink_rx: std::sync::mpsc::Receiver<String>,
        tray_rx: std::sync::mpsc::Receiver<crate::tray::TrayMsg>,
    ) -> App {
        let dark = true;
        crate::fonts::install(&cc.egui_ctx);
        theme::apply(&cc.egui_ctx, dark);
        // Enables egui::Image to load remote thumbnails (JPEG/PNG/WebP over http).
        egui_extras::install_image_loaders(&cc.egui_ctx);
        let mut app = App {
            backend: Backend::spawn(cc.egui_ctx.clone()),
            minter: crate::minter::Minter::new(crate::api::port()),
            dark,
            lang: crate::i18n::detect(),
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
            advanced_open: false,
            supported_open: false,
            update_available: None,
            update_dismissed: false,
            whatsnew: Vec::new(),
            whatsnew_open: false,
            deeplink_rx,
            tray_rx,
            shot: std::env::var("YOINK_SHOT")
                .ok()
                .filter(|s| !s.is_empty())
                .map(|p| (p, std::time::Instant::now())),
        };
        // A link the app was launched with (yoink://…) analyzes straight away.
        if let Some(url) = pending {
            app.url = url;
            app.analyze();
        }
        if std::env::var("YOINK_FAKE_UPDATE").is_ok() {
            app.update_available = Some("4.5.0".into());
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
        if std::env::var("YOINK_SHOT_SITES").is_ok() {
            app.supported_open = true;
        }
        if let Ok(sec) = std::env::var("YOINK_SHOT_SCROLL") {
            app.tab = Tab::Ajustes;
            app.settings_scroll_to = Some(sec);
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
                    self.settings = Some(*s);
                }
                Evt::SettingsSaved => self.settings_note = Some("Guardado".into()),
                Evt::UpdateAvailable { version } => self.update_available = Some(version),
                Evt::WhatsNew(entries) => {
                    if !entries.is_empty() {
                        self.whatsnew = entries;
                        // Don't pop it over a screenshot capture (unless forced).
                        self.whatsnew_open =
                            self.shot.is_none() || std::env::var("YOINK_SHOT_WHATSNEW").is_ok();
                    }
                }
                Evt::History(h) => self.history = h,
                Evt::Logs { path, content } => {
                    self.logs_path = path;
                    self.logs_text = content;
                }
                Evt::Analyzing => self.status = Status::Analyzing,
                Evt::Info(v) => {
                    self.preview = Preview::Video(v);
                    self.status = Status::Idle;
                    self.search_results.clear();
                }
                Evt::SearchResults(r) => self.search_results = r,
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
                self.backend.send(Cmd::Download(DownloadReq {
                    url: url.clone(),
                    quality: (kind == "video").then(|| it.quality.clone()),
                    kind,
                    container: it.container.clone(),
                    audio_format: it.audio.clone(),
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

impl eframe::App for App {
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
                crate::tray::TrayMsg::Quit => std::process::exit(0),
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

        egui::Panel::top("topbar")
            .frame(
                egui::Frame::new()
                    .fill(p.surface)
                    .inner_margin(egui::Margin::symmetric(16, 10)),
            )
            .show(ui, |ui| {
                ui.vertical(|ui| {
                    // Brand: a violet logo tile + the Gloock wordmark.
                    ui.horizontal(|ui| {
                        egui::Frame::new()
                            .fill(p.accent)
                            .corner_radius(6)
                            .inner_margin(egui::Margin::same(4))
                            .show(ui, |ui| crate::icons::show(ui, "music", 14.0, p.accent_fg));
                        ui.add_space(7.0);
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
                            let btn = egui::Button::image_and_text(
                                crate::icons::img(ic, 14.0, fg),
                                RichText::new(tl(lang, key)).size(13.0).color(fg),
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
                .frame(
                    egui::Frame::new()
                        .fill(p.accent.gamma_multiply(0.18))
                        .inner_margin(egui::Margin::symmetric(16, 8)),
                )
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        crate::icons::show(ui, "download", 15.0, p.accent);
                        ui.add_space(6.0);
                        ui.label(
                            RichText::new(format!("{} {version}", tl(lang, "update.available")))
                                .color(p.fg),
                        );
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
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
                            if ui
                                .add(
                                    egui::Button::new(
                                        RichText::new(tl(lang, "update.view")).color(p.accent_fg),
                                    )
                                    .fill(p.accent)
                                    .corner_radius(8),
                                )
                                .clicked()
                            {
                                let _ = std::process::Command::new("xdg-open")
                                    .arg("https://github.com/ayozetr/yoink-app/releases/latest")
                                    .spawn();
                            }
                        });
                    });
                });
        }

        // Settings "on this page" nav (sticky right column).
        if self.tab == Tab::Ajustes {
            egui::Panel::right("settings-nav")
                .resizable(false)
                .exact_size(210.0)
                .frame(
                    egui::Frame::new()
                        .fill(p.canvas)
                        .inner_margin(egui::Margin::symmetric(20, 24)),
                )
                .show(ui, |ui| {
                    ui.set_width(170.0);
                    ui.label(
                        RichText::new(tl(lang, "set.onpage"))
                            .small()
                            .color(p.fg_dim),
                    );
                    ui.add_space(8.0);
                    for (key, label) in [
                        ("sec.general", "set.general"),
                        ("sec.downloads", "set.downloads"),
                        ("sec.potoken", "set.potoken"),
                        ("sec.quality", "set.quality"),
                        ("sec.options", "set.options"),
                        ("sec.sponsorblock", "set.sponsorblock"),
                        ("sec.network", "set.network"),
                    ] {
                        if ui
                            .add(
                                egui::Button::new(RichText::new(tl(lang, label)).color(p.fg_dim))
                                    .fill(egui::Color32::TRANSPARENT)
                                    .frame(false),
                            )
                            .clicked()
                        {
                            self.settings_scroll_to = Some(key.to_string());
                        }
                    }
                });
        }

        egui::CentralPanel::default()
            .frame(
                egui::Frame::new()
                    .fill(p.canvas)
                    .inner_margin(egui::Margin::same(20)),
            )
            .show(ui, |ui| {
                egui::ScrollArea::vertical().show(ui, |ui| {
                    // A centered column with LEFT-aligned content (like the web UI).
                    let wide = self.tab == Tab::Ajustes;
                    let w = (if wide { 720.0_f32 } else { 640.0 }).min(ui.available_width() - 48.0);
                    let pad = ((ui.available_width() - w) / 2.0).max(0.0);
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

        // Supported-sites dialog — a custom modal: a dimmed backdrop + a centred,
        // title-bar-less panel (globe + Gloock title, bordered tiles), like the web.
        if self.supported_open {
            let screen = ctx
                .input(|i| i.raw.screen_rect)
                .unwrap_or(egui::Rect::from_min_size(
                    egui::Pos2::ZERO,
                    egui::vec2(2400.0, 1600.0),
                ));
            // Dimmed backdrop (shown first so the panel layers on top); click to close.
            let dim = egui::Area::new(egui::Id::unique("sites_dim"))
                .fixed_pos(screen.min)
                .show(&ctx, |ui| {
                    ui.painter()
                        .rect_filled(screen, 0.0, egui::Color32::from_black_alpha(170));
                    ui.allocate_response(screen.size(), egui::Sense::click())
                });
            if dim.inner.clicked() {
                self.supported_open = false;
            }
            egui::Window::new("sites")
                .title_bar(false)
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
                .frame(modal_frame(p))
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
                    // A 4-column grid of clickable logo + name tiles (no scroll, so
                    // nothing is clipped and there's no scrollbar), each lightening
                    // and gaining an accent border on hover.
                    let lighten = |c: egui::Color32, d: u8| {
                        egui::Color32::from_rgb(
                            c.r().saturating_add(d),
                            c.g().saturating_add(d),
                            c.b().saturating_add(d),
                        )
                    };
                    let cols = 4;
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
                    ui.add_space(10.0);
                    ui.vertical_centered(|ui| {
                        ui.label(
                            RichText::new(tl(lang, "sites.footer"))
                                .small()
                                .color(p.fg_dim),
                        );
                    });
                });
        }

        // "What's new" popup after an update — same custom modal look as the
        // supported-sites dialog (dimmed backdrop + title-bar-less panel).
        if self.whatsnew_open {
            let screen = ctx
                .input(|i| i.raw.screen_rect)
                .unwrap_or(egui::Rect::from_min_size(
                    egui::Pos2::ZERO,
                    egui::vec2(2400.0, 1600.0),
                ));
            let dim = egui::Area::new(egui::Id::unique("whatsnew_dim"))
                .fixed_pos(screen.min)
                .show(&ctx, |ui| {
                    ui.painter()
                        .rect_filled(screen, 0.0, egui::Color32::from_black_alpha(170));
                    ui.allocate_response(screen.size(), egui::Sense::click())
                });
            if dim.inner.clicked() {
                self.whatsnew_open = false;
            }
            egui::Window::new("whatsnew")
                .title_bar(false)
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
                .frame(modal_frame(p))
                .show(&ctx, |ui| {
                    ui.set_width(520.0);
                    ui.horizontal(|ui| {
                        crate::icons::show(ui, "sparkles", 18.0, p.accent);
                        ui.add_space(8.0);
                        ui.label(
                            RichText::new(tl(lang, "whatsnew.title"))
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
                            for (ver, notes) in &self.whatsnew {
                                ui.label(
                                    RichText::new(ver)
                                        .size(17.0)
                                        .family(crate::fonts::display())
                                        .color(p.fg),
                                );
                                ui.add_space(6.0);
                                for line in notes.lines() {
                                    let t = line.trim();
                                    if let Some(h) = t.strip_prefix("## ") {
                                        ui.add_space(4.0);
                                        ui.label(RichText::new(h).strong().color(p.fg));
                                    } else if let Some(h) = t.strip_prefix("# ") {
                                        ui.add_space(4.0);
                                        ui.label(RichText::new(h).size(15.0).strong().color(p.fg));
                                    } else if let Some(b) =
                                        t.strip_prefix("- ").or_else(|| t.strip_prefix("* "))
                                    {
                                        ui.label(RichText::new(format!("•  {b}")).color(p.fg_dim));
                                    } else if !t.is_empty() {
                                        ui.label(RichText::new(t).color(p.fg_dim));
                                    } else {
                                        ui.add_space(4.0);
                                    }
                                }
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
        }

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
        ui.add_space(16.0);

        // URL bar: a rounded pill field + a soft-violet Analyze button to the right.
        let analyzing = matches!(self.status, Status::Analyzing);
        ui.horizontal(|ui| {
            let total = ui.available_width();
            egui::Frame::new()
                .fill(p.surface_hi)
                .stroke(egui::Stroke::new(1.0, p.line))
                .corner_radius(10)
                .inner_margin(egui::Margin::symmetric(10, 7))
                .show(ui, |ui| {
                    ui.set_width(total - 128.0);
                    ui.horizontal(|ui| {
                        let red = if self.source == "soundcloud" {
                            egui::Color32::from_rgb(255, 136, 0)
                        } else {
                            egui::Color32::from_rgb(237, 70, 70)
                        };
                        crate::icons::show(ui, "youtube", 15.0, red);
                        ui.add_space(3.0);
                        egui::ComboBox::from_id_salt("source")
                            .selected_text(if self.source == "soundcloud" {
                                "SoundCloud"
                            } else {
                                "YouTube"
                            })
                            .show_ui(ui, |ui| {
                                ui.selectable_value(&mut self.source, "youtube".into(), "YouTube");
                                ui.selectable_value(
                                    &mut self.source,
                                    "soundcloud".into(),
                                    "SoundCloud",
                                );
                            });
                        ui.add_space(4.0);
                        let resp = ui.add(
                            egui::TextEdit::singleline(&mut self.url)
                                .hint_text(tl(lang, "inicio.url_hint"))
                                .frame(egui::Frame::NONE)
                                .desired_width(ui.available_width() - 26.0),
                        );
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
            let btn = egui::Button::image_and_text(
                crate::icons::img("search", 15.0, p.accent),
                RichText::new(tl(lang, "inicio.analyze")).color(p.accent),
            )
            .fill(p.accent.gamma_multiply(0.18))
            .corner_radius(10)
            .min_size(egui::vec2(104.0, 38.0));
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
                if ui
                    .add(
                        egui::Button::new(
                            RichText::new(tl(lang, "inicio.supported"))
                                .small()
                                .color(p.fg_dim),
                        )
                        .frame(false),
                    )
                    .clicked()
                {
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

        for e in self
            .history
            .clone()
            .into_iter()
            .filter(|e| q.is_empty() || e.title.to_lowercase().contains(&q))
        {
            // The whole row is a hover-highlighted click target that opens the file.
            let resp = egui::Frame::new()
                .inner_margin(egui::Margin::symmetric(6, 8))
                .corner_radius(8)
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        fmt_badge(ui, p, &badge_label(&e));
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
                    self.backend.send(Cmd::Open(path));
                }
            }
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
            ui.label(
                RichText::new(tl(lang, "cola.format"))
                    .small()
                    .color(p.fg_dim),
            );
            ui.add_space(6.0);
            combo_bare(ui, lang, "q.kind", &mut self.q_kind, &["video", "audio"]);
            if self.q_kind == "video" {
                combo_bare(
                    ui,
                    lang,
                    "q.q",
                    &mut self.q_quality,
                    &["best", "2160", "1440", "1080", "720", "480"],
                );
                combo_bare(
                    ui,
                    lang,
                    "q.c",
                    &mut self.q_container,
                    &["mp4", "mov", "mkv", "webm"],
                );
            } else {
                combo_bare(
                    ui,
                    lang,
                    "q.a",
                    &mut self.q_audio,
                    &["mp3", "m4a", "opus", "flac", "wav"],
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

        ui.add_space(10.0);
        ui.horizontal(|ui| {
            let done = self
                .queue
                .iter()
                .filter(|i| matches!(i.status, QStatus::Done))
                .count();
            ui.label(
                RichText::new(format!(
                    "{} {} · {done} {}",
                    self.queue.len(),
                    tl(lang, "cola.queued"),
                    tl(lang, "cola.completed_n")
                ))
                .small()
                .color(p.fg_dim),
            );
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui.button(tl(lang, "cola.clear_done")).clicked() {
                    self.queue.retain(|i| !matches!(i.status, QStatus::Done));
                }
            });
        });
        ui.add_space(6.0);

        let mut remove: Option<u64> = None;
        for it in &self.queue {
            card(ui, p, |ui| {
                ui.horizontal(|ui| {
                    ui.vertical(|ui| {
                        ui.set_width(ui.available_width() - 80.0);
                        let label: String = it.label.chars().take(60).collect();
                        ui.label(RichText::new(label).color(p.fg));
                        let (txt, col) = match &it.status {
                            QStatus::Pending => (tl(lang, "cola.pending").to_string(), p.fg_dim),
                            QStatus::Downloading => {
                                (format!("{:.0}%", it.progress * 100.0), p.accent)
                            }
                            QStatus::Done => (tl(lang, "cola.done").to_string(), p.ok),
                            QStatus::Error(e) => (format!("error: {e}"), p.err),
                        };
                        ui.label(
                            RichText::new(format!("{}  ·  {txt}", it.kind))
                                .small()
                                .color(col),
                        );
                        if matches!(it.status, QStatus::Downloading) {
                            ui.add(egui::ProgressBar::new(it.progress).desired_height(6.0));
                        }
                    });
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if !matches!(it.status, QStatus::Downloading)
                            && ui
                                .button("✕")
                                .on_hover_text(tl(lang, "cola.remove"))
                                .clicked()
                        {
                            remove = Some(it.id);
                        }
                    });
                });
            });
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
            ui.horizontal(|ui| {
                ui.spinner();
                ui.label(RichText::new(tl(lang, "state.loading")).color(p.fg_dim));
            });
            return;
        };
        let mut new_lang = self.lang;
        let scroll_to = self.settings_scroll_to.take();

        let heading = |ui: &mut egui::Ui, sec: &str, key: &str| {
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
            ui.add_space(2.0);
        };

        // General.
        heading(ui, "sec.general", "set.general");
        setting_row(ui, p, tl(lang, "set.language"), |ui| {
            egui::ComboBox::from_id_salt("lang")
                .selected_text(self.lang.label())
                .show_ui(ui, |ui| {
                    for l in Lang::ALL {
                        ui.selectable_value(&mut new_lang, l, l.label());
                    }
                });
        });
        let mut dark = self.dark;
        setting_row(ui, p, tl(lang, "set.theme"), |ui| {
            egui::ComboBox::from_id_salt("theme")
                .selected_text(tl(lang, if dark { "theme.dark" } else { "theme.light" }))
                .show_ui(ui, |ui| {
                    ui.selectable_value(&mut dark, true, tl(lang, "theme.dark"));
                    ui.selectable_value(&mut dark, false, tl(lang, "theme.light"));
                });
        });
        if dark != self.dark {
            self.dark = dark;
            theme::apply(&ui.ctx().clone(), dark);
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
        ui.add(
            egui::TextEdit::singleline(&mut s.download_dir)
                .desired_width(f32::INFINITY)
                .margin(egui::Margin::symmetric(10, 7)),
        );
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
        ui.add(
            egui::TextEdit::singleline(&mut s.filename_template)
                .desired_width(f32::INFINITY)
                .margin(egui::Margin::symmetric(10, 7)),
        );
        setting_row(ui, p, tl(lang, "set.embed_subs"), |ui| {
            toggle(ui, &mut s.default_embed_subs, p);
        });
        setting_row(ui, p, tl(lang, "set.embed_chapters"), |ui| {
            toggle(ui, &mut s.default_embed_chapters, p);
        });

        // PO token.
        ui.add_space(20.0);
        heading(ui, "sec.potoken", "set.potoken");
        ui.add_space(4.0);
        ui.label(
            RichText::new(tl(lang, "set.potoken_desc"))
                .small()
                .color(p.fg_dim),
        );
        setting_row(ui, p, tl(lang, "set.mode"), |ui| {
            combo_bare(
                ui,
                lang,
                "set.mode",
                &mut s.po_token_mode,
                &["off", "manual", "auto"],
            );
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
            egui::Frame::new()
                .fill(p.surface)
                .corner_radius(10)
                .inner_margin(egui::Margin::symmetric(12, 10))
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        ui.label(RichText::new(tl(lang, "set.loudness")).small().color(p.fg));
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            ui.label(RichText::new("Spotify/YouTube").small().color(p.fg_dim));
                            ui.add_space(6.0);
                            ui.label(
                                RichText::new(format!("{} LUFS", s.normalize_lufs))
                                    .small()
                                    .strong()
                                    .color(p.accent),
                            );
                        });
                    });
                    ui.add_space(4.0);
                    ui.spacing_mut().slider_width = ui.available_width() - 16.0;
                    ui.add(egui::Slider::new(&mut s.normalize_lufs, -23..=-9).show_value(false));
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

        if new_lang != self.lang {
            self.lang = new_lang;
        }
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
        let _ = std::fs::create_dir_all(&dir);
        let _ = std::fs::write(
            &path,
            "[Desktop Entry]\nType=Application\nName=Yoink\nExec=yoink-desktop\n\
             Icon=yoink\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
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

/// A settings row: label on the left, control on the right.
fn setting_row(ui: &mut egui::Ui, p: theme::Palette, label: &str, add: impl FnOnce(&mut egui::Ui)) {
    ui.add_space(12.0);
    ui.horizontal(|ui| {
        ui.label(RichText::new(label).color(p.fg));
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), add);
    });
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

fn combo_bare(ui: &mut egui::Ui, lang: Lang, id: &str, value: &mut String, options: &[&str]) {
    egui::ComboBox::from_id_salt(id)
        .selected_text(opt_label(lang, value))
        .show_ui(ui, |ui| {
            for opt in options {
                ui.selectable_value(value, opt.to_string(), opt_label(lang, opt));
            }
        });
}
