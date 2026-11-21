// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Media-server music-library layout: rename a tagged track to "Artist - Title"
//! and/or relocate it into `<download dir>/<Artist>/<Album>/` with folder-level
//! `album.nfo`/`artist.nfo`. Ported from autotag_service.py (rename_to_tagged,
//! organize_music_library, _write_folder_nfo). All best-effort: a failure leaves
//! the file where it was and returns the original path.

use std::path::{Path, PathBuf};

use crate::nfo;

const SIDECAR_SUFFIXES: &[&str] = &["nfo", "lrc", "jpg", "jpeg", "png", "webp"];

/// Sanitise one path component the way yt-dlp does (restricted=False): map the
/// Windows-reserved characters to full-width look-alikes (so a fresh download and
/// a relocation produce the same name), drop control chars, trim trailing dots
/// and spaces. A lone ".." is left intact so the caller's confinement check sees it.
pub fn sanitize_filename(name: &str) -> String {
    let mut out = String::new();
    for c in name.chars() {
        match c {
            '<' => out.push('＜'),
            '>' => out.push('＞'),
            ':' => out.push('：'),
            '"' => out.push('＂'),
            '/' => out.push('⧸'),
            '\\' => out.push('⧹'),
            '|' => out.push('｜'),
            '?' => out.push('？'),
            '*' => out.push('＊'),
            c if (c as u32) < 0x20 => {}
            c => out.push(c),
        }
    }
    out.trim_end_matches(['.', ' ']).trim().to_string()
}

fn is_sidecar(p: &Path) -> bool {
    p.extension()
        .and_then(|e| e.to_str())
        .map(|e| SIDECAR_SUFFIXES.contains(&e.to_lowercase().as_str()))
        .unwrap_or(false)
}

/// The audio file plus its known sidecars (`<stem>.…` with a recognised suffix).
fn movable_siblings(path: &Path, stem: &str) -> Vec<PathBuf> {
    let prefix = format!("{stem}.");
    let mut out = Vec::new();
    let Some(parent) = path.parent() else {
        return out;
    };
    let Ok(entries) = std::fs::read_dir(parent) else {
        return out;
    };
    for entry in entries.flatten() {
        let sib = entry.path();
        if !sib.is_file() {
            continue;
        }
        let Some(name) = sib.file_name().and_then(|n| n.to_str()) else {
            continue;
        };
        if !name.starts_with(&prefix) {
            continue;
        }
        if sib == path || is_sidecar(&sib) {
            out.push(sib);
        }
    }
    // The audio file (== path) sorts LAST, so a partial failure can't leave the
    // audio moved while the caller returns the old path.
    out.sort_by_key(|s| s == path);
    out
}

/// The suffix part of a sidecar name after the shared stem (e.g. ".nfo", ".es.lrc").
fn tail<'a>(sib: &'a Path, stem: &str) -> &'a str {
    sib.file_name()
        .and_then(|n| n.to_str())
        .map(|n| &n[stem.len()..])
        .unwrap_or("")
}

/// Rename the audio file (+ sidecars) to the auto-tag name, keeping extensions.
pub fn rename_to_tagged(path: &Path, new_title: &str) -> PathBuf {
    let new_stem = sanitize_filename(new_title);
    let cur_stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("");
    if new_stem.is_empty() || new_stem == cur_stem {
        return path.to_path_buf();
    }
    let suffix = path.extension().and_then(|e| e.to_str()).unwrap_or("");
    let target = path.with_file_name(format!("{new_stem}.{suffix}"));
    if target.exists() {
        return path.to_path_buf(); // don't clobber a different file
    }
    let Some(parent) = path.parent() else {
        return path.to_path_buf();
    };
    for sib in movable_siblings(path, cur_stem) {
        let dest = parent.join(format!("{new_stem}{}", tail(&sib, cur_stem)));
        if dest.exists() {
            continue;
        }
        if std::fs::rename(&sib, &dest).is_err() {
            return path.to_path_buf();
        }
    }
    target
}

/// Move a tagged track (+ sidecars) into `<download dir>/<Artist>/<Album>/<stem>.ext`
/// and, when `nfo_sidecars`, write folder-level album/artist .nfo. Returns the new
/// path, or the original when it can't move.
#[allow(clippy::too_many_arguments)]
pub fn organize_music_library(
    path: &Path,
    artist: &str,
    album: &str,
    year: &str,
    stem: &str,
    cover_url: Option<&str>,
    download_root: &Path,
    nfo_sidecars: bool,
) -> PathBuf {
    let safe_artist = sanitize_filename(artist);
    let safe_stem = sanitize_filename(stem);
    if safe_artist.is_empty() || safe_stem.is_empty() {
        return path.to_path_buf();
    }
    let safe_album = if album.is_empty() {
        String::new()
    } else {
        sanitize_filename(album)
    };
    // Confinement: a crafted "artist"/"album" must not escape the download dir.
    if safe_artist == ".." || safe_album == ".." {
        return path.to_path_buf();
    }
    let mut folder = download_root.join(&safe_artist);
    if !safe_album.is_empty() {
        folder = folder.join(&safe_album);
    }
    let suffix = path.extension().and_then(|e| e.to_str()).unwrap_or("");
    let target = folder.join(format!("{safe_stem}.{suffix}"));
    if target == path {
        return path.to_path_buf();
    }
    if target.exists() {
        return path.to_path_buf();
    }
    let cur_stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("");
    if std::fs::create_dir_all(&folder).is_err() {
        return path.to_path_buf();
    }
    for sib in movable_siblings(path, cur_stem) {
        let dest = folder.join(format!("{safe_stem}{}", tail(&sib, cur_stem)));
        if dest.exists() && dest != sib {
            continue;
        }
        if std::fs::rename(&sib, &dest).is_err() {
            return path.to_path_buf();
        }
    }
    if nfo_sidecars {
        write_folder_nfo(
            &folder,
            &safe_album,
            album,
            artist,
            year,
            cover_url.unwrap_or(""),
        );
    }
    target
}

/// `album.nfo` (album folder) + `artist.nfo` (artist folder). Best-effort.
fn write_folder_nfo(
    album_folder: &Path,
    safe_album: &str,
    album: &str,
    artist: &str,
    year: &str,
    thumb: &str,
) {
    // With no album the track sits directly in the artist folder.
    let artist_folder = if album.is_empty() {
        album_folder
    } else {
        album_folder.parent().unwrap_or(album_folder)
    };
    if !safe_album.is_empty() {
        let _ = std::fs::write(
            album_folder.join("album.nfo"),
            nfo::build_album(album, artist, year, thumb),
        );
    }
    let _ = std::fs::write(
        artist_folder.join("artist.nfo"),
        nfo::build_artist(artist, thumb),
    );
}
