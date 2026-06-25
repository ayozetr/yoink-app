"""The optional .nfo sidecar (Kodi/Jellyfin metadata) writer."""

from __future__ import annotations

from app.services import nfo


def test_from_info_video_is_movie_and_escapes():
    info = {
        "title": "Cool & Clip",
        "uploader": "Chan",
        "description": "Plot <here>",
        "upload_date": "20240115",
        "id": "abc",
        "duration": 245,
        "webpage_url": "http://x/v",
        "thumbnail": "http://x/t.jpg",
    }
    xml = nfo.from_info(info, "video")
    assert xml.startswith("<?xml")
    assert "<movie>" in xml and "</movie>" in xml
    assert "<title>Cool &amp; Clip</title>" in xml  # & escaped
    assert "<studio>Chan</studio>" in xml
    assert "<plot>Plot &lt;here&gt;</plot>" in xml  # <> escaped
    assert "<year>2024</year>" in xml
    assert "<premiered>2024-01-15</premiered>" in xml
    assert "<runtime>4</runtime>" in xml  # 245s -> 4 min
    assert '<uniqueid type="yoink">abc</uniqueid>' in xml


def test_from_info_audio_is_musicvideo_no_empty_tags():
    xml = nfo.from_info({"title": "Song", "uploader": "Artist", "id": "x"}, "audio")
    assert "<musicvideo>" in xml
    assert "<artist>Artist</artist>" in xml
    # Missing fields must not emit empty tags.
    assert "<plot>" not in xml and "<year>" not in xml


def test_build_audio_uses_tagged_fields():
    # The auto-tag path builds from explicit (tagged) fields, incl. <album>.
    xml = nfo.build(
        kind="audio", title="Danza Kuduro", artist="Don Omar",
        album="Meet the Orphans", year="2010", thumb="http://x/cover.jpg",
    )
    assert "<musicvideo>" in xml
    assert "<artist>Don Omar</artist>" in xml
    assert "<album>Meet the Orphans</album>" in xml
    assert "<year>2010</year>" in xml
    assert "<thumb>http://x/cover.jpg</thumb>" in xml


def test_write_sidecar(tmp_path):
    media = tmp_path / "Song.mp3"
    media.write_bytes(b"x")
    nfo.write(media, nfo.build(kind="audio", title="Song", artist="A"))
    out = tmp_path / "Song.nfo"
    assert out.exists()
    assert "<title>Song</title>" in out.read_text(encoding="utf-8")
