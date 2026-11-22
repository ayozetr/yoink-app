// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! The app's typefaces, matching the web UI: **Inter** for the interface and
//! **Gloock** for display titles (`font-display`). Both are bundled (converted
//! from the project's `@fontsource` woff2 to TTF) and registered on startup.

use std::sync::Arc;

use egui::{FontData, FontDefinitions, FontFamily};

const INTER: &[u8] = include_bytes!("../assets/fonts/Inter-Regular.ttf");
const INTER_SEMIBOLD: &[u8] = include_bytes!("../assets/fonts/Inter-SemiBold.ttf");
const GLOOCK: &[u8] = include_bytes!("../assets/fonts/Gloock-Regular.ttf");

/// The custom family name for display titles (Gloock).
pub fn display() -> FontFamily {
    FontFamily::Name("display".into())
}

/// The custom family name for semibold UI text (Inter SemiBold) — egui's default
/// fonts have no bold face, so a real weight is bundled for emphasis.
pub fn semibold() -> FontFamily {
    FontFamily::Name("semibold".into())
}

/// Register Inter (UI) and Gloock (titles). Call once, before the first frame.
pub fn install(ctx: &egui::Context) {
    let mut fonts = FontDefinitions::default();
    fonts
        .font_data
        .insert("inter".to_owned(), Arc::new(FontData::from_static(INTER)));
    fonts.font_data.insert(
        "inter-semibold".to_owned(),
        Arc::new(FontData::from_static(INTER_SEMIBOLD)),
    );
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

    // Semibold emphasis; fall back to egui's default fonts for missing glyphs.
    fonts.families.insert(
        FontFamily::Name("semibold".into()),
        vec!["inter-semibold".to_owned(), "inter".to_owned()],
    );

    ctx.set_fonts(fonts);
}
