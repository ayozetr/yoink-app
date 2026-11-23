// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! The `yoink` command line. When `yoink-core` is launched with arguments it runs
//! this instead of serving the API — a terminal front-end that drives the exact
//! same engine (yt-dlp + ffmpeg) and writes to the same history/settings.

use std::io::{Read, Write};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use clap::{CommandFactory, Parser};

use crate::music::MusicTrack;

const VR_LAYOUTS: &[&str] = &[
    "180_sbs",
    "180_tb",
    "180_mono",
    "360_sbs",
    "360_tb",
    "360_mono",
    "fisheye190",
    "fisheye200",
    "mkx200",
    "mkx220",
    "rf52",
];

#[derive(Parser, Debug)]
#[command(
    name = "yoink",
    version,
    about = "Download high-fidelity video/audio from ~1800 sites (yt-dlp + ffmpeg).",
    after_help = "settings: 'yoink config' prints them; 'yoink config get|set KEY [VALUE]' reads/edits them."
)]
pub struct Cli {
    /// URLs to download (or `config …`). Use `-` to read URLs from stdin.
    #[arg(value_name = "URL")]
    urls: Vec<String>,

    /// Read URLs from a file (repeatable); only http(s) links are taken.
    #[arg(short = 'a', long = "batch-file", value_name = "FILE")]
    batch_file: Vec<String>,

    /// Download audio only.
    #[arg(long, conflicts_with = "video")]
    audio: bool,
    /// Download video (default).
    #[arg(long)]
    video: bool,

    /// Audio format (audio downloads).
    #[arg(short = 'f', long, value_parser = ["mp3", "m4a", "opus", "flac", "wav"])]
    format: Option<String>,
    /// Video container.
    #[arg(short = 'c', long, value_parser = ["mp4", "mov", "mkv", "webm"])]
    container: Option<String>,
    /// Video quality, e.g. "1080", "720", "best".
    #[arg(short = 'q', long)]
    quality: Option<String>,
    /// Output directory.
    #[arg(short = 'o', long, value_name = "DIR")]
    output: Option<String>,
    /// yt-dlp output filename template.
    #[arg(short = 't', long = "filename-template", value_name = "TMPL")]
    filename_template: Option<String>,

    #[arg(long = "rate-limit", value_name = "RATE")]
    rate_limit: Option<String>,
    #[arg(long, value_name = "URL")]
    proxy: Option<String>,
    #[arg(long = "cookies-from-browser", value_name = "BROWSER")]
    cookies_from_browser: Option<String>,
    #[arg(long = "cookies-file", value_name = "FILE")]
    cookies_file: Option<String>,
    /// SponsorBlock: remove (default) or mark.
    #[arg(long, num_args = 0..=1, default_missing_value = "remove", value_parser = ["remove", "mark"])]
    sponsorblock: Option<String>,
    /// Loudness-normalize audio to -14 LUFS.
    #[arg(long)]
    normalize: bool,
    /// Loudness target in LUFS (implies --normalize).
    #[arg(long = "normalize-lufs", value_name = "LUFS")]
    normalize_lufs: Option<i32>,
    #[arg(long = "video-codec", value_parser = ["any", "h264", "h265", "vp9", "av1"])]
    video_codec: Option<String>,
    #[arg(long = "audio-bitrate", value_parser = ["best", "320", "256", "192", "128"])]
    audio_bitrate: Option<String>,

    /// Trim start, e.g. "90", "1:30", "1:02:03".
    #[arg(long = "trim-start", value_name = "TS")]
    trim_start: Option<String>,
    #[arg(long = "trim-end", value_name = "TS")]
    trim_end: Option<String>,

    /// Embed subtitles (video); optional LANG, else all.
    #[arg(long, num_args = 0..=1, default_missing_value = "all", value_name = "LANG")]
    subs: Option<String>,
    #[arg(long = "no-subs")]
    no_subs: bool,
    #[arg(long)]
    chapters: bool,
    #[arg(long = "no-chapters")]
    no_chapters: bool,

    /// Tag the download as VR (auto-detect the layout).
    #[arg(long)]
    vr: bool,
    /// Force a VR layout (implies --vr).
    #[arg(long = "vr-layout", value_parser = clap::builder::PossibleValuesParser::new(VR_LAYOUTS))]
    vr_layout: Option<String>,

    /// Select playlist/import items, e.g. "1,3-5".
    #[arg(long, value_name = "SPEC")]
    items: Option<String>,
    /// Only items whose title contains TEXT.
    #[arg(long, value_name = "TEXT")]
    filter: Option<String>,
    /// Skip items already in the download history.
    #[arg(long = "skip-existing")]
    skip_existing: bool,

    /// Auto-tag audio from the catalogue after download.
    #[arg(long)]
    tag: bool,
    #[arg(long = "no-tag")]
    no_tag: bool,

    /// Print metadata instead of downloading.
    #[arg(long)]
    info: bool,
    /// List playlist/import entries instead of downloading.
    #[arg(long)]
    list: bool,
    /// List a single video's available formats.
    #[arg(long = "list-formats")]
    list_formats: bool,

    /// Machine-readable JSON output.
    #[arg(long)]
    json: bool,
    /// Suppress non-essential output.
    #[arg(long)]
    quiet: bool,
    /// Hide the progress bar.
    #[arg(long = "no-progress")]
    no_progress: bool,
    /// Print a shell completion script and exit.
    #[arg(long = "print-completion", value_parser = ["bash", "zsh", "fish"])]
    print_completion: Option<String>,
}

enum Tag {
    Catalog,
    Music(Box<MusicTrack>),
}

fn fail(msg: &str, as_json: bool) {
    if as_json {
        println!("{}", serde_json::json!({ "error": msg }));
    } else {
        eprintln!("yoink: {msg}");
    }
}

/// Parse "SS", "MM:SS" or "HH:MM:SS" into seconds.
fn parse_timestamp(v: &str) -> Option<f64> {
    let parts: Vec<&str> = v.split(':').collect();
    if parts.is_empty() || parts.len() > 3 {
        return None;
    }
    let mut secs = 0f64;
    for p in &parts {
        secs = secs * 60.0 + p.trim().parse::<f64>().ok()?;
    }
    Some(secs)
}

fn show_progress(args: &Cli) -> bool {
    !(args.no_progress || args.quiet)
}

fn render_progress(p: &crate::ProgressInfo, prefix: &str) {
    const W: usize = 22;
    let filled = ((p.percent / 100.0) * W as f64).round() as usize;
    let filled = filled.min(W);
    let bar: String = "█".repeat(filled) + &"░".repeat(W - filled);
    let speed = p.speed.as_deref().unwrap_or("");
    let eta = p
        .eta
        .as_deref()
        .map(|e| format!("ETA {e}"))
        .unwrap_or_default();
    eprint!("\r{prefix}{bar} {:>5.1}% {speed} {eta}    ", p.percent);
    let _ = std::io::stderr().flush();
}

fn apply_cli_overrides(args: &Cli, settings: &mut crate::AppSettings) {
    if let Some(o) = &args.output {
        settings.download_dir = shellexpand(o);
    }
    if let Some(t) = &args.filename_template {
        settings.filename_template = t.clone();
    }
    if let Some(r) = &args.rate_limit {
        settings.rate_limit = Some(r.clone());
    }
    if let Some(p) = &args.proxy {
        settings.proxy = Some(p.clone());
    }
    if let Some(b) = &args.cookies_from_browser {
        settings.cookies_from_browser = Some(b.clone());
    }
    if let Some(f) = &args.cookies_file {
        settings.cookies_file = Some(shellexpand(f));
    }
    if let Some(sb) = &args.sponsorblock {
        settings.sponsorblock_enabled = true;
        settings.sponsorblock_action = sb.clone();
    }
    if args.normalize {
        settings.normalize_audio = true;
    }
    if let Some(l) = args.normalize_lufs {
        settings.normalize_audio = true;
        settings.normalize_lufs = l.clamp(-70, -5);
    }
}

fn shellexpand(p: &str) -> String {
    if let Some(rest) = p.strip_prefix("~/") {
        if let Ok(home) = std::env::var("HOME") {
            return format!("{home}/{rest}");
        }
    }
    p.to_string()
}

fn build_request(
    url: &str,
    args: &Cli,
    s: &crate::AppSettings,
    kind_override: Option<&str>,
) -> crate::DownloadRequest {
    let kind = kind_override.map(str::to_string).unwrap_or_else(|| {
        if args.audio {
            "audio".into()
        } else if args.video {
            "video".into()
        } else {
            s.default_kind.clone()
        }
    });
    let is_video = kind == "video";

    let (embed_subs, subtitle_lang) = if args.no_subs {
        (false, None)
    } else if let Some(sub) = &args.subs {
        (true, (sub != "all").then(|| sub.clone()))
    } else {
        (s.default_embed_subs, None)
    };
    let embed_chapters = if args.no_chapters {
        false
    } else if args.chapters {
        true
    } else {
        s.default_embed_chapters
    };

    crate::DownloadRequest {
        url: url.to_string(),
        kind,
        quality: args
            .quality
            .clone()
            .or_else(|| Some(s.default_quality.clone())),
        container: args
            .container
            .clone()
            .unwrap_or_else(|| s.default_container.clone()),
        audio_format: args
            .format
            .clone()
            .unwrap_or_else(|| s.default_audio_format.clone()),
        audio_bitrate: args.audio_bitrate.clone(),
        video_codec: args.video_codec.clone(),
        embed_subs: embed_subs && is_video,
        subtitle_lang: if is_video { subtitle_lang } else { None },
        embed_chapters,
        audio_multistreams: false,
        trim_start: args.trim_start.as_deref().and_then(parse_timestamp),
        trim_end: args.trim_end.as_deref().and_then(parse_timestamp),
        is_vr: is_video && args.vr_layout.is_some(),
        vr_layout: args.vr_layout.clone().or_else(|| Some("180_sbs".into())),
        auto_vr: is_video && args.vr && args.vr_layout.is_none(),
    }
}

async fn apply_catalog_tags(filepath: &str, settings: &crate::AppSettings) {
    let name = Path::new(filepath)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("");
    let (artist, title) = crate::autotag::guess_from_filename(name);
    if title.is_empty() {
        return;
    }
    let results = crate::autotag::search_catalogue(&settings.autotag_source, &artist, &title).await;
    let Some(c) = results.into_iter().next() else {
        return;
    };
    let cover = match c.cover_url.as_deref() {
        Some(u) if !u.is_empty() => crate::autotag::fetch_cover(u).await,
        _ => None,
    };
    let fields = crate::autotag::ApplyFields {
        path: filepath.to_string(),
        title: Some(c.title),
        artist: Some(c.artist),
        album: c.album,
        year: c.year,
        genre: c.genre,
        track_number: c.track_number.map(|n| n as u32),
        isrc: None,
        cover,
    };
    let _ = tokio::task::spawn_blocking(move || crate::autotag::write_tags(&fields)).await;
}

async fn apply_music_tags(filepath: &str, t: &MusicTrack) {
    let cover = match t.cover_url.as_deref() {
        Some(u) if !u.is_empty() => crate::autotag::fetch_cover(u).await,
        _ => None,
    };
    let fields = crate::autotag::ApplyFields {
        path: filepath.to_string(),
        title: Some(t.title.clone()),
        artist: Some(t.artists.clone()),
        album: t.album.clone(),
        year: t.year.clone(),
        genre: None,
        track_number: None,
        isrc: t.isrc.clone(),
        cover,
    };
    let _ = tokio::task::spawn_blocking(move || crate::autotag::write_tags(&fields)).await;
}

/// Download one request, record history, optionally tag. Returns success.
async fn download_one(
    req: &crate::DownloadRequest,
    settings: &crate::AppSettings,
    prefix: &str,
    progress: bool,
    as_json: bool,
    tag: Option<Tag>,
) -> bool {
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<crate::DlEvent>();
    let cancel = Arc::new(AtomicBool::new(false));
    let (r2, s2, c2) = (req.clone(), settings.clone(), cancel.clone());
    // Ctrl+C stops the download cleanly.
    tokio::spawn(async move {
        if tokio::signal::ctrl_c().await.is_ok() {
            c2.store(true, Ordering::Relaxed);
        }
    });
    let handle = tokio::spawn(async move { crate::execute_download(&r2, &s2, &tx, &cancel).await });

    let show_bar = progress && !as_json;
    let mut completed: Option<(String, String, Option<i64>)> = None;
    let mut error: Option<String> = None;
    while let Some(ev) = rx.recv().await {
        match ev {
            crate::DlEvent::Progress(p) => {
                if show_bar {
                    render_progress(&p, prefix);
                }
            }
            crate::DlEvent::Completed {
                filename,
                filepath,
                total_bytes,
            } => {
                completed = Some((filename, filepath, total_bytes));
            }
            crate::DlEvent::Error(m) => error = Some(m),
        }
    }
    let _ = handle.await;
    if show_bar {
        eprintln!();
    }

    match completed {
        Some((filename, filepath, total_bytes)) => {
            if req.kind == "audio" {
                match tag {
                    Some(Tag::Catalog) => apply_catalog_tags(&filepath, settings).await,
                    Some(Tag::Music(t)) => apply_music_tags(&filepath, &t).await,
                    None => {}
                }
            }
            if as_json {
                println!(
                    "{}",
                    serde_json::json!({ "status": "completed", "filename": filename, "filepath": filepath, "bytes": total_bytes })
                );
            } else {
                println!("{filepath}");
            }
            true
        }
        None => {
            fail(&error.unwrap_or_else(|| "cancelled".into()), as_json);
            false
        }
    }
}

fn parse_items(spec: &str) -> std::collections::HashSet<usize> {
    let mut out = std::collections::HashSet::new();
    for part in spec.split(',') {
        let part = part.trim();
        if let Some((a, b)) = part.split_once('-') {
            if let (Ok(a), Ok(b)) = (a.trim().parse::<usize>(), b.trim().parse::<usize>()) {
                for i in a..=b {
                    out.insert(i);
                }
            }
        } else if let Ok(n) = part.parse::<usize>() {
            out.insert(n);
        }
    }
    out
}

/// Apply --items / --filter to a 1-based list; `key` is each item's search text.
fn selected<'a, T>(entries: &'a [T], args: &Cli, key: impl Fn(&T) -> String) -> Vec<&'a T> {
    let items = args.items.as_deref().map(parse_items);
    entries
        .iter()
        .enumerate()
        .filter(|(i, e)| {
            let n = i + 1;
            if let Some(ref set) = items {
                if !set.contains(&n) {
                    return false;
                }
            }
            if let Some(ref f) = args.filter {
                if !key(e).to_lowercase().contains(&f.to_lowercase()) {
                    return false;
                }
            }
            true
        })
        .map(|(_, e)| e)
        .collect()
}

fn tag_for(args: &Cli) -> Option<Tag> {
    (args.tag && !args.no_tag).then_some(Tag::Catalog)
}

// --------------------------------------------------------------------- output

fn print_video_info(v: &crate::VideoInfo, as_json: bool) {
    if as_json {
        println!(
            "{}",
            serde_json::json!({
                "type": "video", "title": v.title, "uploader": v.uploader,
                "duration": v.duration_string, "has_audio": v.has_audio,
                "is_vr": v.is_vr, "formats": v.formats.len(), "webpage_url": v.webpage_url,
            })
        );
    } else {
        println!("Title:    {}", v.title);
        println!("Uploader: {}", v.uploader.as_deref().unwrap_or("—"));
        println!("Duration: {}", v.duration_string.as_deref().unwrap_or("—"));
        println!("Audio:    {}", if v.has_audio { "yes" } else { "no" });
        if v.is_vr {
            println!("VR:       {}", v.vr_layout);
        }
        println!("Formats:  {}", v.formats.len());
    }
}

fn print_formats(v: &crate::VideoInfo, as_json: bool) {
    if as_json {
        let fmts: Vec<_> = v
            .formats
            .iter()
            .map(|f| {
                serde_json::json!({
                    "format_id": f.format_id, "ext": f.ext, "resolution": f.resolution,
                    "fps": f.fps, "vcodec": f.vcodec, "acodec": f.acodec, "filesize": f.filesize,
                })
            })
            .collect();
        println!(
            "{}",
            serde_json::json!({ "title": v.title, "formats": fmts })
        );
        return;
    }
    println!("{} — {} format(s)", v.title, v.formats.len());
    println!(
        "  {:<8} {:<5} {:<12} {:>4} {:<10} {:<10} SIZE",
        "ID", "EXT", "RESOLUTION", "FPS", "VCODEC", "ACODEC"
    );
    for f in &v.formats {
        let size = f
            .filesize
            .map(crate::humanize_bytes)
            .unwrap_or_else(|| "—".into());
        let fps = f.fps.map(|x| (x as i64).to_string()).unwrap_or_default();
        println!(
            "  {:<8} {:<5} {:<12} {:>4} {:<10} {:<10} {size}",
            f.format_id,
            f.ext,
            f.resolution.as_deref().unwrap_or("—"),
            fps,
            f.vcodec.as_deref().unwrap_or("—"),
            f.acodec.as_deref().unwrap_or("—"),
        );
    }
}

fn print_entries(title: &str, count: usize, rows: &[(String, Option<String>)], as_json: bool) {
    if as_json {
        let entries: Vec<_> = rows
            .iter()
            .enumerate()
            .map(|(i, (t, d))| serde_json::json!({ "n": i + 1, "title": t, "duration": d }))
            .collect();
        println!(
            "{}",
            serde_json::json!({ "title": title, "count": count, "entries": entries })
        );
    } else {
        println!("{title} — {count} item(s)");
        for (i, (label, dur)) in rows.iter().enumerate() {
            let d = dur
                .as_deref()
                .map(|d| format!("  [{d}]"))
                .unwrap_or_default();
            println!("  {:>3}. {label}{d}", i + 1);
        }
    }
}

// --------------------------------------------------------------- url collection

fn extract_urls(text: &str) -> Vec<String> {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    let re = RE.get_or_init(|| regex::Regex::new(r#"(?i)https?://[^\s'"<>]+"#).unwrap());
    re.find_iter(text)
        .map(|m| {
            m.as_str()
                .trim_end_matches(['.', ',', ';', ')', ']', '}', '"', '\''])
                .to_string()
        })
        .collect()
}

fn read_stdin() -> String {
    let mut s = String::new();
    let _ = std::io::stdin().read_to_string(&mut s);
    s
}

fn collect_urls(args: &Cli) -> Vec<String> {
    let mut raw: Vec<String> = Vec::new();
    for u in &args.urls {
        if u == "-" {
            raw.extend(extract_urls(&read_stdin()));
        } else {
            raw.push(u.clone());
        }
    }
    for path in &args.batch_file {
        let text = if path == "-" {
            read_stdin()
        } else {
            match std::fs::read_to_string(shellexpand(path)) {
                Ok(t) => t,
                Err(e) => {
                    fail(&format!("cannot read {path}: {e}"), args.json);
                    continue;
                }
            }
        };
        raw.extend(extract_urls(&text));
    }
    let mut seen = std::collections::HashSet::new();
    raw.into_iter().filter(|u| seen.insert(u.clone())).collect()
}

fn looks_like_playlist(url: &str) -> bool {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    RE.get_or_init(|| regex::Regex::new(r"(?i)([?&]list=|/playlist\b|/sets/)").unwrap())
        .is_match(url)
}

// ------------------------------------------------------------------- config

fn run_config(rest: &[String], as_json: bool) -> i32 {
    let settings = crate::load_settings();
    let mut map = match serde_json::to_value(&settings) {
        Ok(serde_json::Value::Object(m)) => m,
        _ => {
            fail("could not read settings", as_json);
            return 1;
        }
    };
    if rest.is_empty() {
        if as_json {
            println!("{}", serde_json::to_string_pretty(&map).unwrap_or_default());
        } else {
            let mut keys: Vec<_> = map.keys().cloned().collect();
            keys.sort();
            for k in keys {
                println!("{k} = {}", fmt_val(&map[&k]));
            }
        }
        return 0;
    }
    match rest[0].as_str() {
        "get" if rest.len() == 2 && map.contains_key(&rest[1]) => {
            let v = &map[&rest[1]];
            println!("{}", if as_json { v.to_string() } else { fmt_val(v) });
            0
        }
        "set" if rest.len() >= 3 && map.contains_key(&rest[1]) => {
            let key = &rest[1];
            let raw = rest[2..].join(" ");
            map.insert(key.clone(), coerce_setting(&map[key], &raw));
            match serde_json::from_value::<crate::AppSettings>(serde_json::Value::Object(map)) {
                Ok(updated) => {
                    if let Err(e) = crate::save_settings(&updated) {
                        fail(&format!("could not save: {e}"), as_json);
                        return 1;
                    }
                    let m = serde_json::to_value(&updated).unwrap_or_default();
                    println!("{key} = {}", fmt_val(&m[key]));
                    0
                }
                Err(e) => {
                    fail(&format!("invalid value for {key}: {e}"), as_json);
                    2
                }
            }
        }
        "get" => {
            fail("usage: yoink config get KEY", as_json);
            2
        }
        "set" => {
            fail("usage: yoink config set KEY VALUE", as_json);
            2
        }
        _ => {
            fail("usage: yoink config [get KEY | set KEY VALUE]", as_json);
            2
        }
    }
}

fn fmt_val(v: &serde_json::Value) -> String {
    match v {
        serde_json::Value::String(s) => s.clone(),
        serde_json::Value::Null => String::new(),
        other => other.to_string(),
    }
}

fn coerce_setting(current: &serde_json::Value, value: &str) -> serde_json::Value {
    let low = value.trim().to_lowercase();
    if current.is_boolean() {
        return serde_json::Value::Bool(matches!(low.as_str(), "1" | "true" | "yes" | "on"));
    }
    if current.is_number() {
        if let Ok(n) = value.trim().parse::<i64>() {
            return serde_json::json!(n);
        }
    }
    if matches!(low.as_str(), "none" | "null" | "") {
        return serde_json::Value::Null;
    }
    serde_json::Value::String(value.to_string())
}

// --------------------------------------------------------------------- flows

async fn run_playlist(
    entries: &[crate::PlaylistEntry],
    args: &Cli,
    settings: &crate::AppSettings,
) -> i32 {
    let picked = selected(entries, args, |e| e.title.clone());
    if picked.is_empty() {
        eprintln!("nothing to download");
        return 0;
    }
    let tag = tag_for(args);
    let (total, mut ok) = (picked.len(), 0);
    for (n, e) in picked.iter().enumerate() {
        let prefix = format!("[{}/{total}] ", n + 1);
        let req = build_request(&e.url, args, settings, None);
        let t = if req.kind == "audio" {
            tag_for(args)
        } else {
            None
        };
        let _ = &tag; // tag_for is cheap; recompute per item
        if download_one(&req, settings, &prefix, show_progress(args), args.json, t).await {
            ok += 1;
        }
    }
    if !args.quiet {
        eprintln!("\n{ok}/{total} downloaded.");
    }
    if ok == total {
        0
    } else {
        1
    }
}

async fn run_music(
    info: &crate::music::MusicImportInfo,
    args: &Cli,
    settings: &crate::AppSettings,
) -> i32 {
    let picked = selected(&info.tracks, args, |t| format!("{} {}", t.artists, t.title));
    if picked.is_empty() {
        eprintln!("nothing to download");
        return 0;
    }
    let (total, mut ok) = (picked.len(), 0);
    for (n, t) in picked.iter().enumerate() {
        let short: String = t.title.chars().take(28).collect();
        let prefix = format!("[{}/{total}] {} — {}  ", n + 1, t.artists, short);
        let isrc = match t.isrc.as_deref() {
            Some(i) if !i.is_empty() => Some(i.to_string()),
            _ => crate::music::deezer_isrc(&t.title, &t.artists, t.duration_ms).await,
        };
        let url = crate::find_youtube_match(
            &t.title,
            &t.artists,
            t.duration_ms,
            isrc.as_deref(),
            settings,
        )
        .await;
        let Some(url) = url else {
            eprintln!("\r{prefix}no YouTube match");
            continue;
        };
        let req = build_request(&url, args, settings, Some("audio"));
        let tag = if args.no_tag {
            None
        } else {
            Some(Tag::Music(Box::new((*t).clone())))
        };
        if download_one(&req, settings, &prefix, show_progress(args), args.json, tag).await {
            ok += 1;
        }
    }
    if !args.quiet {
        eprintln!("\n{ok}/{total} imported.");
    }
    if ok == total {
        0
    } else {
        1
    }
}

async fn dispatch_url(url: &str, args: &Cli, settings: &crate::AppSettings) -> i32 {
    // Music-service URL (Spotify/Deezer/Apple/Tidal/Amazon).
    if crate::music::detect_source(url).is_some() {
        let info = match crate::resolve_music(url).await {
            Ok(i) => i,
            Err(e) => {
                fail(&e, args.json);
                return 1;
            }
        };
        if args.info || args.list {
            let rows: Vec<_> = info
                .tracks
                .iter()
                .map(|t| (format!("{} — {}", t.artists, t.title), None))
                .collect();
            print_entries(
                &format!("{}: {}", title_case(&info.kind), info.name),
                info.tracks.len(),
                &rows,
                args.json,
            );
            return 0;
        }
        return run_music(&info, args, settings).await;
    }

    // Analyze only when we might need the listing.
    if args.info || args.list || args.list_formats || looks_like_playlist(url) {
        match crate::fetch_info_response(url, settings).await {
            Ok(resp) => {
                if let Some(pl) = resp.playlist {
                    if args.list_formats {
                        fail(
                            "--list-formats needs a single video, not a playlist",
                            args.json,
                        );
                        return 2;
                    }
                    if args.info || args.list {
                        let rows: Vec<_> = pl
                            .entries
                            .iter()
                            .map(|e| (e.title.clone(), e.duration_string.clone()))
                            .collect();
                        print_entries(
                            &format!("Playlist: {}", pl.title),
                            pl.entry_count,
                            &rows,
                            args.json,
                        );
                        return 0;
                    }
                    return run_playlist(&pl.entries, args, settings).await;
                }
                if let Some(v) = resp.video {
                    if args.list_formats {
                        print_formats(&v, args.json);
                        return 0;
                    }
                    if args.info || args.list {
                        print_video_info(&v, args.json);
                        return 0;
                    }
                }
            }
            Err((_t, e)) => {
                fail(&e, args.json);
                return 1;
            }
        }
    }

    // Single download.
    let req = build_request(url, args, settings, None);
    let tag = if req.kind == "audio" {
        tag_for(args)
    } else {
        None
    };
    if download_one(&req, settings, "", show_progress(args), args.json, tag).await {
        0
    } else {
        1
    }
}

fn title_case(s: &str) -> String {
    let mut c = s.chars();
    match c.next() {
        Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
        None => String::new(),
    }
}

/// CLI entry point. Returns the process exit code.
pub async fn run(argv: Vec<String>) -> i32 {
    // `yoink config …` is handled before clap, so values like a negative LUFS
    // (`config set normalize_lufs -16`) aren't mistaken for flags.
    if argv.get(1).map(String::as_str) == Some("config") {
        let json = argv[2..].iter().any(|a| a == "--json");
        let rest: Vec<String> = argv[2..]
            .iter()
            .filter(|a| *a != "--json")
            .cloned()
            .collect();
        return run_config(&rest, json);
    }

    let args = match Cli::try_parse_from(&argv) {
        Ok(a) => a,
        Err(e) => {
            // clap prints help/usage/version; its exit code says which.
            let _ = e.print();
            return if e.use_stderr() { 2 } else { 0 };
        }
    };

    if let Some(shell) = &args.print_completion {
        let mut cmd = Cli::command();
        let gen = match shell.as_str() {
            "bash" => clap_complete::Shell::Bash,
            "zsh" => clap_complete::Shell::Zsh,
            _ => clap_complete::Shell::Fish,
        };
        clap_complete::generate(gen, &mut cmd, "yoink", &mut std::io::stdout());
        return 0;
    }

    if let (Some(a), Some(b)) = (
        args.trim_start.as_deref().and_then(parse_timestamp),
        args.trim_end.as_deref().and_then(parse_timestamp),
    ) {
        if b <= a {
            fail("--trim-end must be greater than --trim-start", args.json);
            return 2;
        }
    }

    let mut settings = crate::load_settings();
    apply_cli_overrides(&args, &mut settings);

    let urls = collect_urls(&args);
    if urls.is_empty() {
        fail(
            "no URL given (pass a URL, -a FILE, or - to read from stdin)",
            args.json,
        );
        return 2;
    }

    if urls.len() == 1 {
        return dispatch_url(&urls[0], &args, &settings).await;
    }
    let total = urls.len();
    let mut failed = false;
    for (i, u) in urls.iter().enumerate() {
        if !args.quiet {
            eprintln!("\n[{}/{total}] {u}", i + 1);
        }
        if dispatch_url(u, &args, &settings).await != 0 {
            failed = true;
        }
    }
    if failed {
        1
    } else {
        0
    }
}

#[cfg(test)]
mod cli_tests {
    use super::parse_timestamp;

    #[test]
    fn parse_timestamp_formats() {
        assert_eq!(parse_timestamp("90"), Some(90.0));
        assert_eq!(parse_timestamp("1:30"), Some(90.0));
        assert_eq!(parse_timestamp("1:02:03"), Some(3723.0));
        assert_eq!(parse_timestamp("0"), Some(0.0));
        assert_eq!(parse_timestamp("x"), None);
        assert_eq!(parse_timestamp("1:2:3:4"), None); // >3 parts
    }
}
