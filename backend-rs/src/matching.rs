// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Faithful port of `backend/app/services/matching.py` — the keyless, spotDL-style
//! scorer that ranks yt-dlp `ytsearch` candidates against a music track on fuzzy
//! name/artist similarity plus a duration penalty. `difflib::SequenceMatcher`
//! mirrors Python's `difflib.SequenceMatcher.ratio()` so the scores match.

use std::collections::{BTreeSet, HashSet};
use std::sync::OnceLock;

use difflib::sequencematcher::SequenceMatcher;
use regex::Regex;
use serde_json::Value;
use unicode_normalization::UnicodeNormalization;

const FORBIDDEN_WORDS: &[&str] = &[
    "remix",
    "remastered",
    "live",
    "acoustic",
    "8d",
    "concert",
    "acapella",
    "slowed",
    "instrumental",
    "cover",
    "karaoke",
    "bassboost",
    "bass boost",
    "reverb",
    "sped up",
    "nightcore",
    "mashup",
    "tribute",
];

const MIN_NAME: f64 = 60.0;
const MIN_ARTIST: f64 = 60.0;
const MIN_TIME: f64 = 25.0;

fn feat_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)\s*[\(\[]?\s*\b(?:feat\.?|ft\.?|featuring)\s.+$").unwrap())
}

fn artist_split_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)\s*(?:,|&|/|\bx\b)\s*").unwrap())
}

fn is_combining(c: char) -> bool {
    matches!(
        c as u32,
        0x0300..=0x036F | 0x1AB0..=0x1AFF | 0x1DC0..=0x1DFF | 0x20D0..=0x20FF | 0xFE20..=0xFE2F
    )
}

/// Lowercase, de-accented, alphanumeric-only token string (mirrors `_slug`).
fn slug(text: &str) -> String {
    let translated: String = text
        .chars()
        .map(|c| match c {
            '€' => 'e',
            '$' => 's',
            '@' => 'a',
            '£' => 'l',
            '¥' => 'y',
            'ø' => 'o',
            'ł' => 'l',
            'đ' => 'd',
            other => other,
        })
        .collect();
    let deaccented: String = translated.nfkd().filter(|c| !is_combining(*c)).collect();
    let lower = deaccented.to_lowercase();
    let mut out = String::new();
    let mut prev_space = true;
    for c in lower.chars() {
        if c.is_ascii_lowercase() || c.is_ascii_digit() {
            out.push(c);
            prev_space = false;
        } else if !prev_space {
            out.push(' ');
            prev_space = true;
        }
    }
    out.trim().to_string()
}

fn seq_ratio(a: &str, b: &str) -> f64 {
    SequenceMatcher::new(a, b).ratio() as f64
}

/// fuzzywuzzy-style token-set ratio (0–1), robust to extra words on one side.
fn token_set_ratio(a: &str, b: &str) -> f64 {
    let t1: BTreeSet<&str> = a.split_whitespace().collect();
    let t2: BTreeSet<&str> = b.split_whitespace().collect();
    if t1.is_empty() || t2.is_empty() {
        return 0.0;
    }
    let join = |it: std::collections::btree_set::Intersection<&str>| -> String {
        it.copied().collect::<Vec<_>>().join(" ")
    };
    let inter = join(t1.intersection(&t2));
    let diff1 = t1.difference(&t2).copied().collect::<Vec<_>>().join(" ");
    let diff2 = t2.difference(&t1).copied().collect::<Vec<_>>().join(" ");
    let combined1 = format!("{inter} {diff1}").trim().to_string();
    let combined2 = format!("{inter} {diff2}").trim().to_string();
    seq_ratio(&inter, &combined1)
        .max(seq_ratio(&inter, &combined2))
        .max(seq_ratio(&combined1, &combined2))
}

/// Fuzzy similarity 0–100: max of direct, token-sorted, and token-set ratios.
fn ratio(a: &str, b: &str) -> f64 {
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    let direct = seq_ratio(a, b);
    let sort = |s: &str| {
        let mut v: Vec<&str> = s.split_whitespace().collect();
        v.sort_unstable();
        v.join(" ")
    };
    let token = seq_ratio(&sort(a), &sort(b));
    direct.max(token).max(token_set_ratio(a, b)) * 100.0
}

fn forbidden_penalty(cand_title_slug: &str, track_title_slug: &str) -> f64 {
    let mut penalty = 0.0;
    for word in FORBIDDEN_WORDS {
        let w = slug(word);
        if !w.is_empty() && cand_title_slug.contains(&w) && !track_title_slug.contains(&w) {
            penalty += 15.0;
        }
    }
    penalty
}

fn name_match(track_title: &str, cand_title: &str) -> f64 {
    let t = slug(&feat_re().replace(track_title, ""));
    let c = slug(cand_title);
    let mut best = ratio(&t, &c);
    if let Some(idx) = cand_title.find(" - ") {
        best = best.max(ratio(&t, &slug(&cand_title[idx + 3..])));
    }
    let penalty = forbidden_penalty(&c, &t);
    (best - penalty).max(0.0)
}

fn coverage(artist_slug: &str, cand_tokens: &HashSet<&str>) -> f64 {
    let tokens: Vec<&str> = artist_slug.split_whitespace().collect();
    if tokens.is_empty() {
        return 0.0;
    }
    let hits = tokens.iter().filter(|t| cand_tokens.contains(**t)).count();
    100.0 * hits as f64 / tokens.len() as f64
}

fn artist_match(track_artists: &str, cand_title: &str, cand_channel: &str) -> f64 {
    let cleaned = feat_re().replace(track_artists, "").to_string();
    let artist_slug = slug(&cleaned);
    if artist_slug.is_empty() {
        return 0.0;
    }
    let cand_blob = slug(&format!("{cand_channel} {cand_title}"));
    let cand_tokens: HashSet<&str> = cand_blob.split_whitespace().collect();
    let primary = artist_split_re().splitn(&cleaned, 2).next().unwrap_or("");
    let primary_slug = slug(primary);
    let channel_blob = slug(cand_channel).replace(' ', "");
    for variant in [&artist_slug, &primary_slug] {
        let despaced = variant.replace(' ', "");
        if despaced.chars().count() >= 5 && channel_blob.contains(&despaced) {
            return 100.0;
        }
    }
    coverage(&artist_slug, &cand_tokens)
        .max(coverage(&primary_slug, &cand_tokens))
        .max(ratio(&artist_slug, &slug(cand_channel)))
}

fn time_match(track_secs: Option<f64>, cand_secs: Option<f64>) -> f64 {
    match (track_secs, cand_secs) {
        (Some(t), Some(c)) if t > 0.0 && c > 0.0 => (-0.1 * (t - c).abs()).exp() * 100.0,
        _ => 100.0,
    }
}

/// Combined 0–100 score for one candidate, or None if rejected. `cand` is a
/// yt-dlp flat search entry (`title`, `channel`/`uploader`, `duration`, `url`).
pub fn score(
    track_title: &str,
    track_artists: &str,
    track_duration_ms: Option<i64>,
    cand: &Value,
) -> Option<f64> {
    let cand_title = cand.get("title").and_then(Value::as_str).unwrap_or("");
    let cand_channel = cand
        .get("channel")
        .and_then(Value::as_str)
        .or_else(|| cand.get("uploader").and_then(Value::as_str))
        .unwrap_or("");
    let nm = name_match(track_title, cand_title);
    let am = artist_match(track_artists, cand_title, cand_channel);
    let track_secs = track_duration_ms
        .filter(|&m| m > 0)
        .map(|m| m as f64 / 1000.0);
    let tm = time_match(track_secs, cand.get("duration").and_then(Value::as_f64));

    let min_time = if nm >= 90.0 && am >= 90.0 {
        0.5
    } else if nm >= 85.0 && am >= 85.0 {
        10.0
    } else {
        MIN_TIME
    };
    if nm < MIN_NAME || am < MIN_ARTIST || tm < min_time {
        return None;
    }
    let mut avg = (nm + am) / 2.0;
    if track_secs.is_some() {
        avg = (avg + tm) / 2.0;
    }
    Some(avg.min(100.0))
}

/// The highest-scoring candidate that clears the thresholds, plus its rounded
/// score, or None. Stable sort → ties keep search order (first wins), like Python.
pub fn best_match<'a>(
    track_title: &str,
    track_artists: &str,
    track_duration_ms: Option<i64>,
    candidates: &'a [Value],
) -> Option<(&'a Value, f64)> {
    let mut scored: Vec<(f64, &Value)> = candidates
        .iter()
        .filter_map(|c| score(track_title, track_artists, track_duration_ms, c).map(|s| (s, c)))
        .collect();
    scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    scored.first().map(|(s, c)| (*c, (s * 10.0).round() / 10.0))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn cand(title: &str, channel: &str, dur: f64) -> Value {
        json!({ "title": title, "channel": channel, "duration": dur, "url": "x" })
    }

    // Reference values computed from the Python matcher (matching.py) on the
    // same inputs — the port must reproduce them exactly.
    #[test]
    fn matches_python_reference() {
        let (title, artists, dur) = ("Despechá", "ROSALÍA", Some(160_000i64));
        let a = cand("ROSALÍA - DESPECHÁ (Official Video)", "ROSALÍA", 160.0);
        let b = cand("Despechá (Remix)", "DJ Random", 200.0);
        let c = cand("Bad Bunny - Tití Me Preguntó", "Bad Bunny", 160.0);
        let d = cand("Rosalia Despecha Lyrics", "LyricChannel", 162.0);

        assert!((score(title, artists, dur, &a).unwrap() - 100.0).abs() < 0.05);
        assert!(score(title, artists, dur, &b).is_none()); // remix: artist 25 < 60
        assert!(score(title, artists, dur, &c).is_none()); // different song
        assert!((score(title, artists, dur, &d).unwrap() - 90.937).abs() < 0.05);

        assert!((name_match(title, "Despechá (Remix)") - 85.0).abs() < 0.5);
        assert!((artist_match(artists, "Despechá (Remix)", "DJ Random") - 25.0).abs() < 0.5);

        let all = [a, b, c, d];
        let (best, s) = best_match(title, artists, dur, &all).unwrap();
        assert_eq!(
            best.get("title").unwrap(),
            "ROSALÍA - DESPECHÁ (Official Video)"
        );
        assert!((s - 100.0).abs() < 0.05);
    }
}
