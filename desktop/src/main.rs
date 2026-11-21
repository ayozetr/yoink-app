// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Yoink native desktop UI (egui). It renders straight to the GPU — no WebView,
//! no HTML/JS — and drives the local `yoink-core` backend over its REST/WS API.
//! A hidden WebView used only for YouTube PO-token minting arrives in a later
//! phase (it's the one thing that still needs a JS runtime).

mod api;
mod app;
mod minter;
mod theme;

fn main() -> eframe::Result {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("Yoink")
            .with_inner_size([1000.0, 720.0])
            .with_min_inner_size([520.0, 480.0]),
        ..Default::default()
    };
    eframe::run_native(
        "Yoink",
        options,
        Box::new(|cc| Ok(Box::new(app::App::new(cc)))),
    )
}
