// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! The egui application: the tabbed shell and the download screen. This is the
//! native replacement for the React UI; it drives the same `yoink-core` backend
//! over the REST/WS contract (see [`crate::api`]).

use egui::RichText;

use crate::api::{Backend, Cmd, DownloadReq, Evt, HistoryEntry, Settings, VideoLite};
use crate::theme;

#[derive(PartialEq, Clone, Copy)]
enum Tab {
    Inicio,
    Cola,
    Historial,
    Ajustes,
}

enum Preview {
    None,
    Video(VideoLite),
    Playlist { title: String, count: usize },
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

struct QueueItem {
    id: u64,
    url: String,
    kind: String,
    status: QStatus,
    progress: f32,
}

pub struct App {
    backend: Backend,
    minter: crate::minter::Minter,
    dark: bool,
    tab: Tab,
    url: String,
    kind: String,
    quality: String,
    container: String,
    audio_format: String,
    preview: Preview,
    status: Status,
    progress: f32,
    speed: Option<String>,
    eta: Option<String>,
    settings: Option<Settings>,
    settings_note: Option<String>,
    history: Vec<HistoryEntry>,
    history_loaded: bool,
    active: Option<ActiveDl>,
    queue: Vec<QueueItem>,
    queue_url: String,
    next_qid: u64,
}

impl App {
    pub fn new(cc: &eframe::CreationContext<'_>) -> App {
        let dark = true;
        theme::apply(&cc.egui_ctx, dark);
        // Enables egui::Image to load remote thumbnails (JPEG/PNG/WebP over http).
        egui_extras::install_image_loaders(&cc.egui_ctx);
        App {
            backend: Backend::spawn(cc.egui_ctx.clone()),
            minter: crate::minter::Minter::new(crate::api::port()),
            dark,
            tab: Tab::Inicio,
            url: String::new(),
            kind: "video".into(),
            quality: "best".into(),
            container: "mp4".into(),
            audio_format: "mp3".into(),
            preview: Preview::None,
            status: Status::Idle,
            progress: 0.0,
            speed: None,
            eta: None,
            settings: None,
            settings_note: None,
            history: Vec::new(),
            history_loaded: false,
            active: None,
            queue: Vec::new(),
            queue_url: String::new(),
            next_qid: 0,
        }
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
                Evt::Analyzing => self.status = Status::Analyzing,
                Evt::Info(v) => {
                    self.preview = Preview::Video(v);
                    self.status = Status::Idle;
                }
                Evt::Playlist { title, count } => {
                    self.preview = Preview::Playlist { title, count };
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
                Evt::Done(path) => match self.active.take() {
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
                },
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

    /// Start the next queued item when nothing is downloading.
    fn pump_queue(&mut self) {
        if self.active.is_some() {
            return;
        }
        let Some(s) = self.settings.clone() else {
            return;
        };
        let Some(it) = self
            .queue
            .iter_mut()
            .find(|i| matches!(i.status, QStatus::Pending))
        else {
            return;
        };
        it.status = QStatus::Downloading;
        it.progress = 0.0;
        let (id, url, kind) = (it.id, it.url.clone(), it.kind.clone());
        self.active = Some(ActiveDl::Queue(id));
        self.backend.send(Cmd::Download(DownloadReq {
            url,
            quality: (kind == "video").then(|| s.default_quality.clone()),
            kind,
            container: s.default_container.clone(),
            audio_format: s.default_audio_format.clone(),
        }));
    }

    fn queue_add(&mut self) {
        let url = self.queue_url.trim().to_string();
        if url.is_empty() {
            return;
        }
        let kind = self
            .settings
            .as_ref()
            .map(|s| s.default_kind.clone())
            .unwrap_or_else(|| "video".into());
        self.queue.push(QueueItem {
            id: self.next_qid,
            url,
            kind,
            status: QStatus::Pending,
            progress: 0.0,
        });
        self.next_qid += 1;
        self.queue_url.clear();
    }

    fn analyze(&mut self) {
        let url = self.url.trim().to_string();
        if url.is_empty() {
            return;
        }
        self.preview = Preview::None;
        self.status = Status::Analyzing;
        self.backend.send(Cmd::Analyze(url));
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
        self.drain_events();
        self.pump_queue();
        // Lazy-load the history the first time its tab is opened.
        if self.tab == Tab::Historial && !self.history_loaded {
            self.history_loaded = true;
            self.backend.send(Cmd::LoadHistory);
        }
        let p = theme::palette(self.dark);

        egui::Panel::top("topbar")
            .frame(
                egui::Frame::new()
                    .fill(p.surface)
                    .inner_margin(egui::Margin::symmetric(16, 10)),
            )
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(RichText::new("Yoink").size(22.0).strong().color(p.fg));
                    ui.add_space(16.0);
                    for (tab, name) in [
                        (Tab::Inicio, "Inicio"),
                        (Tab::Cola, "Cola"),
                        (Tab::Historial, "Historial"),
                        (Tab::Ajustes, "Ajustes"),
                    ] {
                        ui.selectable_value(&mut self.tab, tab, name);
                    }
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let icon = if self.dark { "☀" } else { "☾" };
                        if ui.button(icon).on_hover_text("Cambiar tema").clicked() {
                            self.dark = !self.dark;
                            theme::apply(&ctx, self.dark);
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
                    ui.vertical_centered(|ui| {
                        ui.set_max_width(680.0);
                        match self.tab {
                            Tab::Inicio => self.ui_inicio(ui, p),
                            Tab::Historial => self.ui_historial(ui, p),
                            Tab::Ajustes => self.ui_ajustes(ui, p),
                            Tab::Cola => self.ui_cola(ui, p),
                        }
                    });
                });
            });
    }
}

impl App {
    fn ui_inicio(&mut self, ui: &mut egui::Ui, p: theme::Palette) {
        ui.add_space(12.0);
        ui.label(
            RichText::new("Pega un enlace para empezar")
                .heading()
                .color(p.fg),
        );
        ui.add_space(12.0);

        // URL input + analyze.
        card(ui, p, |ui| {
            ui.horizontal(|ui| {
                let field = egui::TextEdit::singleline(&mut self.url)
                    .hint_text("https://…")
                    .desired_width(ui.available_width() - 110.0);
                let resp = ui.add(field);
                let submit = resp.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter));
                let analyzing = matches!(self.status, Status::Analyzing);
                if ui
                    .add_enabled(!analyzing, egui::Button::new("Analizar"))
                    .clicked()
                    || submit
                {
                    self.analyze();
                }
            });
        });

        // Status line.
        match &self.status {
            Status::Analyzing => {
                ui.add_space(10.0);
                ui.horizontal(|ui| {
                    ui.spinner();
                    ui.label(RichText::new("Analizando…").color(p.fg_dim));
                });
            }
            Status::Error(e) => {
                ui.add_space(10.0);
                ui.label(RichText::new(format!("⚠ {e}")).color(p.err));
            }
            _ => {}
        }

        // Preview + download controls.
        match &self.preview {
            Preview::Video(v) => {
                let v = v.clone();
                ui.add_space(14.0);
                card(ui, p, |ui| {
                    if let Some(thumb) = v.thumbnail_url.as_deref().filter(|s| !s.is_empty()) {
                        ui.add(
                            egui::Image::from_uri(thumb.to_string())
                                .max_width(ui.available_width())
                                .max_height(200.0)
                                .corner_radius(8),
                        );
                        ui.add_space(10.0);
                    }
                    ui.label(RichText::new(&v.title).size(17.0).strong().color(p.fg));
                    ui.add_space(4.0);
                    let mut meta = Vec::new();
                    if let Some(u) = &v.uploader {
                        meta.push(u.clone());
                    }
                    if let Some(d) = &v.duration_string {
                        meta.push(d.clone());
                    }
                    meta.push(format!("{} formatos", v.formats.len()));
                    if v.is_vr {
                        meta.push("VR".into());
                    }
                    ui.label(RichText::new(meta.join("  ·  ")).color(p.fg_dim));
                    ui.add_space(12.0);
                    self.ui_download_controls(ui, p, v.has_audio);
                });
                self.ui_progress(ui, p);
            }
            Preview::Playlist { title, count } => {
                let (title, count) = (title.clone(), *count);
                ui.add_space(14.0);
                card(ui, p, |ui| {
                    ui.label(RichText::new(&title).size(17.0).strong().color(p.fg));
                    ui.label(RichText::new(format!("Lista · {count} elementos")).color(p.fg_dim));
                    ui.add_space(6.0);
                    ui.label(
                        RichText::new("La descarga de listas llega en una fase posterior.")
                            .small()
                            .color(p.fg_dim),
                    );
                });
            }
            Preview::None => {}
        }
    }

    fn ui_download_controls(&mut self, ui: &mut egui::Ui, p: theme::Palette, has_audio: bool) {
        ui.horizontal(|ui| {
            ui.selectable_value(&mut self.kind, "video".to_string(), "Vídeo");
            ui.add_enabled_ui(has_audio, |ui| {
                ui.selectable_value(&mut self.kind, "audio".to_string(), "Audio");
            });
        });
        ui.add_space(8.0);
        ui.horizontal(|ui| {
            if self.kind == "video" {
                combo(
                    ui,
                    "Calidad",
                    &mut self.quality,
                    &["best", "2160", "1440", "1080", "720", "480"],
                );
                combo(
                    ui,
                    "Contenedor",
                    &mut self.container,
                    &["mp4", "mov", "mkv", "webm"],
                );
            } else {
                combo(
                    ui,
                    "Formato",
                    &mut self.audio_format,
                    &["mp3", "m4a", "opus", "flac", "wav"],
                );
            }
        });
        ui.add_space(12.0);
        let busy = self.active.is_some();
        let btn =
            egui::Button::new(RichText::new("  Descargar  ").color(p.accent_fg)).fill(p.accent);
        if ui.add_enabled(!busy, btn).clicked() {
            self.start_download();
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
                ui.label(RichText::new(format!("✓ Descargado: {path}")).color(p.ok));
            }
            _ => {}
        }
    }

    fn ui_historial(&mut self, ui: &mut egui::Ui, p: theme::Palette) {
        ui.add_space(12.0);
        ui.horizontal(|ui| {
            ui.label(RichText::new("Historial").heading().color(p.fg));
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui.button("Refrescar").clicked() {
                    self.backend.send(Cmd::LoadHistory);
                }
            });
        });
        ui.add_space(8.0);

        if self.history.is_empty() {
            ui.add_space(24.0);
            ui.label(RichText::new("Todavía no hay descargas.").color(p.fg_dim));
            return;
        }

        for e in self.history.clone() {
            card(ui, p, |ui| {
                ui.horizontal(|ui| {
                    let color = match e.status.as_str() {
                        "completed" => p.ok,
                        "error" => p.err,
                        _ => p.fg_dim,
                    };
                    ui.vertical(|ui| {
                        ui.set_width(ui.available_width() - 90.0);
                        ui.label(RichText::new(&e.title).strong().color(p.fg));
                        let mut meta = vec![e.kind.clone()];
                        if let Some(q) = &e.quality {
                            if !q.is_empty() {
                                meta.push(q.clone());
                            }
                        }
                        if let Some(sz) = e.filesize {
                            meta.push(human_bytes(sz));
                        }
                        meta.push(e.created_at.chars().take(10).collect());
                        ui.label(RichText::new(meta.join("  ·  ")).small().color(color));
                    });
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if let Some(path) = e.filepath.clone() {
                            if e.status == "completed" && ui.button("Abrir").clicked() {
                                self.backend.send(Cmd::Open(path));
                            }
                        }
                    });
                });
            });
        }
    }

    fn ui_cola(&mut self, ui: &mut egui::Ui, p: theme::Palette) {
        ui.add_space(12.0);
        ui.label(RichText::new("Cola").heading().color(p.fg));
        ui.add_space(8.0);

        // Add box — uses the default format from Ajustes; downloads run one by one.
        card(ui, p, |ui| {
            ui.horizontal(|ui| {
                let field = egui::TextEdit::singleline(&mut self.queue_url)
                    .hint_text("Pega un enlace y añádelo a la cola")
                    .desired_width(ui.available_width() - 90.0);
                let resp = ui.add(field);
                let enter = resp.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter));
                if ui.button("Añadir").clicked() || enter {
                    self.queue_add();
                }
            });
        });

        if self.queue.is_empty() {
            ui.add_space(24.0);
            ui.label(RichText::new("La cola está vacía.").color(p.fg_dim));
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
                RichText::new(format!("{} en cola · {done} completadas", self.queue.len()))
                    .small()
                    .color(p.fg_dim),
            );
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui.button("Limpiar completadas").clicked() {
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
                        let label: String = it.url.chars().take(60).collect();
                        ui.label(RichText::new(label).color(p.fg));
                        let (txt, col) = match &it.status {
                            QStatus::Pending => ("en espera".to_string(), p.fg_dim),
                            QStatus::Downloading => {
                                (format!("{:.0}%", it.progress * 100.0), p.accent)
                            }
                            QStatus::Done => ("completada".to_string(), p.ok),
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
                            && ui.button("✕").on_hover_text("Quitar").clicked()
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

    fn ui_ajustes(&mut self, ui: &mut egui::Ui, p: theme::Palette) {
        ui.add_space(12.0);
        ui.label(RichText::new("Ajustes").heading().color(p.fg));
        ui.add_space(8.0);

        let Some(mut s) = self.settings.clone() else {
            ui.add_space(24.0);
            ui.horizontal(|ui| {
                ui.spinner();
                ui.label(RichText::new("Cargando…").color(p.fg_dim));
            });
            return;
        };

        card(ui, p, |ui| {
            ui.label(RichText::new("Descargas").strong().color(p.fg));
            ui.add_space(6.0);
            ui.label(
                RichText::new("Carpeta de descargas")
                    .small()
                    .color(p.fg_dim),
            );
            ui.add(egui::TextEdit::singleline(&mut s.download_dir).desired_width(f32::INFINITY));
            ui.add_space(8.0);
            ui.horizontal(|ui| {
                combo(ui, "Tipo", &mut s.default_kind, &["video", "audio"]);
                combo(
                    ui,
                    "Calidad",
                    &mut s.default_quality,
                    &["best", "2160", "1440", "1080", "720", "480"],
                );
                combo(
                    ui,
                    "Contenedor",
                    &mut s.default_container,
                    &["mp4", "mov", "mkv", "webm"],
                );
                combo(
                    ui,
                    "Audio",
                    &mut s.default_audio_format,
                    &["mp3", "m4a", "opus", "flac", "wav"],
                );
            });
        });

        ui.add_space(12.0);
        card(ui, p, |ui| {
            ui.label(RichText::new("YouTube PO token").strong().color(p.fg));
            ui.add_space(6.0);
            ui.label(
                RichText::new(
                    "auto mintea un token en un WebView oculto para saltar el muro antibot.",
                )
                .small()
                .color(p.fg_dim),
            );
            ui.add_space(6.0);
            combo(ui, "Modo", &mut s.po_token_mode, &["off", "manual", "auto"]);
        });

        ui.add_space(12.0);
        card(ui, p, |ui| {
            ui.label(RichText::new("Opciones").strong().color(p.fg));
            ui.add_space(6.0);
            ui.checkbox(&mut s.normalize_audio, "Normalizar audio a -14 LUFS");
            ui.checkbox(&mut s.sponsorblock_enabled, "SponsorBlock");
            ui.checkbox(&mut s.fetch_lyrics, "Buscar letras");
            ui.checkbox(&mut s.check_updates, "Buscar actualizaciones al iniciar");
            ui.checkbox(&mut s.notify_on_complete, "Notificar al terminar");
        });

        ui.add_space(14.0);
        ui.horizontal(|ui| {
            let btn =
                egui::Button::new(RichText::new("  Guardar  ").color(p.accent_fg)).fill(p.accent);
            if ui.add(btn).clicked() {
                self.settings_note = None;
                self.backend.send(Cmd::SaveSettings(Box::new(s.clone())));
            }
            if let Some(note) = &self.settings_note {
                ui.label(RichText::new(format!("✓ {note}")).color(p.ok));
            }
        });

        // Keep edits in the in-memory copy so they persist across frames until saved.
        self.settings = Some(s);
    }
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

/// A raised surface card with padding and a hairline border.
fn card(ui: &mut egui::Ui, p: theme::Palette, add: impl FnOnce(&mut egui::Ui)) {
    egui::Frame::new()
        .fill(p.surface)
        .stroke(egui::Stroke::new(1.0, p.line))
        .corner_radius(12)
        .inner_margin(egui::Margin::same(16))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            add(ui);
        });
}

/// A labelled dropdown bound to a string from a fixed option list.
fn combo(ui: &mut egui::Ui, label: &str, value: &mut String, options: &[&str]) {
    ui.vertical(|ui| {
        ui.label(RichText::new(label).small());
        egui::ComboBox::from_id_salt(label)
            .selected_text(value.clone())
            .show_ui(ui, |ui| {
                for opt in options {
                    ui.selectable_value(value, opt.to_string(), *opt);
                }
            });
    });
}
