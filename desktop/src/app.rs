// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! The egui application: the tabbed shell and the download screen. This is the
//! native replacement for the React UI; it drives the same `yoink-core` backend
//! over the REST/WS contract (see [`crate::api`]).

use egui::RichText;

use crate::api::{Backend, Cmd, DownloadReq, Evt, VideoLite};
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

pub struct App {
    backend: Backend,
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
}

impl App {
    pub fn new(cc: &eframe::CreationContext<'_>) -> App {
        let dark = true;
        theme::apply(&cc.egui_ctx, dark);
        App {
            backend: Backend::spawn(cc.egui_ctx.clone()),
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
        }
    }

    fn drain_events(&mut self) {
        while let Ok(evt) = self.backend.rx.try_recv() {
            match evt {
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
                Evt::Progress { percent, speed, eta } => {
                    self.status = Status::Downloading;
                    self.progress = (percent / 100.0).clamp(0.0, 1.0);
                    self.speed = speed;
                    self.eta = eta;
                }
                Evt::Done(path) => {
                    self.progress = 1.0;
                    self.status = Status::Done(path);
                }
                Evt::DownloadErr(e) => self.status = Status::Error(e),
            }
        }
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
        let p = theme::palette(self.dark);

        egui::Panel::top("topbar")
            .frame(egui::Frame::new().fill(p.surface).inner_margin(egui::Margin::symmetric(16, 10)))
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
            .frame(egui::Frame::new().fill(p.canvas).inner_margin(egui::Margin::same(20)))
            .show(ui, |ui| {
                egui::ScrollArea::vertical().show(ui, |ui| {
                    ui.vertical_centered(|ui| {
                        ui.set_max_width(680.0);
                        match self.tab {
                            Tab::Inicio => self.ui_inicio(ui, p),
                            other => {
                                ui.add_space(40.0);
                                let name = match other {
                                    Tab::Cola => "Cola",
                                    Tab::Historial => "Historial",
                                    Tab::Ajustes => "Ajustes",
                                    Tab::Inicio => "",
                                };
                                ui.label(RichText::new(format!("{name} — próximamente")).color(p.fg_dim));
                            }
                        }
                    });
                });
            });
    }
}

impl App {
    fn ui_inicio(&mut self, ui: &mut egui::Ui, p: theme::Palette) {
        ui.add_space(12.0);
        ui.label(RichText::new("Pega un enlace para empezar").heading().color(p.fg));
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
                if ui.add_enabled(!analyzing, egui::Button::new("Analizar")).clicked() || submit {
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
                    ui.label(RichText::new("La descarga de listas llega en una fase posterior.").small().color(p.fg_dim));
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
                combo(ui, "Calidad", &mut self.quality, &["best", "2160", "1440", "1080", "720", "480"]);
                combo(ui, "Contenedor", &mut self.container, &["mp4", "mov", "mkv", "webm"]);
            } else {
                combo(ui, "Formato", &mut self.audio_format, &["mp3", "m4a", "opus", "flac", "wav"]);
            }
        });
        ui.add_space(12.0);
        let busy = matches!(self.status, Status::Downloading);
        let btn = egui::Button::new(RichText::new("  Descargar  ").color(p.accent_fg)).fill(p.accent);
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
                ui.add(egui::ProgressBar::new(self.progress).show_percentage().text(extra.join("  ·  ")));
            }
            Status::Done(path) => {
                ui.add_space(12.0);
                ui.label(RichText::new(format!("✓ Descargado: {path}")).color(p.ok));
            }
            _ => {}
        }
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
