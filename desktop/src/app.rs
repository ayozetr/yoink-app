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
    deeplink_rx: std::sync::mpsc::Receiver<String>,
    shot: Option<(String, std::time::Instant)>, // (output path, started) for YOINK_SHOT
}

impl App {
    pub fn new(
        cc: &eframe::CreationContext<'_>,
        pending: Option<String>,
        deeplink_rx: std::sync::mpsc::Receiver<String>,
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
            deeplink_rx,
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
        self.backend.send(Cmd::Download(DownloadReq {
            url: self.url.trim().to_string(),
            kind: self.kind.clone(),
            quality: (self.kind == "video").then(|| self.quality.clone()),
            container: self.container.clone(),
            audio_format: self.audio_format.clone(),
        }));
    }
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        // Poll a little even when idle, so deep links handed over by another launch
        // are picked up promptly (and progress bars stay smooth).
        ctx.request_repaint_after(std::time::Duration::from_millis(400));
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
                    // Brand: a violet logo tile + the Gloock wordmark, theme toggle right.
                    ui.horizontal(|ui| {
                        egui::Frame::new()
                            .fill(p.accent)
                            .corner_radius(7)
                            .inner_margin(egui::Margin::same(5))
                            .show(ui, |ui| crate::icons::show(ui, "music", 16.0, p.accent_fg));
                        ui.add_space(8.0);
                        ui.label(
                            RichText::new("Yoink")
                                .size(23.0)
                                .family(crate::fonts::display())
                                .color(p.fg),
                        );
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            let tint = p.fg_dim;
                            let ic = if self.dark { "sun" } else { "moon" };
                            if ui
                                .add(
                                    egui::Button::image(crate::icons::img(ic, 18.0, tint))
                                        .frame(false),
                                )
                                .on_hover_text(tl(lang, "theme.toggle"))
                                .clicked()
                            {
                                self.dark = !self.dark;
                                theme::apply(&ctx, self.dark);
                            }
                        });
                    });
                    ui.add_space(8.0);
                    // Pill tabs with icons.
                    ui.horizontal(|ui| {
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
                                crate::icons::img(ic, 16.0, fg),
                                RichText::new(tl(lang, key)).color(fg),
                            )
                            .fill(fill)
                            .corner_radius(8);
                            if ui.add(btn).clicked() {
                                self.tab = tab;
                            }
                        }
                    });
                });
            });

        egui::CentralPanel::default()
            .frame(
                egui::Frame::new()
                    .fill(p.canvas)
                    .inner_margin(egui::Margin::same(20)),
            )
            .show(ui, |ui| {
                egui::ScrollArea::vertical().show(ui, |ui| {
                    // A centered column with LEFT-aligned content (like the web UI).
                    let w = 720.0_f32.min(ui.available_width() - 48.0);
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
                .corner_radius(10)
                .inner_margin(egui::Margin::symmetric(10, 7))
                .show(ui, |ui| {
                    ui.set_width(total - 128.0);
                    ui.horizontal(|ui| {
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
                                .desired_width(f32::INFINITY),
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
                ui.label(
                    RichText::new(tl(lang, "inicio.supported"))
                        .small()
                        .color(p.fg_dim),
                );
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
            ui.add_space(72.0);
            ui.vertical_centered(|ui| {
                crate::icons::show(ui, "download", 44.0, p.fg_dim);
                ui.add_space(10.0);
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
                        if let Some(d) = &v.duration_string {
                            meta.push(d.clone());
                        }
                        if v.is_vr {
                            meta.push("VR".into());
                        }
                        ui.label(RichText::new(meta.join("  ·  ")).small().color(p.fg_dim));
                    });
                });
                ui.add_space(16.0);
                self.ui_download_controls(ui, p, v.has_audio);
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
                ui.add_space(14.0);
                let mut import = false;
                card(ui, p, |ui| {
                    ui.horizontal(|ui| {
                        if let Some(c) = info.cover_url.as_deref().filter(|s| !s.is_empty()) {
                            ui.add(
                                egui::Image::from_uri(c.to_string())
                                    .fit_to_exact_size(egui::vec2(72.0, 72.0))
                                    .corner_radius(6),
                            );
                            ui.add_space(10.0);
                        }
                        ui.vertical(|ui| {
                            ui.label(RichText::new(&info.name).size(17.0).strong().color(p.fg));
                            let mut meta = vec![info.source.clone()];
                            if let Some(sub) = &info.subtitle {
                                meta.push(sub.clone());
                            }
                            meta.push(format!(
                                "{} {}",
                                info.tracks.len(),
                                tl(lang, "music.tracks")
                            ));
                            ui.label(RichText::new(meta.join("  ·  ")).color(p.fg_dim));
                        });
                    });
                    ui.add_space(10.0);
                    for t in info.tracks.iter().take(8) {
                        ui.label(
                            RichText::new(format!("• {} — {}", t.artists, t.title))
                                .small()
                                .color(p.fg_dim),
                        );
                    }
                    if info.tracks.len() > 8 {
                        ui.label(RichText::new("…").small().color(p.fg_dim));
                    }
                    ui.add_space(12.0);
                    let label = format!("  {}  ", tl(lang, "music.import"));
                    let btn =
                        egui::Button::new(RichText::new(label).color(p.accent_fg)).fill(p.accent);
                    if ui.add(btn).clicked() {
                        import = true;
                    }
                });
                if import {
                    self.enqueue_music(&info);
                    self.tab = Tab::Cola;
                    self.preview = Preview::None;
                }
            }
            Preview::None => {}
        }
    }

    fn ui_download_controls(&mut self, ui: &mut egui::Ui, p: theme::Palette, has_audio: bool) {
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
            // Wide Download button, with the chosen format summarised.
            let summary = if self.kind == "video" {
                format!(
                    "{} · {}",
                    self.quality.to_uppercase(),
                    self.container.to_uppercase()
                )
            } else {
                self.audio_format.to_uppercase()
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

        // Collapsible advanced options: the format pickers.
        if self.advanced_open {
            ui.add_space(8.0);
            ui.horizontal(|ui| {
                if self.kind == "video" {
                    combo(
                        ui,
                        "q",
                        tl(lang, "field.quality"),
                        &mut self.quality,
                        &["best", "2160", "1440", "1080", "720", "480"],
                    );
                    combo(
                        ui,
                        "c",
                        tl(lang, "field.container"),
                        &mut self.container,
                        &["mp4", "mov", "mkv", "webm"],
                    );
                } else {
                    combo(
                        ui,
                        "f",
                        tl(lang, "field.format"),
                        &mut self.audio_format,
                        &["mp3", "m4a", "opus", "flac", "wav"],
                    );
                }
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
        for e in self
            .history
            .clone()
            .into_iter()
            .filter(|e| q.is_empty() || e.title.to_lowercase().contains(&q))
        {
            card(ui, p, |ui| {
                ui.horizontal(|ui| {
                    fmt_badge(ui, p, &badge_label(&e));
                    ui.add_space(12.0);
                    ui.vertical(|ui| {
                        ui.set_width(ui.available_width() - 70.0);
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
                            meta.push(relative(&e.created_at, lang));
                            ui.label(RichText::new(meta.join("  ·  ")).small().color(p.fg_dim));
                        });
                    });
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if let Some(path) = e.filepath.clone() {
                            if e.status == "completed"
                                && ui
                                    .add(
                                        egui::Button::image_and_text(
                                            crate::icons::img("folder", 14.0, p.fg_dim),
                                            RichText::new(tl(lang, "action.open"))
                                                .small()
                                                .color(p.fg_dim),
                                        )
                                        .frame(false),
                                    )
                                    .clicked()
                            {
                                self.backend.send(Cmd::Open(path));
                            }
                        }
                    });
                });
            });
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
            combo_bare(ui, "q.kind", &mut self.q_kind, &["video", "audio"]);
            if self.q_kind == "video" {
                combo_bare(
                    ui,
                    "q.q",
                    &mut self.q_quality,
                    &["best", "2160", "1440", "1080", "720", "480"],
                );
                combo_bare(
                    ui,
                    "q.c",
                    &mut self.q_container,
                    &["mp4", "mov", "mkv", "webm"],
                );
            } else {
                combo_bare(
                    ui,
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
                        egui::Button::new(RichText::new(format!("  {label}  ")).color(p.accent_fg))
                            .fill(p.accent)
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
            ui.add_space(24.0);
            ui.label(RichText::new(tl(lang, "cola.empty")).color(p.fg_dim));
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
                    self.backend.send(Cmd::LoadLogs);
                }
                ui.add_space(12.0);
                if ui
                    .add(
                        egui::Button::image_and_text(
                            crate::icons::img("clipboard", 14.0, p.fg_dim),
                            RichText::new(tl(lang, "action.copy"))
                                .small()
                                .color(p.fg_dim),
                        )
                        .frame(false),
                    )
                    .clicked()
                {
                    ui.ctx().copy_text(self.logs_text.clone());
                }
            });
        });
        ui.add_space(4.0);
        ui.label(RichText::new(&self.logs_path).small().color(p.fg_dim));
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

        let heading = |ui: &mut egui::Ui, key: &str| {
            ui.add_space(10.0);
            ui.label(
                RichText::new(tl(lang, key))
                    .size(26.0)
                    .family(crate::fonts::display())
                    .color(p.fg),
            );
            ui.add_space(2.0);
        };

        // General.
        heading(ui, "set.general");
        setting_row(ui, p, tl(lang, "set.language"), |ui| {
            egui::ComboBox::from_id_salt("lang")
                .selected_text(self.lang.label())
                .show_ui(ui, |ui| {
                    for l in Lang::ALL {
                        ui.selectable_value(&mut new_lang, l, l.label());
                    }
                });
        });
        setting_row(ui, p, tl(lang, "set.updates"), |ui| {
            toggle(ui, &mut s.check_updates, p);
        });
        setting_row(ui, p, tl(lang, "set.notify"), |ui| {
            toggle(ui, &mut s.notify_on_complete, p);
        });

        // Downloads.
        ui.add_space(20.0);
        heading(ui, "set.downloads");
        ui.add_space(12.0);
        ui.label(RichText::new(tl(lang, "set.dir")).small().color(p.fg_dim));
        ui.add_space(3.0);
        ui.add(
            egui::TextEdit::singleline(&mut s.download_dir)
                .desired_width(f32::INFINITY)
                .margin(egui::Margin::symmetric(10, 7)),
        );
        setting_row(ui, p, tl(lang, "field.kind"), |ui| {
            combo_bare(ui, "set.kind", &mut s.default_kind, &["video", "audio"]);
        });
        setting_row(ui, p, tl(lang, "field.quality"), |ui| {
            combo_bare(
                ui,
                "set.q",
                &mut s.default_quality,
                &["best", "2160", "1440", "1080", "720", "480"],
            );
        });
        setting_row(ui, p, tl(lang, "field.container"), |ui| {
            combo_bare(
                ui,
                "set.c",
                &mut s.default_container,
                &["mp4", "mov", "mkv", "webm"],
            );
        });
        setting_row(ui, p, tl(lang, "field.audio"), |ui| {
            combo_bare(
                ui,
                "set.a",
                &mut s.default_audio_format,
                &["mp3", "m4a", "opus", "flac", "wav"],
            );
        });

        // PO token.
        ui.add_space(20.0);
        heading(ui, "set.potoken");
        ui.add_space(4.0);
        ui.label(
            RichText::new(tl(lang, "set.potoken_desc"))
                .small()
                .color(p.fg_dim),
        );
        setting_row(ui, p, tl(lang, "set.mode"), |ui| {
            combo_bare(
                ui,
                "set.mode",
                &mut s.po_token_mode,
                &["off", "manual", "auto"],
            );
        });

        // Processing.
        ui.add_space(20.0);
        heading(ui, "set.options");
        setting_row(ui, p, tl(lang, "set.normalize"), |ui| {
            toggle(ui, &mut s.normalize_audio, p);
        });
        setting_row(ui, p, tl(lang, "set.sponsorblock"), |ui| {
            toggle(ui, &mut s.sponsorblock_enabled, p);
        });
        setting_row(ui, p, tl(lang, "set.lyrics"), |ui| {
            toggle(ui, &mut s.fetch_lyrics, p);
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
fn combo_bare(ui: &mut egui::Ui, id: &str, value: &mut String, options: &[&str]) {
    egui::ComboBox::from_id_salt(id)
        .selected_text(value.clone())
        .show_ui(ui, |ui| {
            for opt in options {
                ui.selectable_value(value, opt.to_string(), *opt);
            }
        });
}

fn combo(ui: &mut egui::Ui, id: &str, label: &str, value: &mut String, options: &[&str]) {
    ui.vertical(|ui| {
        ui.label(RichText::new(label).small());
        egui::ComboBox::from_id_salt(id)
            .selected_text(value.clone())
            .show_ui(ui, |ui| {
                for opt in options {
                    ui.selectable_value(value, opt.to_string(), *opt);
                }
            });
    });
}
