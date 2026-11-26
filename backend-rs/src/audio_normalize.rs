// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! EBU R128 loudness normalization (ffmpeg two-pass `loudnorm`), ported from
//! audio_normalize.py. Brings an audio download to a fixed integrated loudness
//! (-14 LUFS by default, the streaming standard): measure the file, then
//! re-encode applying the measured values. Best-effort — any failure leaves the
//! original file untouched and returns false, so a hiccup never loses a download.

use std::path::Path;
use std::process::Command;

use regex::Regex;
use serde_json::Value;

const TARGET_TP: f64 = -1.5;
const TARGET_LRA: f64 = 11.0;

/// ffmpeg/ffprobe binary: prefer the bundled dir (`YOINK_FFMPEG`), else PATH.
fn bin(name: &str) -> String {
    match std::env::var("YOINK_FFMPEG") {
        Ok(dir) => Path::new(&dir).join(name).to_string_lossy().into_owned(),
        Err(_) => name.to_string(),
    }
}

// A corrupt or absurdly long input can hang loudnorm/ffmpeg; cap each run so one
// bad file never wedges a download worker (generous — a legit two-pass re-encode
// of a long track finishes well under this). Mirrors _FFMPEG/_FFPROBE_TIMEOUT.
const FFMPEG_TIMEOUT_SECS: u64 = 1800;
const FFPROBE_TIMEOUT_SECS: u64 = 60;

/// Run a command with a wall-clock timeout, draining stdout/stderr in threads so
/// a verbose process can't deadlock on a full pipe. Returns None on a spawn error
/// or a timeout (the child is killed), so callers treat it as a failure.
fn run_timed(mut cmd: Command, secs: u64) -> Option<std::process::Output> {
    use std::io::Read;
    let mut child = cmd
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .ok()?;
    let mut out_pipe = child.stdout.take();
    let mut err_pipe = child.stderr.take();
    let h_out = std::thread::spawn(move || {
        let mut b = Vec::new();
        if let Some(ref mut s) = out_pipe {
            let _ = s.read_to_end(&mut b);
        }
        b
    });
    let h_err = std::thread::spawn(move || {
        let mut b = Vec::new();
        if let Some(ref mut s) = err_pipe {
            let _ = s.read_to_end(&mut b);
        }
        b
    });
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(secs);
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                return Some(std::process::Output {
                    status,
                    stdout: h_out.join().unwrap_or_default(),
                    stderr: h_err.join().unwrap_or_default(),
                });
            }
            Ok(None) => {
                if std::time::Instant::now() >= deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    return None;
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            Err(_) => return None,
        }
    }
}

fn run_ffmpeg(args: &[String]) -> Option<std::process::Output> {
    let mut cmd = Command::new(bin("ffmpeg"));
    crate::hide_console_std(&mut cmd);
    cmd.stdin(std::process::Stdio::null());
    cmd.arg("-hide_banner").arg("-nostdin").args(args);
    run_timed(cmd, FFMPEG_TIMEOUT_SECS)
}

fn ffprobe(args: &[&str]) -> Option<String> {
    let mut cmd = Command::new(bin("ffprobe"));
    crate::hide_console_std(&mut cmd);
    cmd.stdin(std::process::Stdio::null());
    cmd.args(args);
    let out = run_timed(cmd, FFPROBE_TIMEOUT_SECS)?;
    Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

/// First pass: measure loudness; returns loudnorm's measured JSON values.
fn measure(path: &str, target_i: f64) -> Option<Value> {
    let filt = format!("loudnorm=I={target_i}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json");
    let out = run_ffmpeg(&[
        "-i".into(),
        path.to_string(),
        "-af".into(),
        filt,
        "-f".into(),
        "null".into(),
        "-".into(),
    ])?;
    // loudnorm prints its JSON to stderr; pick the last brace block that actually
    // holds the measured values, not merely the first `{...}` in ffmpeg's log.
    let stderr = String::from_utf8_lossy(&out.stderr);
    let re = Regex::new(r"\{[^{}]+\}").ok()?;
    for block in re
        .find_iter(&stderr)
        .map(|m| m.as_str())
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
    {
        if block.contains("\"input_i\"") {
            return serde_json::from_str(block).ok();
        }
    }
    None
}

/// The audio's sample rate (Hz), so the re-encode preserves it instead of
/// leaving loudnorm's internal 192 kHz. Falls back to 44100.
fn sample_rate(path: &str) -> String {
    let rate = ffprobe(&[
        "-v",
        "quiet",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate",
        "-of",
        "csv=p=0",
        path,
    ])
    .unwrap_or_default();
    if !rate.is_empty() && rate.chars().all(|c| c.is_ascii_digit()) {
        rate
    } else {
        "44100".to_string()
    }
}

/// True if the file carries an attached-picture (embedded cover) stream.
fn has_cover(path: &str) -> bool {
    ffprobe(&[
        "-v",
        "quiet",
        "-select_streams",
        "v",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        path,
    ])
    .map(|s| s.contains("video"))
    .unwrap_or(false)
}

/// Two-pass loudness-normalize `path` in place to `target_i` LUFS. Returns
/// whether the file was rewritten.
pub fn normalize(path: &str, audio_format: &str, bitrate: &str, target_i: f64) -> bool {
    let encoder: &[&str] = match audio_format {
        "mp3" => &["-c:a", "libmp3lame"],
        "m4a" => &["-c:a", "aac"],
        "flac" => &["-c:a", "flac"],
        "wav" => &["-c:a", "pcm_s16le"],
        _ => return false,
    };
    let Some(measured) = measure(path, target_i) else {
        return false;
    };
    let get = |k: &str| measured.get(k).and_then(Value::as_str);
    let keys = [
        "input_i",
        "input_tp",
        "input_lra",
        "input_thresh",
        "target_offset",
    ];
    if keys.iter().any(|k| get(k).is_none()) {
        return false;
    }
    let filt = format!(
        "loudnorm=I={target_i}:TP={TARGET_TP}:LRA={TARGET_LRA}:measured_I={}:measured_TP={}\
         :measured_LRA={}:measured_thresh={}:offset={}:linear=true",
        get("input_i").unwrap(),
        get("input_tp").unwrap(),
        get("input_lra").unwrap(),
        get("input_thresh").unwrap(),
        get("target_offset").unwrap(),
    );

    let mut args: Vec<String> = vec![
        "-y".into(),
        "-i".into(),
        path.to_string(),
        "-af".into(),
        filt,
        "-ar".into(),
        sample_rate(path),
        "-map_metadata".into(),
        "0".into(),
    ];
    // Preserve an embedded cover through the re-encode (only when one exists —
    // mapping a missing video stream, or muxing one into WAV, would fail).
    if audio_format != "wav" && has_cover(path) {
        for a in [
            "-map",
            "0:a",
            "-map",
            "0:v",
            "-c:v",
            "copy",
            "-disposition:v:0",
            "attached_pic",
        ] {
            args.push(a.into());
        }
    }
    for a in encoder {
        args.push((*a).into());
    }
    // Lossy re-encode bitrate (keep it high for "best").
    let best = match audio_format {
        "mp3" => Some("320"),
        "m4a" => Some("256"),
        _ => None,
    };
    if let Some(b) = best {
        let chosen = if bitrate == "best" { b } else { bitrate };
        args.push("-b:a".into());
        args.push(format!("{chosen}k"));
    }

    let p = Path::new(path);
    let stem = p.file_stem().and_then(|s| s.to_str()).unwrap_or("out");
    let ext = p.extension().and_then(|s| s.to_str()).unwrap_or("tmp");
    let tmp = p.with_file_name(format!("{stem}.loudnorm.{ext}"));
    args.push(tmp.to_string_lossy().into_owned());

    let out = run_ffmpeg(&args);
    let wrote = matches!(&out, Some(o) if o.status.success())
        && std::fs::metadata(&tmp)
            .map(|m| m.len() > 0)
            .unwrap_or(false);
    if !wrote {
        let _ = std::fs::remove_file(&tmp);
        return false;
    }
    std::fs::rename(&tmp, path).is_ok()
}

/// Clip a fully-downloaded file to [start, end] in place by stream copy (no
/// re-encode — the bundled LGPL ffmpeg has no x264/x265). Used for HLS sources,
/// where yt-dlp's range download can't trim. Mirrors _ffmpeg_trim. Best-effort.
pub fn ffmpeg_trim(path: &str, start: f64, end: Option<f64>) -> bool {
    let p = Path::new(path);
    let stem = p.file_stem().and_then(|s| s.to_str()).unwrap_or("out");
    let ext = p.extension().and_then(|s| s.to_str()).unwrap_or("mp4");
    let tmp = p.with_file_name(format!("{stem}.trim.{ext}"));
    let mut args = vec![
        "-y".into(),
        "-loglevel".into(),
        "error".into(),
        "-ss".into(),
        format!("{start:.3}"),
    ];
    if let Some(e) = end.filter(|e| *e > start) {
        args.push("-t".into());
        args.push(format!("{:.3}", e - start));
    }
    args.push("-i".into());
    args.push(path.to_string());
    args.push("-map".into());
    args.push("0".into());
    args.push("-c".into());
    args.push("copy".into());
    args.push(tmp.to_string_lossy().into_owned());
    let out = run_ffmpeg(&args);
    let wrote = matches!(&out, Some(o) if o.status.success())
        && std::fs::metadata(&tmp)
            .map(|m| m.len() > 0)
            .unwrap_or(false);
    if !wrote {
        let _ = std::fs::remove_file(&tmp);
        return false;
    }
    std::fs::rename(&tmp, path).is_ok()
}
