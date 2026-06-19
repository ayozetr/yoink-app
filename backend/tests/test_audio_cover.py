"""Audio downloads embed the source thumbnail as a *fallback* cover."""

from __future__ import annotations

from app.models.media import DownloadRequest
from app.services.download_service import _build_options


def _noop(_d):  # trivial progress hook
    return None


def test_audio_embeds_thumbnail_for_cover_formats():
    for fmt in ("mp3", "m4a", "flac"):
        req = DownloadRequest(url="https://x.com/v", kind="audio", audio_format=fmt)
        opts = _build_options(req, _noop)
        assert opts.get("writethumbnail") is True
        keys = [pp.get("key") for pp in opts.get("postprocessors", [])]
        assert "EmbedThumbnail" in keys
        # It must run after the audio is extracted.
        assert keys.index("EmbedThumbnail") > keys.index("FFmpegExtractAudio")


def test_wav_does_not_embed_thumbnail():
    req = DownloadRequest(url="https://x.com/v", kind="audio", audio_format="wav")
    opts = _build_options(req, _noop)
    assert "writethumbnail" not in opts
    keys = [pp.get("key") for pp in opts.get("postprocessors", [])]
    assert "EmbedThumbnail" not in keys


def test_video_does_not_embed_thumbnail():
    req = DownloadRequest(url="https://x.com/v", kind="video")
    opts = _build_options(req, _noop)
    assert "writethumbnail" not in opts
