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

/// Dark is the default, as in the web UI. Values mirror the `--c-*` tokens in
/// `src/index.css` (violet accent, near-neutral deep surfaces).
pub const DARK: Palette = Palette {
    canvas: rgb(10, 10, 12),     // #0a0a0c
    surface: rgb(20, 20, 23),    // #141417
    surface_hi: rgb(27, 27, 32), // #1b1b20 (surface-2)
    line: rgb(42, 42, 48),       // #eceaf0 @ ~10% over surface
    fg: rgb(236, 234, 240),      // #eceaf0
    fg_dim: rgb(147, 143, 158),  // #938f9e
    accent: rgb(139, 92, 246),   // #8b5cf6 violet-500
    accent_fg: rgb(255, 255, 255),
    ok: rgb(52, 199, 123),
    err: rgb(239, 83, 80),
};

pub const LIGHT: Palette = Palette {
    canvas: rgb(246, 245, 248),     // #f6f5f8
    surface: rgb(255, 255, 255),    // #ffffff
    surface_hi: rgb(240, 238, 244), // #f0eef4 (surface-2)
    line: rgb(224, 222, 228),       // #14101e @ low alpha over white
    fg: rgb(23, 21, 29),            // #17151d
    fg_dim: rgb(95, 91, 107),       // #5f5b6b
    accent: rgb(124, 58, 237),      // #7c3aed violet-600
    accent_fg: rgb(255, 255, 255),
    ok: rgb(34, 150, 83),
    err: rgb(214, 54, 56),
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

    // No hover/active expansion: egui grows the widget rect but clips its paint to
    // the original rect, so an expanded fill/stroke gets its corners clipped (a
    // focused combo looked cut on the right). Keep every state the same size.
    v.widgets.noninteractive.expansion = 0.0;
    v.widgets.inactive.expansion = 0.0;
    v.widgets.hovered.expansion = 0.0;
    v.widgets.active.expansion = 0.0;
    v.widgets.open.expansion = 0.0;

    ctx.set_visuals(v);

    ctx.global_style_mut(|style| {
        style.spacing.item_spacing = egui::vec2(8.0, 8.0);
        style.spacing.button_padding = egui::vec2(12.0, 7.0);
        // A thin, unobtrusive scrollbar instead of egui's thick default.
        let mut scroll = egui::style::ScrollStyle::thin();
        scroll.bar_width = 6.0;
        scroll.floating = true;
        scroll.dormant_handle_opacity = 0.0;
        scroll.interact_handle_opacity = 0.6;
        scroll.active_handle_opacity = 0.7;
        style.spacing.scroll = scroll;

        use egui::{FontFamily::Proportional, FontId, TextStyle};
        style.text_styles = [
            (
                TextStyle::Heading,
                FontId::new(24.0, crate::fonts::display()),
            ),
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
