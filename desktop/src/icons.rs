// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Lucide line icons (the same set the web UI uses), bundled as SVG with a white
//! stroke and tinted at paint time through egui's SVG loader. `img(name, size,
//! color)` returns an [`egui::Image`] ready to add inline or inside a button.

use egui::{Color32, Image, Vec2};

macro_rules! svg {
    ($file:literal) => {
        include_bytes!(concat!("../assets/icons/", $file, ".svg")) as &[u8]
    };
}

/// Map a friendly name to its bundled lucide SVG bytes.
fn bytes(name: &str) -> (&'static str, &'static [u8]) {
    match name {
        "home" => ("house", svg!("house")),
        "queue" => ("list-music", svg!("list-music")),
        "history" => ("history", svg!("history")),
        "settings" => ("settings", svg!("settings")),
        "logs" => ("scroll-text", svg!("scroll-text")),
        "search" => ("search", svg!("search")),
        "paste" => ("clipboard", svg!("clipboard")),
        "download" => ("download", svg!("download")),
        "cloud" => ("cloud", svg!("download-cloud")),
        "youtube" => ("youtube", svg!("youtube")),
        "play" => ("play", svg!("play")),
        "add" => ("list-plus", svg!("list-plus")),
        "options" => ("sliders", svg!("sliders-horizontal")),
        "music" => ("music", svg!("music")),
        "video" => ("video", svg!("video")),
        "check" => ("check", svg!("circle-check-big")),
        "folder" => ("folder", svg!("folder-open")),
        "chevron" => ("chevron", svg!("chevron-down")),
        "chevron-up" => ("chevron-up", svg!("chevron-up")),
        "chevron-right" => ("chevron-right", svg!("chevron-right")),
        "coffee" => ("coffee", svg!("coffee")),
        "github" => ("github", svg!("github")),
        "moon" => ("moon", svg!("moon")),
        "sun" => ("sun", svg!("sun")),
        "trash" => ("trash", svg!("trash-2")),
        "plus" => ("plus", svg!("plus")),
        "x" => ("x", svg!("x")),
        "help" => ("help", svg!("circle-help")),
        "globe" => ("globe", svg!("globe")),
        "sparkles" => ("sparkles", svg!("sparkles")),
        _ => ("help", svg!("circle-help")),
    }
}

/// A supported-site brand logo (bundled from simple-icons), tinted at paint time.
pub fn site_img(slug: &str, size: f32, color: Color32) -> Image<'static> {
    macro_rules! s {
        ($f:literal) => {
            include_bytes!(concat!("../assets/icons/sites/", $f, ".svg")) as &[u8]
        };
    }
    let data: &[u8] = match slug {
        "youtube" => s!("youtube"),
        "dailymotion" => s!("dailymotion"),
        "tiktok" => s!("tiktok"),
        "facebook" => s!("facebook"),
        "instagram" => s!("instagram"),
        "threads" => s!("threads"),
        "x" => s!("x"),
        "reddit" => s!("reddit"),
        "bluesky" => s!("bluesky"),
        "pinterest" => s!("pinterest"),
        "vk" => s!("vk"),
        "vimeo" => s!("vimeo"),
        "twitch" => s!("twitch"),
        "kick" => s!("kick"),
        "medal" => s!("medal"),
        "youtubemusic" => s!("youtubemusic"),
        "spotify" => s!("spotify"),
        "deezer" => s!("deezer"),
        "applemusic" => s!("applemusic"),
        "tidal" => s!("tidal"),
        "amazonmusic" => s!("amazonmusic"),
        "soundcloud" => s!("soundcloud"),
        "bandlab" => s!("bandlab"),
        "bandcamp" => s!("bandcamp"),
        _ => s!("youtube"),
    };
    Image::from_bytes(format!("bytes://site/{slug}.svg"), data)
        .fit_to_exact_size(Vec2::splat(size))
        .tint(color)
}

/// An icon tinted to `color`, sized `size`×`size`.
pub fn img(name: &str, size: f32, color: Color32) -> Image<'static> {
    let (key, data) = bytes(name);
    Image::from_bytes(format!("bytes://icon/{key}.svg"), data)
        .fit_to_exact_size(Vec2::splat(size))
        .tint(color)
}

/// Add an icon inline (as a widget), vertically centered with surrounding text.
pub fn show(ui: &mut egui::Ui, name: &str, size: f32, color: Color32) {
    ui.add(img(name, size, color));
}

/// Add a supported-site brand logo inline.
pub fn show_site(ui: &mut egui::Ui, slug: &str, size: f32, color: Color32) {
    ui.add(site_img(slug, size, color));
}
