// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! The design system — Yoink's "Flat Minimal" look expressed as typed tokens.
//!
//! This replaces the Tailwind utility classes of the web UI with one typed source
//! of truth: a [`Palette`] of semantic colors (dark + light), plus one [`apply`]
//! that maps it onto egui's [`egui::Visuals`] and sizing. There is no CSS, no
//! class strings — a widget just reads the ambient style egui already carries.

use egui::{Color32, Stroke};

/// Semantic colors. Names describe *role*, not hue, so the two palettes stay
/// swappable and components never reach for a literal color.
#[derive(Clone, Copy)]
pub struct Palette {
    pub canvas: Color32,     // the window background
    pub surface: Color32,    // cards / raised panels
    pub surface_hi: Color32, // inputs / insets
    pub line: Color32,       // hairline borders, dividers
    pub fg: Color32,         // primary text
    pub fg_dim: Color32,     // secondary text
    pub accent: Color32,     // the brand accent (actions, focus)
    pub accent_fg: Color32,  // text/icon on the accent
    pub ok: Color32,         // success
    pub err: Color32,        // error
}

const fn rgb(r: u8, g: u8, b: u8) -> Color32 {
    Color32::from_rgb(r, g, b)
}

/// Dark is the default, as in the web UI.
pub const DARK: Palette = Palette {
    canvas: rgb(0x0f, 0x11, 0x15),
    surface: rgb(0x17, 0x1a, 0x21),
    surface_hi: rgb(0x1e, 0x22, 0x2b),
    line: rgb(0x2a, 0x2f, 0x3a),
    fg: rgb(0xe8, 0xea, 0xed),
    fg_dim: rgb(0x9a, 0xa0, 0xad),
    accent: rgb(0x7c, 0x3a, 0xed),
    accent_fg: rgb(0xff, 0xff, 0xff),
    ok: rgb(0x2e, 0xa4, 0x4f),
    err: rgb(0xe5, 0x48, 0x4d),
};

pub const LIGHT: Palette = Palette {
    canvas: rgb(0xf7, 0xf8, 0xfa),
    surface: rgb(0xff, 0xff, 0xff),
    surface_hi: rgb(0xf0, 0xf2, 0xf5),
    line: rgb(0xe2, 0xe5, 0xea),
    fg: rgb(0x1a, 0x1d, 0x23),
    fg_dim: rgb(0x5c, 0x63, 0x70),
    accent: rgb(0x7c, 0x3a, 0xed),
    accent_fg: rgb(0xff, 0xff, 0xff),
    ok: rgb(0x2e, 0xa4, 0x4f),
    err: rgb(0xe5, 0x48, 0x4d),
};

/// The palette currently in force (dark unless the viewer chose light).
pub fn palette(dark: bool) -> Palette {
    if dark {
        DARK
    } else {
        LIGHT
    }
}

/// Map a palette onto egui's style for the whole app. Call on startup and whenever
/// the theme toggles.
pub fn apply(ctx: &egui::Context, dark: bool) {
    let p = palette(dark);
    let mut v = if dark {
        egui::Visuals::dark()
    } else {
        egui::Visuals::light()
    };

    v.override_text_color = Some(p.fg);
    v.panel_fill = p.canvas;
    v.window_fill = p.surface;
    v.extreme_bg_color = p.surface_hi;
    v.faint_bg_color = p.surface;
    v.window_stroke = Stroke::new(1.0, p.line);
    v.hyperlink_color = p.accent;
    v.selection.bg_fill = p.accent.gamma_multiply(0.35);
    v.selection.stroke = Stroke::new(1.0, p.accent);

    v.widgets.noninteractive.bg_fill = p.surface;
    v.widgets.noninteractive.bg_stroke = Stroke::new(1.0, p.line);
    v.widgets.noninteractive.fg_stroke = Stroke::new(1.0, p.fg_dim);

    v.widgets.inactive.bg_fill = p.surface_hi;
    v.widgets.inactive.weak_bg_fill = p.surface_hi;
    v.widgets.inactive.bg_stroke = Stroke::new(1.0, p.line);
    v.widgets.inactive.fg_stroke = Stroke::new(1.0, p.fg);

    v.widgets.hovered.bg_fill = p.line;
    v.widgets.hovered.weak_bg_fill = p.line;
    v.widgets.hovered.bg_stroke = Stroke::new(1.0, p.accent);
    v.widgets.hovered.fg_stroke = Stroke::new(1.0, p.fg);

    v.widgets.active.bg_fill = p.accent;
    v.widgets.active.weak_bg_fill = p.accent;
    v.widgets.active.bg_stroke = Stroke::new(1.0, p.accent);
    v.widgets.active.fg_stroke = Stroke::new(1.0, p.accent_fg);

    ctx.set_visuals(v);

    ctx.global_style_mut(|style| {
        style.spacing.item_spacing = egui::vec2(8.0, 8.0);
        style.spacing.button_padding = egui::vec2(12.0, 7.0);

        use egui::{FontFamily::Proportional, FontId, TextStyle};
        style.text_styles = [
            (TextStyle::Heading, FontId::new(24.0, Proportional)),
            (TextStyle::Body, FontId::new(15.0, Proportional)),
            (TextStyle::Button, FontId::new(15.0, Proportional)),
            (TextStyle::Small, FontId::new(12.0, Proportional)),
            (
                TextStyle::Monospace,
                FontId::new(13.0, egui::FontFamily::Monospace),
            ),
        ]
        .into();
    });
}
