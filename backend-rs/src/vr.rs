// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! VR (180°/360°) detection + spatial-media tagging, ported from vr.py.
//!
//! Two independent signals make a player treat a download as immersive: a
//! projection suffix in the file name (the robust primary mechanism) and
//! Spherical Video V2 (`st3d`/`sv3d`) box metadata injected into the MP4. The
//! box injection is best-effort and atomic — a failure keeps the (valid) file
//! and its name suffix.

use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use regex::Regex;
use serde_json::Value;

pub const DEFAULT_LAYOUT: &str = "180_sbs";

const STEREO_MONO: u8 = 0;
const STEREO_TB: u8 = 1;
const STEREO_LR: u8 = 2;

struct LayoutSpec {
    suffix: &'static str,
    stereo: u8,
    equirect: bool,
    deg: u32,
}

fn layout_spec(layout: &str) -> LayoutSpec {
    match layout {
        "180_tb" => LayoutSpec {
            suffix: "_180x180_3dv",
            stereo: STEREO_TB,
            equirect: true,
            deg: 180,
        },
        "180_mono" => LayoutSpec {
            suffix: "_180x180",
            stereo: STEREO_MONO,
            equirect: true,
            deg: 180,
        },
        "360_sbs" => LayoutSpec {
            suffix: "_360_3dh",
            stereo: STEREO_LR,
            equirect: true,
            deg: 360,
        },
        "360_tb" => LayoutSpec {
            suffix: "_360_3dv",
            stereo: STEREO_TB,
            equirect: true,
            deg: 360,
        },
        "360_mono" => LayoutSpec {
            suffix: "_360",
            stereo: STEREO_MONO,
            equirect: true,
            deg: 360,
        },
        "fisheye190" => LayoutSpec {
            suffix: "_FISHEYE190",
            stereo: STEREO_LR,
            equirect: false,
            deg: 190,
        },
        "fisheye200" => LayoutSpec {
            suffix: "_FISHEYE200",
            stereo: STEREO_LR,
            equirect: false,
            deg: 200,
        },
        "mkx200" => LayoutSpec {
            suffix: "_MKX200",
            stereo: STEREO_LR,
            equirect: false,
            deg: 200,
        },
        "mkx220" => LayoutSpec {
            suffix: "_MKX220",
            stereo: STEREO_LR,
            equirect: false,
            deg: 220,
        },
        "rf52" => LayoutSpec {
            suffix: "_RF52",
            stereo: STEREO_LR,
            equirect: false,
            deg: 190,
        },
        // "180_sbs" (default)
        _ => LayoutSpec {
            suffix: "_180x180_3dh",
            stereo: STEREO_LR,
            equirect: true,
            deg: 180,
        },
    }
}

const KNOWN_LAYOUTS: &[&str] = &[
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

pub fn normalize_layout(layout: &str) -> String {
    if KNOWN_LAYOUTS.contains(&layout) {
        layout.to_string()
    } else {
        DEFAULT_LAYOUT.to_string()
    }
}

pub fn filename_suffix(layout: &str) -> &'static str {
    layout_spec(&normalize_layout(layout)).suffix
}

// ── Detection ──────────────────────────────────────────────────────────────

/// Minimal base64 decode (standard alphabet) — keeps the studio list encoded in
/// source, like vr.py, without a crate dependency.
fn b64_decode(s: &str) -> String {
    fn val(c: u8) -> Option<u32> {
        match c {
            b'A'..=b'Z' => Some((c - b'A') as u32),
            b'a'..=b'z' => Some((c - b'a' + 26) as u32),
            b'0'..=b'9' => Some((c - b'0' + 52) as u32),
            b'+' => Some(62),
            b'/' => Some(63),
            _ => None,
        }
    }
    let mut out = Vec::new();
    let mut acc = 0u32;
    let mut bits = 0;
    for &c in s.as_bytes() {
        let Some(v) = val(c) else { continue };
        acc = (acc << 6) | v;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((acc >> bits) as u8);
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn vr_studios() -> &'static Vec<String> {
    static S: OnceLock<Vec<String>> = OnceLock::new();
    S.get_or_init(|| {
        b64_decode(
            "dmlydHVhbHRhYm9vLGN6ZWNodnIsdnJiYW5nZXJzLHZyYnRyYW5zLHdhbmt6dnIsYmFkb2lu\
             a3ZyLG5hdWdodHlhbWVyaWNhdnIsc2V4YmFiZXN2cixyZWFsamFtdnIsdnJodXNoLHZyY29u\
             ayxzd2FsbG93YmF5LHRtd3ZybmV0LHZpcnR1YWxyZWFscG9ybixzdGFzeXF2ciwxOHZyLHZy\
             Y29zcGxheXgsa2lua3ZyLG1pbGZ2cixoZXJwb3ZyLHdldHZyLHZybGF0aW5hLHNpbnN2cixn\
             cm9vYnl2cixwZXJ2cnQsdnJpbnRpbWFjeSx2cnBvcm4sc2xyb3JpZ2luYWxzLHNleGxpa2Vy\
             ZWFsLHBvdnI=",
        )
        .split(',')
        .map(|s| s.to_string())
        .collect()
    })
}

fn re(cell: &'static OnceLock<Regex>, pat: &str) -> &'static Regex {
    cell.get_or_init(|| Regex::new(pat).unwrap())
}

fn is_vr_text(blob: &str, strict: bool) -> bool {
    static STRONG: OnceLock<Regex> = OnceLock::new();
    static STRONG_STRICT: OnceLock<Regex> = OnceLock::new();
    static DEGREE: OnceLock<Regex> = OnceLock::new();
    static CUE: OnceLock<Regex> = OnceLock::new();
    let strong = if strict {
        re(
            &STRONG_STRICT,
            r"(?i)\b(vr180|mkx\d*|mkz\d*|rf52|fisheye\d*|domeplus)\b|virtual reality",
        )
    } else {
        re(
            &STRONG,
            r"(?i)\b(vr180|vr|mkx\d*|mkz\d*|rf52|fisheye\d*|domeplus)\b|virtual reality",
        )
    };
    if strong.is_match(blob) {
        return true;
    }
    let degree = re(&DEGREE, r"(?i)\b(180|360)\b");
    let cue = re(
        &CUE,
        r"(?i)\b(vr|sbs|tb)\b|side[ -]by[ -]side|top[ -]bottom|over[ -]under|monoscopic",
    );
    degree.is_match(blob) && cue.is_match(blob)
}

fn fisheye_layout(blob: &str) -> &'static str {
    static MKX220: OnceLock<Regex> = OnceLock::new();
    static MKX200: OnceLock<Regex> = OnceLock::new();
    static RF52: OnceLock<Regex> = OnceLock::new();
    static FE200: OnceLock<Regex> = OnceLock::new();
    if re(&MKX220, r"(?i)mkx\s*220").is_match(blob) {
        return "mkx220";
    }
    if re(&MKX200, r"(?i)mkx\s*200").is_match(blob) {
        return "mkx200";
    }
    if re(&RF52, r"(?i)\brf\s?52\b|rf5\.2|canon\s+dual").is_match(blob) {
        return "rf52";
    }
    if re(&FE200, r"(?i)fisheye\s*200|\b200°").is_match(blob) {
        return "fisheye200";
    }
    "fisheye190"
}

fn str_field<'a>(info: &'a Value, key: &str) -> Option<&'a str> {
    info.get(key).and_then(Value::as_str)
}

fn studio_hit(info: &Value) -> bool {
    for key in ["uploader_id", "uploader", "channel", "channel_id"] {
        if let Some(v) = str_field(info, key) {
            let low = v.to_lowercase();
            if vr_studios().iter().any(|s| low.contains(s.as_str())) {
                return true;
            }
        }
    }
    false
}

fn text_blob(info: &Value) -> String {
    let mut parts: Vec<String> = Vec::new();
    for key in ["title", "description", "uploader", "uploader_id"] {
        if let Some(v) = str_field(info, key) {
            parts.push(v.to_string());
        }
    }
    for key in ["tags", "categories"] {
        if let Some(arr) = info.get(key).and_then(Value::as_array) {
            for v in arr {
                if let Some(s) = v.as_str() {
                    parts.push(s.to_string());
                }
            }
        }
    }
    parts.join(" ").to_lowercase()
}

fn best_video_aspect(info: &Value) -> Option<f64> {
    let formats = info.get("formats").and_then(Value::as_array)?;
    let mut best_h = 0f64;
    let mut best_aspect = None;
    for fmt in formats {
        let (Some(w), Some(h)) = (
            fmt.get("width").and_then(Value::as_f64),
            fmt.get("height").and_then(Value::as_f64),
        ) else {
            continue;
        };
        if w > 0.0 && h > 0.0 && h > best_h {
            best_h = h;
            best_aspect = Some(w / h);
        }
    }
    best_aspect
}

fn infer_layout(blob: &str, aspect: Option<f64>) -> String {
    static TBM: OnceLock<Regex> = OnceLock::new();
    static FE: OnceLock<Regex> = OnceLock::new();
    static D360: OnceLock<Regex> = OnceLock::new();
    static D180: OnceLock<Regex> = OnceLock::new();
    static MONO: OnceLock<Regex> = OnceLock::new();
    let mut tb = re(&TBM, r"(?i)\btb\b|top[ -]bottom|over[ -]under|3dv").is_match(blob);
    if re(&FE, r"(?i)fisheye|\bmkx\d*\b|\bmkz\d*\b|\brf52\b|domeplus").is_match(blob) {
        return fisheye_layout(blob).to_string();
    }
    let deg360 = re(&D360, r"(?i)\b360\b").is_match(blob)
        && !re(&D180, r"(?i)\b(180|vr180)\b").is_match(blob);
    if re(&MONO, r"(?i)\bmono\b|monoscopic").is_match(blob) {
        return if deg360 {
            "360_mono".into()
        } else {
            "180_mono".into()
        };
    }
    if let Some(a) = aspect {
        if a >= 3.0 {
            return "360_sbs".into();
        }
        if a <= 1.3 {
            tb = true;
        } else if deg360 && !tb {
            return "360_mono".into();
        }
    }
    if deg360 {
        return if tb {
            "360_tb".into()
        } else {
            "360_sbs".into()
        };
    }
    if tb {
        "180_tb".into()
    } else {
        "180_sbs".into()
    }
}

/// Heuristically decide whether a media item is VR and guess its layout.
pub fn detect_vr(info: &Value, strict: bool) -> (bool, String) {
    if let Some(hint) = str_field(info, "vr_layout_hint").filter(|s| !s.is_empty()) {
        return (true, normalize_layout(hint));
    }
    let blob = text_blob(info);
    let is_vr = studio_hit(info) || is_vr_text(&blob, strict);
    (is_vr, infer_layout(&blob, best_video_aspect(info)))
}

// ── Spherical Video V2 box construction ────────────────────────────────────

const BOUND_QUARTER: u32 = 0x4000_0000;

fn mp4_box(box_type: &[u8; 4], payload: &[u8]) -> Vec<u8> {
    let mut out = ((8 + payload.len()) as u32).to_be_bytes().to_vec();
    out.extend_from_slice(box_type);
    out.extend_from_slice(payload);
    out
}

fn spherical_boxes(layout: &str) -> Vec<u8> {
    let spec = layout_spec(&normalize_layout(layout));
    let st3d = mp4_box(b"st3d", &[0, 0, 0, 0, spec.stereo]);
    if !spec.equirect {
        return st3d;
    }
    let bound: u32 = if spec.deg == 180 { BOUND_QUARTER } else { 0 };
    let mut equi_payload = vec![0u8, 0, 0, 0];
    for v in [0u32, 0, bound, bound] {
        equi_payload.extend_from_slice(&v.to_be_bytes());
    }
    let equi = mp4_box(b"equi", &equi_payload);
    let mut prhd_payload = vec![0u8, 0, 0, 0];
    prhd_payload.extend_from_slice(&[0u8; 12]);
    let prhd = mp4_box(b"prhd", &prhd_payload);
    let mut proj_payload = prhd;
    proj_payload.extend_from_slice(&equi);
    let proj = mp4_box(b"proj", &proj_payload);
    let mut svhd_payload = vec![0u8, 0, 0, 0];
    svhd_payload.extend_from_slice(b"Yoink\x00");
    let svhd = mp4_box(b"svhd", &svhd_payload);
    let mut sv3d_payload = svhd;
    sv3d_payload.extend_from_slice(&proj);
    let sv3d = mp4_box(b"sv3d", &sv3d_payload);
    let mut out = st3d;
    out.extend_from_slice(&sv3d);
    out
}

// ── MP4 box walking + injection ────────────────────────────────────────────

const U32_MAX: u64 = 0xFFFF_FFFF;
type Boxt = (String, usize, usize, usize); // (type, offset, size, header_size)

fn be_u32(b: &[u8]) -> u64 {
    u32::from_be_bytes([b[0], b[1], b[2], b[3]]) as u64
}
fn be_u64(b: &[u8]) -> u64 {
    u64::from_be_bytes([b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]])
}

/// (type, total_size, header_size) for the box at `pos`, or None if malformed.
fn read_header(buf: &[u8], pos: usize, end: usize) -> Option<(String, usize, usize)> {
    if pos + 8 > end {
        return None;
    }
    let mut size = be_u32(&buf[pos..pos + 4]) as usize;
    let box_type = String::from_utf8_lossy(&buf[pos + 4..pos + 8]).into_owned();
    let mut header = 8;
    if size == 1 {
        if pos + 16 > end {
            return None;
        }
        size = be_u64(&buf[pos + 8..pos + 16]) as usize;
        header = 16;
    } else if size == 0 {
        size = end - pos;
    }
    if size < header || pos + size > end {
        return None;
    }
    Some((box_type, size, header))
}

fn iter_children(buf: &[u8], start: usize, end: usize, skip: usize) -> Option<Vec<Boxt>> {
    let mut out = Vec::new();
    let mut pos = start + skip;
    while pos + 8 <= end {
        let (t, size, header) = read_header(buf, pos, end)?;
        out.push((t, pos, size, header));
        pos += size;
    }
    Some(out)
}

fn find(buf: &[u8], start: usize, end: usize, want: &str, skip: usize) -> Option<Boxt> {
    iter_children(buf, start, end, skip)?
        .into_iter()
        .find(|c| c.0 == want)
}

/// (insert_offset, ancestors[se,stsd,stbl,minf,mdia,trak,moov], chunk_offset_boxes).
#[allow(clippy::type_complexity)]
fn locate_video_sample_entry(
    buf: &[u8],
) -> Option<(
    usize,
    Vec<(usize, usize, usize)>,
    Vec<(usize, usize, usize)>,
)> {
    let (_, moov_off, moov_size, moov_hdr) = find(buf, 0, buf.len(), "moov", 0)?;
    let moov_end = moov_off + moov_size;
    // Fragmented MP4 (mvex): bail — growing moov would shift fragments.
    if find(buf, moov_off, moov_end, "mvex", moov_hdr).is_some() {
        return None;
    }
    let mut insert: Option<usize> = None;
    let mut ancestors: Vec<(usize, usize, usize)> = Vec::new();
    let mut chunk_boxes: Vec<(usize, usize, usize)> = Vec::new();

    for (typ, trak_off, trak_size, trak_hdr) in iter_children(buf, moov_off, moov_end, moov_hdr)? {
        if typ != "trak" {
            continue;
        }
        let trak_end = trak_off + trak_size;
        let Some((_, mdia_off, mdia_size, mdia_hdr)) =
            find(buf, trak_off, trak_end, "mdia", trak_hdr)
        else {
            continue;
        };
        let mdia_end = mdia_off + mdia_size;
        let Some((_, minf_off, minf_size, minf_hdr)) =
            find(buf, mdia_off, mdia_end, "minf", mdia_hdr)
        else {
            continue;
        };
        let minf_end = minf_off + minf_size;
        let Some((_, stbl_off, stbl_size, stbl_hdr)) =
            find(buf, minf_off, minf_end, "stbl", minf_hdr)
        else {
            continue;
        };
        let stbl_end = stbl_off + stbl_size;

        for name in ["stco", "co64"] {
            if let Some(b) = find(buf, stbl_off, stbl_end, name, stbl_hdr) {
                chunk_boxes.push((b.1, b.2, b.3));
            }
        }

        let Some((_, h_off, _, h_hdr)) = find(buf, mdia_off, mdia_end, "hdlr", mdia_hdr) else {
            continue;
        };
        let handler = &buf[h_off + h_hdr + 8..h_off + h_hdr + 12];
        if handler != b"vide" || insert.is_some() {
            continue;
        }
        let (_, stsd_off, stsd_size, stsd_hdr) = find(buf, stbl_off, stbl_end, "stsd", stbl_hdr)?;
        let entry_count = be_u32(&buf[stsd_off + stsd_hdr + 4..stsd_off + stsd_hdr + 8]);
        if entry_count != 1 {
            return None; // multiple sample entries — unsafe
        }
        let se_off = stsd_off + stsd_hdr + 8;
        let (_, se_size, se_hdr) = read_header(buf, se_off, stsd_off + stsd_size)?;
        insert = Some(se_off + se_size);
        ancestors = vec![
            (se_off, se_size, se_hdr),
            (stsd_off, stsd_size, stsd_hdr),
            (stbl_off, stbl_size, stbl_hdr),
            (minf_off, minf_size, minf_hdr),
            (mdia_off, mdia_size, mdia_hdr),
            (trak_off, trak_size, trak_hdr),
            (moov_off, moov_size, moov_hdr),
        ];
    }
    Some((insert?, ancestors, chunk_boxes))
}

fn already_spherical(buf: &[u8], ancestors: &[(usize, usize, usize)]) -> bool {
    let (se_off, se_size, _) = ancestors[0];
    let slice = &buf[se_off..se_off + se_size];
    find_bytes(slice, b"sv3d") || find_bytes(slice, b"st3d")
}

fn find_bytes(hay: &[u8], needle: &[u8]) -> bool {
    hay.windows(needle.len()).any(|w| w == needle)
}

fn patch_size(buf: &mut [u8], off: usize, size: usize, hsize: usize, delta: usize) -> Option<()> {
    let new = (size + delta) as u64;
    if hsize == 16 {
        buf[off + 8..off + 16].copy_from_slice(&new.to_be_bytes());
    } else if new > U32_MAX {
        return None;
    } else {
        buf[off..off + 4].copy_from_slice(&(new as u32).to_be_bytes());
    }
    Some(())
}

fn patch_chunk_offsets(
    buf: &mut [u8],
    boxt: (usize, usize, usize),
    threshold: u64,
    delta: u64,
) -> Option<()> {
    let (off, size, hsize) = boxt;
    let is_co64 = &buf[off + 4..off + 8] == b"co64";
    let entry_size = if is_co64 { 8 } else { 4 };
    let count = be_u32(&buf[off + hsize + 4..off + hsize + 8]);
    let mut pos = off + hsize + 8;
    let end = off + size;
    for _ in 0..count {
        if pos + entry_size > end {
            break;
        }
        let mut value = if is_co64 {
            be_u64(&buf[pos..pos + 8])
        } else {
            be_u32(&buf[pos..pos + 4])
        };
        if value >= threshold {
            value += delta;
            if entry_size == 4 && value > U32_MAX {
                return None;
            }
            if is_co64 {
                buf[pos..pos + 8].copy_from_slice(&value.to_be_bytes());
            } else {
                buf[pos..pos + 4].copy_from_slice(&(value as u32).to_be_bytes());
            }
        }
        pos += entry_size;
    }
    Some(())
}

const MAX_MOOV: u64 = 256 * 1024 * 1024;
const COPY_CHUNK: usize = 1024 * 1024;

fn read_moov(f: &mut std::fs::File, filesize: u64) -> Option<(u64, Vec<u8>)> {
    let mut pos: u64 = 0;
    while pos + 8 <= filesize {
        f.seek(SeekFrom::Start(pos)).ok()?;
        let mut head = [0u8; 16];
        let n = read_up_to(f, &mut head)?;
        if n < 8 {
            break;
        }
        let mut size = be_u32(&head[..4]);
        let box_type = &head[4..8];
        let mut header = 8u64;
        if size == 1 {
            if n < 16 {
                return None;
            }
            size = be_u64(&head[8..16]);
            header = 16;
        } else if size == 0 {
            size = filesize - pos;
        }
        if size < header || pos + size > filesize {
            return None;
        }
        if box_type == b"moov" {
            if size > MAX_MOOV {
                return None;
            }
            f.seek(SeekFrom::Start(pos)).ok()?;
            let mut moov = vec![0u8; size as usize];
            f.read_exact(&mut moov).ok()?;
            return Some((pos, moov));
        }
        pos += size;
    }
    None
}

fn read_up_to(f: &mut std::fs::File, buf: &mut [u8]) -> Option<usize> {
    let mut filled = 0;
    while filled < buf.len() {
        match f.read(&mut buf[filled..]) {
            Ok(0) => break,
            Ok(n) => filled += n,
            Err(_) => return None,
        }
    }
    Some(filled)
}

fn copy_range(
    src: &mut std::fs::File,
    dst: &mut std::fs::File,
    start: u64,
    end: u64,
) -> Option<()> {
    src.seek(SeekFrom::Start(start)).ok()?;
    let mut remaining = end - start;
    let mut buf = vec![0u8; COPY_CHUNK];
    while remaining > 0 {
        let want = std::cmp::min(COPY_CHUNK as u64, remaining) as usize;
        let n = src.read(&mut buf[..want]).ok()?;
        if n == 0 {
            return None;
        }
        dst.write_all(&buf[..n]).ok()?;
        remaining -= n as u64;
    }
    Some(())
}

/// Build the new moov, write `path` atomically via a temp + rename. Returns true
/// if written. `build` produces (new_moov_bytes, delta) from the parsed moov, or
/// None to bail. `tmp_suffix` names the temp file.
fn rewrite_moov<F>(path: &Path, tmp_suffix: &str, build: F) -> bool
where
    F: FnOnce(&[u8], u64) -> Option<(Vec<u8>, usize)>,
{
    let Ok(meta) = std::fs::metadata(path) else {
        return false;
    };
    let filesize = meta.len();
    let Ok(mut f) = std::fs::File::open(path) else {
        return false;
    };
    let Some((moov_off, moov)) = read_moov(&mut f, filesize) else {
        return false;
    };
    let Some((new_moov, delta)) = build(&moov, moov_off) else {
        return false;
    };

    let tmp = path.with_file_name(format!(
        "{}{tmp_suffix}",
        path.file_name().and_then(|n| n.to_str()).unwrap_or("out")
    ));
    let expected = filesize + delta as u64;
    let write_ok = (|| -> Option<()> {
        let mut out = std::fs::File::create(&tmp).ok()?;
        copy_range(&mut f, &mut out, 0, moov_off)?;
        out.write_all(&new_moov).ok()?;
        copy_range(&mut f, &mut out, moov_off + moov.len() as u64, filesize)?;
        out.flush().ok()?;
        out.sync_all().ok()?;
        if std::fs::metadata(&tmp).ok()?.len() != expected {
            return None;
        }
        Some(())
    })();
    drop(f);
    if write_ok.is_none() {
        let _ = std::fs::remove_file(&tmp);
        return false;
    }
    if std::fs::rename(&tmp, path).is_err() {
        let _ = std::fs::remove_file(&tmp);
        return false;
    }
    true
}

/// Inject Spherical Video V2 (st3d/sv3d) into an MP4, atomically.
pub fn inject_spherical_metadata(path: &Path, layout: &str) -> bool {
    rewrite_moov(path, ".vrtmp", |moov, moov_off| {
        let (insert, ancestors, chunk_boxes) = locate_video_sample_entry(moov)?;
        if already_spherical(moov, &ancestors) {
            return None;
        }
        let new_boxes = spherical_boxes(layout);
        let delta = new_boxes.len();
        let mut buf = moov.to_vec();
        for &(off, size, hsize) in &ancestors {
            patch_size(&mut buf, off, size, hsize, delta)?;
        }
        // Chunk-offset values are absolute file offsets, so the insertion
        // threshold must be absolute too (moov's file offset + the in-moov insert).
        let threshold = moov_off + insert as u64;
        for &b in &chunk_boxes {
            patch_chunk_offsets(&mut buf, b, threshold, delta as u64)?;
        }
        let mut new_moov = buf[..insert].to_vec();
        new_moov.extend_from_slice(&new_boxes);
        new_moov.extend_from_slice(&buf[insert..]);
        Some((new_moov, delta))
    })
}

/// Inject the legacy Spherical Video V1 `uuid` box (360°-equirect only).
pub fn inject_spherical_v1(path: &Path, layout: &str) -> bool {
    let Some(payload) = spherical_v1_xml(layout) else {
        return false;
    };
    rewrite_moov(path, ".v1tmp", |moov, moov_off| {
        if find_bytes(moov, &SPHERICAL_V1_UUID) {
            return None; // already carries V1
        }
        let (_, ancestors, chunk_boxes) = locate_video_sample_entry(moov)?;
        let (trak_off, trak_size, trak_hdr) = ancestors[5];
        let (moov_o, moov_size, moov_hdr) = ancestors[6];
        let insert = trak_off + trak_size; // right after the trak's children
        let mut box_payload = SPHERICAL_V1_UUID.to_vec();
        box_payload.extend_from_slice(&payload);
        let boxb = mp4_box(b"uuid", &box_payload);
        let delta = boxb.len();
        let mut buf = moov.to_vec();
        patch_size(&mut buf, trak_off, trak_size, trak_hdr, delta)?;
        patch_size(&mut buf, moov_o, moov_size, moov_hdr, delta)?;
        let threshold = moov_off + insert as u64;
        for &b in &chunk_boxes {
            patch_chunk_offsets(&mut buf, b, threshold, delta as u64)?;
        }
        let mut new_moov = buf[..insert].to_vec();
        new_moov.extend_from_slice(&boxb);
        new_moov.extend_from_slice(&buf[insert..]);
        Some((new_moov, delta))
    })
}

// ── Spherical Video V1 (legacy uuid/XML) + MKV + apply ──────────────────────

const SPHERICAL_V1_UUID: [u8; 16] = [
    0xff, 0xcc, 0x82, 0x63, 0xf8, 0x55, 0x4a, 0x93, 0x88, 0x14, 0x58, 0x7a, 0x02, 0x52, 0x1f, 0xdd,
];

fn spherical_v1_xml(layout: &str) -> Option<Vec<u8>> {
    let spec = layout_spec(&normalize_layout(layout));
    if !spec.equirect || spec.deg != 360 {
        return None;
    }
    let mode = match spec.stereo {
        STEREO_MONO => "mono",
        STEREO_LR => "left-right",
        STEREO_TB => "top-bottom",
        _ => "mono",
    };
    let xml = format!(
        "<?xml version=\"1.0\"?>\
         <rdf:SphericalVideo \
         xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\" \
         xmlns:GSpherical=\"http://ns.google.com/videos/1.0/spherical/\">\
         <GSpherical:Spherical>true</GSpherical:Spherical>\
         <GSpherical:Stitched>true</GSpherical:Stitched>\
         <GSpherical:ProjectionType>equirectangular</GSpherical:ProjectionType>\
         <GSpherical:StereoMode>{mode}</GSpherical:StereoMode>\
         <GSpherical:StitchingSoftware>Yoink</GSpherical:StitchingSoftware>\
         </rdf:SphericalVideo>"
    );
    Some(xml.into_bytes())
}

/// Set the Matroska StereoMode on an MKV's video track (stream-copy remux).
pub fn set_mkv_stereo_mode(path: &Path, layout: &str) -> bool {
    let spec = layout_spec(&normalize_layout(layout));
    let mode = match spec.stereo {
        STEREO_LR => "left_right",
        STEREO_TB => "top_bottom",
        _ => return false, // mono — nothing to signal
    };
    let tmp = path.with_file_name(format!(
        "{}.vrtmp.mkv",
        path.file_name().and_then(|n| n.to_str()).unwrap_or("out")
    ));
    let ffmpeg = match std::env::var("YOINK_FFMPEG") {
        Ok(dir) if !dir.is_empty() => Path::new(&dir)
            .join("ffmpeg")
            .to_string_lossy()
            .into_owned(),
        _ => "ffmpeg".to_string(),
    };
    let out = std::process::Command::new(ffmpeg)
        .args([
            "-y",
            "-loglevel",
            "error",
            "-i",
            &path.to_string_lossy(),
            "-map",
            "0",
            "-c",
            "copy",
            "-metadata:s:v:0",
            &format!("stereo_mode={mode}"),
            &tmp.to_string_lossy(),
        ])
        .output();
    let ok = matches!(&out, Ok(o) if o.status.success())
        && std::fs::metadata(&tmp)
            .map(|m| m.len() > 0)
            .unwrap_or(false);
    if !ok {
        let _ = std::fs::remove_file(&tmp);
        return false;
    }
    if std::fs::rename(&tmp, path).is_err() {
        let _ = std::fs::remove_file(&tmp);
        return false;
    }
    true
}

/// Tag a finished video as VR: projection name suffix + spherical boxes.
/// Returns the (possibly renamed) path.
pub fn apply_vr(path: &Path, layout: &str) -> PathBuf {
    let layout = normalize_layout(layout);
    let suffix = filename_suffix(&layout);
    let mut final_path = path.to_path_buf();

    let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("");
    let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
    if !suffix.is_empty() && !stem.contains(suffix) {
        let mk = |name: String| path.with_file_name(name);
        let mut target = mk(format!("{stem}{suffix}.{ext}"));
        let mut n = 2;
        while target.exists() && n <= 999 {
            target = mk(format!("{stem}{suffix}_{n}.{ext}"));
            n += 1;
        }
        if !target.exists() && std::fs::rename(path, &target).is_ok() {
            final_path = target;
        }
    }

    let ext_lower = final_path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();
    match ext_lower.as_str() {
        "mp4" | "m4v" | "mov" => {
            inject_spherical_metadata(&final_path, &layout);
            inject_spherical_v1(&final_path, &layout); // 360°-only; no-op otherwise
        }
        "mkv" => {
            set_mkv_stereo_mode(&final_path, &layout);
        }
        _ => {}
    }
    final_path
}

#[cfg(test)]
mod vr_tests {
    use super::{filename_suffix, fisheye_layout, is_vr_text, normalize_layout, DEFAULT_LAYOUT};

    #[test]
    fn normalize_layout_keeps_known_else_default() {
        assert_eq!(normalize_layout("360_tb"), "360_tb");
        assert_eq!(normalize_layout("mkx200"), "mkx200");
        assert_eq!(normalize_layout("not-a-layout"), DEFAULT_LAYOUT);
        assert_eq!(normalize_layout(""), DEFAULT_LAYOUT);
    }

    #[test]
    fn filename_suffix_per_layout() {
        assert_eq!(filename_suffix("180_sbs"), "_180x180_3dh");
        assert_eq!(filename_suffix("360_tb"), "_360_3dv");
        assert_eq!(filename_suffix("mkx200"), "_MKX200");
        assert_eq!(filename_suffix("360_mono"), "_360");
        // Unknown falls back to the default (180_sbs) suffix.
        assert_eq!(filename_suffix("garbage"), "_180x180_3dh");
    }

    #[test]
    fn is_vr_text_strong_and_cue_based() {
        // Strong keywords match in both modes.
        assert!(is_vr_text("Amazing VR180 experience", false));
        assert!(is_vr_text("Amazing VR180 experience", true));
        assert!(is_vr_text("shot on MKX200 fisheye", true));
        // Degree + cue combo (no strong keyword).
        assert!(is_vr_text("180 side-by-side clip", false));
        // A bare "VR" counts only in the lenient mode.
        assert!(is_vr_text("cool VR stuff", false));
        assert!(!is_vr_text("cool VR stuff", true));
        // Plain content is not VR.
        assert!(!is_vr_text("just a normal music video", false));
    }

    #[test]
    fn fisheye_layout_detection() {
        assert_eq!(fisheye_layout("recorded with MKX220"), "mkx220");
        assert_eq!(fisheye_layout("MKX200 lens"), "mkx200");
        assert_eq!(fisheye_layout("Canon RF52 dual"), "rf52");
        assert_eq!(fisheye_layout("fisheye 200 degrees"), "fisheye200");
        assert_eq!(fisheye_layout("some fisheye footage"), "fisheye190");
    }
}
