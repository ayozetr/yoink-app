// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! The app's typefaces, matching the web UI: **Inter** for the interface and
//! **Gloock** for display titles (`font-display`). Both are bundled (converted
//! from the project's `@fontsource` woff2 to TTF) and registered on startup.

use std::sync::Arc;

use egui::{FontData, FontDefinitions, FontFamily};

const INTER: &[u8] = include_bytes!("../assets/fonts/Inter-Regular.ttf");
const GLOOCK: &[u8] = include_bytes!("../assets/fonts/Gloock-Regular.ttf");

/// The custom family name for display titles (Gloock).
pub fn display() -> FontFamily {
    FontFamily::Name("display".into())
}

/// Register Inter (UI) and Gloock (titles). Call once, before the first frame.
pub fn install(ctx: &egui::Context) {
    let mut fonts = FontDefinitions::default();
    fonts
        .font_data
        .insert("inter".to_owned(), Arc::new(FontData::from_static(INTER)));
    fonts
        .font_data
        .insert("gloock".to_owned(), Arc::new(FontData::from_static(GLOOCK)));

    // Inter leads the proportional family; egui's built-in fonts stay as fallback
    // for any glyph Inter lacks.
    fonts
        .families
        .entry(FontFamily::Proportional)
        .or_default()
        .insert(0, "inter".to_owned());

    // A dedicated family for titles.
    fonts.families.insert(
        FontFamily::Name("display".into()),
        vec!["gloock".to_owned()],
    );

    ctx.set_fonts(fonts);
}
