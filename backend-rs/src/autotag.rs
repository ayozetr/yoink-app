// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Audio auto-tagging — the write side of services/autotag_service.py. Writes the
//! chosen metadata (title/artist/album/year/genre/track/ISRC) and embeds the cover
//! into a downloaded file with `lofty`, which maps each tag to the right frame per
//! format (ID3 TSRC, MP4 iTunes atom, Vorbis `ISRC`, …). The catalogue lookups
//! (Apple/Deezer/MusicBrainz), lyrics and .nfo/music-folders are later slices.

use lofty::config::WriteOptions;
use lofty::file::TaggedFileExt;
use lofty::picture::{MimeType, Picture, PictureType};
use lofty::prelude::{Accessor, ItemKey, TagExt};
use lofty::tag::Tag;

pub struct ApplyFields {
    pub path: String,
    pub title: Option<String>,
    pub artist: Option<String>,
    pub album: Option<String>,
    pub year: Option<String>,
    pub genre: Option<String>,
    pub track_number: Option<u32>,
    pub isrc: Option<String>,
    /// Already-fetched cover bytes (JPEG/PNG), if any.
    pub cover: Option<Vec<u8>>,
}

fn sniff_mime(bytes: &[u8]) -> MimeType {
    if bytes.starts_with(&[0x89, 0x50, 0x4E, 0x47]) {
        MimeType::Png
    } else {
        MimeType::Jpeg
    }
}

/// Write the tags + cover into the file. Returns whether a cover was embedded.
pub fn write_tags(f: &ApplyFields) -> Result<bool, String> {
    let mut tagged = lofty::read_from_path(&f.path).map_err(|e| e.to_string())?;
    let tag_type = tagged.primary_tag_type();
    if tagged.primary_tag_mut().is_none() {
        tagged.insert_tag(Tag::new(tag_type));
    }
    let tag = tagged
        .primary_tag_mut()
        .ok_or_else(|| "this file type cannot be tagged".to_string())?;

    if let Some(t) = &f.title {
        tag.set_title(t.clone());
    }
    if let Some(a) = &f.artist {
        tag.set_artist(a.clone());
    }
    if let Some(al) = &f.album {
        tag.set_album(al.clone());
    }
    if let Some(y) = f.year.as_ref().and_then(|y| y.parse::<u32>().ok()) {
        tag.set_year(y);
    }
    if let Some(g) = &f.genre {
        tag.set_genre(g.clone());
    }
    if let Some(tn) = f.track_number {
        tag.set_track(tn);
    }
    if let Some(isrc) = &f.isrc {
        tag.insert_text(ItemKey::Isrc, isrc.clone());
    }

    let mut embedded = false;
    if let Some(bytes) = &f.cover {
        let mime = sniff_mime(bytes);
        tag.push_picture(Picture::new_unchecked(
            PictureType::CoverFront,
            Some(mime),
            None,
            bytes.clone(),
        ));
        embedded = true;
    }

    tag.save_to_path(&f.path, WriteOptions::default())
        .map_err(|e| e.to_string())?;
    Ok(embedded)
}

/// Fetch cover bytes (best-effort) for embedding.
pub async fn fetch_cover(url: &str) -> Option<Vec<u8>> {
    let resp = reqwest::Client::builder()
        .user_agent("Yoink")
        .build()
        .ok()?
        .get(url)
        .send()
        .await
        .ok()?;
    resp.bytes().await.ok().map(|b| b.to_vec())
}
