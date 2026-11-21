// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Yoink native desktop UI (egui). It renders straight to the GPU — no WebView,
//! no HTML/JS — and drives the local `yoink-core` backend over its REST/WS API.
//! A hidden WebView (`yoink-minter`) is spawned only for YouTube PO-token minting,
//! the one thing that still needs a JS runtime.

mod api;
mod app;
mod backend_proc;
mod deeplink;
mod fonts;
mod i18n;
mod minter;
mod theme;

/// The window/taskbar icon, decoded from the bundled PNG.
fn icon() -> egui::IconData {
    match image::load_from_memory(include_bytes!("../assets/icon.png")) {
        Ok(img) => {
            let img = img.to_rgba8();
            let (width, height) = (img.width(), img.height());
            egui::IconData {
                rgba: img.into_raw(),
                width,
                height,
            }
        }
        Err(_) => egui::IconData::default(),
    }
}

fn main() -> eframe::Result {
    // Deep link + single instance: if a yoink:// link was passed and another
    // instance is already running, hand it over and exit; otherwise we become the
    // owner and receive future links on `dl_rx`.
    let pending = deeplink::url_from_args();
    let (dl_tx, dl_rx) = std::sync::mpsc::channel::<String>();
    if deeplink::single_instance(pending.clone(), dl_tx) {
        return Ok(());
    }

    // Start (and own) the backend if one isn't already running; dropped on exit.
    let _backend = backend_proc::Backend::ensure();

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("Yoink")
            .with_app_id("app.yoink.desktop")
            .with_inner_size([1000.0, 720.0])
            .with_min_inner_size([520.0, 480.0])
            .with_icon(icon()),
        ..Default::default()
    };
    eframe::run_native(
        "Yoink",
        options,
        Box::new(move |cc| Ok(Box::new(app::App::new(cc, pending, dl_rx)))),
    )
}
