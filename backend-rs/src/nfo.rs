// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Kodi/Jellyfin-style `.nfo` metadata sidecars (movie / musicvideo), ported
//! from nfo.py. Written at download time from yt-dlp's info, and re-written at
//! audio auto-tagging time from the tagged metadata.

use std::path::Path;

use serde_json::Value;

/// Escape XML text content (`&`, `<`, `>` — matching Python's saxutils.escape).
fn esc(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn tag(name: &str, value: &str) -> String {
    if value.is_empty() {
        String::new()
    } else {
        format!("  <{name}>{}</{name}>\n", esc(value))
    }
}

/// Fields for a `.nfo` body (`musicvideo` for audio, `movie` otherwise).
#[derive(Default)]
pub struct NfoFields<'a> {
    pub kind: &'a str,
    pub title: &'a str,
    pub artist: &'a str,
    pub album: &'a str,
    pub genre: &'a str,
    pub plot: &'a str,
    pub year: &'a str,
    pub premiered: &'a str,
    pub runtime: &'a str,
    pub thumb: &'a str,
    pub source: &'a str,
    pub source_id: &'a str,
}

pub fn build(f: &NfoFields) -> String {
    let root = if f.kind == "audio" {
        "musicvideo"
    } else {
        "movie"
    };
    let mut body =
        format!("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<{root}>\n");
    body.push_str(&tag("title", f.title));
    body.push_str(&tag(
        if f.kind == "audio" {
            "artist"
        } else {
            "studio"
        },
        f.artist,
    ));
    if f.kind == "audio" {
        body.push_str(&tag("album", f.album));
    }
    body.push_str(&tag("genre", f.genre));
    body.push_str(&tag("plot", f.plot));
    body.push_str(&tag("year", f.year));
    body.push_str(&tag("premiered", f.premiered));
    body.push_str(&tag("runtime", f.runtime));
    body.push_str(&tag("thumb", f.thumb));
    body.push_str(&tag("source", f.source));
    if !f.source_id.is_empty() {
        body.push_str(&format!(
            "  <uniqueid type=\"yoink\">{}</uniqueid>\n",
            esc(f.source_id)
        ));
    }
    body.push_str(&format!("</{root}>\n"));
    body
}

fn xml(root: &str, fields: &[(&str, &str)]) -> String {
    let mut body =
        format!("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<{root}>\n");
    for (name, value) in fields {
        if !value.is_empty() {
            body.push_str(&format!("  <{name}>{}</{name}>\n", esc(value)));
        }
    }
    body.push_str(&format!("</{root}>\n"));
    body
}

/// A folder-level `album.nfo` (Jellyfin/Kodi music convention).
pub fn build_album(album: &str, artist: &str, year: &str, thumb: &str) -> String {
    xml(
        "album",
        &[
            ("title", album),
            ("artist", artist),
            ("year", year),
            ("thumb", thumb),
        ],
    )
}

/// A folder-level `artist.nfo` (Jellyfin/Kodi music convention).
pub fn build_artist(artist: &str, thumb: &str) -> String {
    xml("artist", &[("name", artist), ("thumb", thumb)])
}

/// Build an .nfo from yt-dlp's info JSON (download time). Mirrors from_info.
pub fn from_info(info: &Value, kind: &str) -> String {
    let g = |k: &str| {
        info.get(k)
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string()
    };
    let upload_date = g("upload_date"); // YYYYMMDD
    let year = if upload_date.len() >= 4 {
        upload_date[..4].to_string()
    } else {
        String::new()
    };
    let premiered = if upload_date.len() == 8 {
        format!(
            "{}-{}-{}",
            &upload_date[..4],
            &upload_date[4..6],
            &upload_date[6..8]
        )
    } else {
        String::new()
    };
    let runtime = info
        .get("duration")
        .and_then(Value::as_f64)
        .filter(|d| *d > 0.0)
        .map(|d| ((d as i64) / 60).to_string())
        .unwrap_or_default();
    build(&NfoFields {
        kind,
        title: &g("title"),
        artist: &g("uploader"),
        plot: &g("description"),
        year: &year,
        premiered: &premiered,
        runtime: &runtime,
        thumb: &g("thumbnail"),
        source: &g("webpage_url"),
        source_id: &g("id"),
        ..Default::default()
    })
}

/// Write `<name>.nfo` next to the media (best-effort; never fatal).
pub fn write(media_path: &Path, body: &str) {
    let _ = std::fs::write(media_path.with_extension("nfo"), body);
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn from_info_video_is_movie_and_escapes() {
        let info = json!({
            "title": "Cool & Clip", "uploader": "Chan", "description": "Plot <here>",
            "upload_date": "20240115", "id": "abc", "duration": 245,
            "webpage_url": "http://x/v", "thumbnail": "http://x/t.jpg",
        });
        let xml = from_info(&info, "video");
        assert!(xml.starts_with("<?xml"));
        assert!(xml.contains("<movie>") && xml.contains("</movie>"));
        assert!(xml.contains("<title>Cool &amp; Clip</title>"));
        assert!(xml.contains("<studio>Chan</studio>"));
        assert!(xml.contains("<plot>Plot &lt;here&gt;</plot>"));
        assert!(xml.contains("<year>2024</year>"));
        assert!(xml.contains("<premiered>2024-01-15</premiered>"));
        assert!(xml.contains("<runtime>4</runtime>")); // 245s -> 4 min
        assert!(xml.contains("<uniqueid type=\"yoink\">abc</uniqueid>"));
    }

    #[test]
    fn from_info_audio_is_musicvideo_without_empty_tags() {
        let xml = from_info(
            &json!({"title": "Song", "uploader": "Artist", "id": "x"}),
            "audio",
        );
        assert!(xml.contains("<musicvideo>"));
        assert!(xml.contains("<artist>Artist</artist>"));
        assert!(!xml.contains("<plot>") && !xml.contains("<year>"));
    }

    #[test]
    fn build_audio_uses_tagged_fields() {
        let xml = build(&NfoFields {
            kind: "audio",
            title: "Danza Kuduro",
            artist: "Don Omar",
            album: "Meet the Orphans",
            genre: "Reggaeton",
            year: "2010",
            thumb: "http://x/cover.jpg",
            ..Default::default()
        });
        assert!(xml.contains("<musicvideo>"));
        assert!(xml.contains("<artist>Don Omar</artist>"));
        assert!(xml.contains("<album>Meet the Orphans</album>"));
        assert!(xml.contains("<genre>Reggaeton</genre>"));
        assert!(xml.contains("<year>2010</year>"));
        assert!(xml.contains("<thumb>http://x/cover.jpg</thumb>"));
    }

    #[test]
    fn write_creates_sidecar() {
        let dir = std::env::temp_dir().join(format!("yoink-nfo-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let media = dir.join("Song.mp3");
        std::fs::write(&media, b"x").unwrap();
        write(
            &media,
            &build(&NfoFields {
                kind: "audio",
                title: "Song",
                artist: "A",
                ..Default::default()
            }),
        );
        let out = dir.join("Song.nfo");
        assert!(out.exists());
        assert!(std::fs::read_to_string(&out)
            .unwrap()
            .contains("<title>Song</title>"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn build_album_folder_nfo() {
        let xml = build_album("Meet the Orphans", "Don Omar", "2010", "http://x/c.jpg");
        assert!(xml.contains("<album>") && xml.contains("</album>"));
        assert!(xml.contains("<title>Meet the Orphans</title>"));
        assert!(xml.contains("<artist>Don Omar</artist>"));
        assert!(xml.contains("<year>2010</year>"));
    }

    #[test]
    fn build_artist_folder_nfo_escapes_name() {
        let xml = build_artist("Don & Omar", "");
        assert!(xml.contains("<artist>") && xml.contains("</artist>"));
        assert!(xml.contains("<name>Don &amp; Omar</name>"));
    }
}
