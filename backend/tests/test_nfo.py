"""The optional .nfo sidecar (Kodi/Jellyfin metadata) writer."""

from __future__ import annotations

from app.services.download_service import _nfo_xml, _write_nfo_sidecar


def test_nfo_xml_video_is_movie_and_escapes():
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
    xml = _nfo_xml(info, "video")
    assert xml.startswith("<?xml")
    assert "<movie>" in xml and "</movie>" in xml
    assert "<title>Cool &amp; Clip</title>" in xml  # & escaped
    assert "<studio>Chan</studio>" in xml
    assert "<plot>Plot &lt;here&gt;</plot>" in xml  # <> escaped
    assert "<year>2024</year>" in xml
    assert "<premiered>2024-01-15</premiered>" in xml
    assert "<runtime>4</runtime>" in xml  # 245s -> 4 min
    assert '<uniqueid type="yoink">abc</uniqueid>' in xml


def test_nfo_xml_audio_is_musicvideo_no_empty_tags():
    xml = _nfo_xml({"title": "Song", "uploader": "Artist", "id": "x"}, "audio")
    assert "<musicvideo>" in xml
    assert "<artist>Artist</artist>" in xml
    # Missing fields must not emit empty tags.
    assert "<plot>" not in xml and "<year>" not in xml


def test_write_nfo_sidecar(tmp_path):
    media = tmp_path / "Song.mp3"
    media.write_bytes(b"x")
    _write_nfo_sidecar(media, {"title": "Song", "id": "1"}, "audio")
    nfo = tmp_path / "Song.nfo"
    assert nfo.exists()
    assert "<title>Song</title>" in nfo.read_text(encoding="utf-8")
