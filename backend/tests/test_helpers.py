"""Unit tests for pure helper functions across the services."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.humanize import humanize_bytes
from app.core.ytdlp_options import cookie_options, normalize_url
from app.models.media import DownloadRequest
from app.services.download_service import (
    _build_options,
    _format_eta,
    _format_speed,
    _map_progress,
    _parse_height,
    _parse_rate_limit,
)
from app.services.ytdlp_service import (
    _audio_langs,
    _audio_summary,
    _auto_caption_langs,
    _build_entry,
    _build_playlist,
    _build_video,
    _format_duration,
    _is_lossless_acodec,
    _map_format,
    _subtitle_langs,
)


@pytest.mark.parametrize(
    ("num", "expected"),
    [(0, "0 B"), (512, "512 B"), (1536, "1.5 KB"), (1048576, "1.0 MB"),
     (457389, "446.7 KB"), (5 * 1024**3, "5.0 GB")],
)
def test_humanize_bytes(num, expected):
    assert humanize_bytes(num) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(None, None), (5, "0:05"), (61, "1:01"), (3661, "1:01:01")],
)
def test_format_duration(seconds, expected):
    assert _format_duration(seconds) == expected


def test_format_speed_and_eta():
    assert _format_speed(None) is None
    assert _format_speed(3_500_000) == "3.3 MB/s"
    assert _format_eta(None) is None
    assert _format_eta(95) == "01:35"
    assert _format_eta(3725) == "1:02:05"


@pytest.mark.parametrize(
    ("quality", "expected"),
    [("1080p", 1080), ("720", 720), (None, None), ("best", None)],
)
def test_parse_height(quality, expected):
    assert _parse_height(quality) == expected


def test_normalize_url_tiktok_photo():
    assert (
        normalize_url("https://www.tiktok.com/@user/photo/123")
        == "https://www.tiktok.com/@user/video/123"
    )
    # Unrelated URLs pass through untouched.
    url = "https://www.youtube.com/watch?v=abc"
    assert normalize_url(url) == url


def test_cookie_options(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "cookies_from_browser", None)
    monkeypatch.setattr(settings, "cookies_file", None)
    assert cookie_options() == {}

    monkeypatch.setattr(settings, "cookies_from_browser", "firefox")
    assert cookie_options() == {"cookiesfrombrowser": ("firefox",)}

    # browser wins over file
    monkeypatch.setattr(settings, "cookies_file", "/tmp/c.txt")
    assert cookie_options() == {"cookiesfrombrowser": ("firefox",)}

    monkeypatch.setattr(settings, "cookies_from_browser", None)
    assert cookie_options() == {"cookiefile": "/tmp/c.txt"}


def test_update_version_compare():
    from app.services.updates import _is_newer, _parse_version

    assert _parse_version("v0.5.0") == (0, 5, 0)
    assert _parse_version("1.2.3-rc1") == (1, 2, 3)
    assert _is_newer("v0.6.0", "0.5.0") is True
    assert _is_newer("v0.5.0", "0.5.0") is False
    assert _is_newer("v0.4.9", "0.5.0") is False


def test_map_progress_downloading():
    event = _map_progress(
        {
            "status": "downloading",
            "downloaded_bytes": 50,
            "total_bytes": 100,
            "speed": 1048576,
            "eta": 30,
            "filename": "/out/clip.mp4",
        }
    )
    assert event is not None
    assert event.status == "downloading"
    assert event.percent == 50.0
    assert event.speed == "1.0 MB/s"
    assert event.eta == "00:30"
    assert event.filename == "clip.mp4"


def test_map_progress_finished_and_other():
    finished = _map_progress({"status": "finished", "total_bytes": 100, "filename": "a.webm"})
    assert finished is not None and finished.status == "processing" and finished.percent == 100.0
    assert _map_progress({"status": "error"}) is None


def test_map_format_video_vs_audio():
    video = _map_format(
        {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "filesize": 1000}
    )
    assert video.has_video and not video.has_audio and video.filesize == 1000
    audio = _map_format({"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a"})
    assert audio.has_audio and not audio.has_video


def test_build_video():
    video = _build_video(
        {
            "id": "abc",
            "title": "Clip",
            "duration": 61,
            "uploader": "Chan",
            "thumbnail": "http://t/x.jpg",
            "formats": [{"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a"}],
        }
    )
    assert video.id == "abc"
    assert video.duration_string == "1:01"
    assert video.thumbnail_url == "http://t/x.jpg"
    assert len(video.formats) == 1


def test_build_entry_and_playlist():
    assert _build_entry({"id": "x", "title": "No URL"}) is None

    playlist = _build_playlist(
        {
            "_type": "playlist",
            "id": "PL1",
            "title": "My List",
            "uploader": "Me",
            "entries": [
                {"id": "a", "title": "A", "url": "http://x/a", "duration": 61},
                {"id": "b", "title": "B", "url": "http://x/b"},
                {"id": "c", "title": "skip"},  # no url -> dropped
            ],
        }
    )
    assert playlist.entry_count == 3  # total reported (incl. the dropped one)
    assert [e.id for e in playlist.entries] == ["a", "b"]
    assert playlist.entries[0].duration_string == "1:01"
    # 2 listed < 3 reported (entry "c" was dropped for missing a URL), so the
    # listing is flagged truncated rather than silently short.
    assert playlist.truncated is True


@pytest.mark.parametrize("container", ["mp4", "mov", "mkv"])
def test_build_options_video_container(temp_dirs, container):
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video", container=container),
        hook=lambda raw: None,
    )
    assert options["merge_output_format"] == container
    assert "postprocessors" not in options
    # Height-based selector logic is unchanged.
    assert options["format"] == "bestvideo+bestaudio/best"


def test_build_options_video_quality_selector(temp_dirs):
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video", quality="720p"),
        hook=lambda raw: None,
    )
    assert options["format"] == (
        "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
    )


@pytest.mark.parametrize(
    ("audio_format", "expected_codec", "has_quality"),
    [
        ("mp3", "mp3", True),
        ("m4a", "m4a", True),
        ("flac", "flac", False),
        ("wav", "wav", False),
    ],
)
def test_build_options_audio_format(
    temp_dirs, audio_format, expected_codec, has_quality
):
    settings.audio_bitrate = "192"  # exercise a concrete lossy bitrate
    options = _build_options(
        DownloadRequest(url="http://x/a", kind="audio", audio_format=audio_format),
        hook=lambda raw: None,
    )
    # m4a prefers an AAC/m4a source so extraction copies the stream (no re-encode).
    expected_format = (
        "bestaudio[ext=m4a]/bestaudio/best" if audio_format == "m4a" else "bestaudio/best"
    )
    assert options["format"] == expected_format
    assert "merge_output_format" not in options
    (pp,) = options["postprocessors"]
    assert pp["key"] == "FFmpegExtractAudio"
    assert pp["preferredcodec"] == expected_codec
    assert ("preferredquality" in pp) is has_quality
    if has_quality:
        assert pp["preferredquality"] == "192"


def test_audio_bitrate_best_drops_target(temp_dirs):
    settings.audio_bitrate = "best"
    options = _build_options(
        DownloadRequest(url="http://x/a", kind="audio", audio_format="mp3"),
        hook=lambda raw: None,
    )
    (pp,) = options["postprocessors"]
    assert "preferredquality" not in pp


def test_video_codec_sets_format_sort(temp_dirs):
    settings.video_codec = "av1"
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video", quality="1080p"),
        hook=lambda raw: None,
    )
    assert options["format_sort"] == ["vcodec:av01"]
    settings.video_codec = "any"
    plain = _build_options(
        DownloadRequest(url="http://x/v", kind="video"),
        hook=lambda raw: None,
    )
    assert "format_sort" not in plain


@pytest.mark.parametrize(
    ("acodec", "expected"),
    [
        ("flac", True),
        ("ALAC", True),
        ("wav", True),
        ("pcm_s16le", True),
        ("tta", True),
        ("wavpack", True),
        ("ape", True),
        ("aac", False),
        ("mp3", False),
        ("opus", False),
        ("vorbis", False),
        ("none", False),
        ("", False),
        (None, False),
    ],
)
def test_is_lossless_acodec(acodec, expected):
    assert _is_lossless_acodec(acodec) is expected


def test_audio_summary_lossless_and_best_abr():
    formats = [
        {"acodec": "none", "vcodec": "avc1", "abr": None},  # video-only, no audio
        {"acodec": "mp4a", "abr": 128.0},
        {"acodec": "opus", "abr": 160},
        {"acodec": "flac", "abr": 1411.2},  # lossless, highest abr
    ]
    lossless, best_abr = _audio_summary(formats)
    assert lossless is True
    assert best_abr == 1411.2


def test_audio_summary_lossy_only():
    formats = [
        {"acodec": "aac", "abr": 192},
        {"acodec": "mp3", "abr": 320},
        {"acodec": "opus"},  # no abr
    ]
    lossless, best_abr = _audio_summary(formats)
    assert lossless is False
    assert best_abr == 320.0


def test_audio_summary_no_audio_or_unknown():
    assert _audio_summary([{"acodec": "none", "abr": 0}]) == (False, None)
    assert _audio_summary(None) == (False, None)
    assert _audio_summary([]) == (False, None)


def _pp_keys(options):
    """Postprocessor `key` values present on a built options dict."""
    return [pp["key"] for pp in options.get("postprocessors", [])]


def test_build_options_embed_subs_specific_lang(temp_dirs):
    options = _build_options(
        DownloadRequest(
            url="http://x/v", kind="video", embed_subs=True, subtitle_lang="en"
        ),
        hook=lambda raw: None,
    )
    assert options["writesubtitles"] is True
    assert options["writeautomaticsub"] is True
    assert options["subtitleslangs"] == ["en"]
    assert "FFmpegEmbedSubtitle" in _pp_keys(options)


@pytest.mark.parametrize("subtitle_lang", [None, "all"])
def test_build_options_embed_subs_all(temp_dirs, subtitle_lang):
    options = _build_options(
        DownloadRequest(
            url="http://x/v",
            kind="video",
            embed_subs=True,
            subtitle_lang=subtitle_lang,
        ),
        hook=lambda raw: None,
    )
    assert options["subtitleslangs"] == ["all"]
    assert "FFmpegEmbedSubtitle" in _pp_keys(options)


def test_build_options_no_subs_by_default(temp_dirs):
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video"),
        hook=lambda raw: None,
    )
    assert "writesubtitles" not in options
    assert "writeautomaticsub" not in options
    assert "subtitleslangs" not in options
    assert "FFmpegEmbedSubtitle" not in _pp_keys(options)


def test_build_options_embed_chapters(temp_dirs):
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video", embed_chapters=True),
        hook=lambda raw: None,
    )
    metadata = [
        pp for pp in options["postprocessors"] if pp["key"] == "FFmpegMetadata"
    ]
    assert len(metadata) == 1
    assert metadata[0]["add_chapters"] is True
    assert metadata[0]["add_metadata"] is True


def test_build_options_no_chapters_by_default(temp_dirs):
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video"),
        hook=lambda raw: None,
    )
    assert "FFmpegMetadata" not in _pp_keys(options)


def test_build_options_subs_and_chapters_together(temp_dirs):
    options = _build_options(
        DownloadRequest(
            url="http://x/v",
            kind="video",
            embed_subs=True,
            subtitle_lang="es",
            embed_chapters=True,
        ),
        hook=lambda raw: None,
    )
    keys = _pp_keys(options)
    assert "FFmpegEmbedSubtitle" in keys
    assert "FFmpegMetadata" in keys


def test_subtitle_langs_manual_and_auto_split():
    info = {
        "subtitles": {"en": [{}], "es": [{}]},
        "automatic_captions": {"es": [{}], "fr": [{}]},
    }
    manual = _subtitle_langs(info)
    assert manual == ["en", "es"]
    # auto-captions exclude codes already published as manual subs (es)
    assert _auto_caption_langs(info, manual) == ["fr"]


def test_subtitle_langs_defensive():
    assert _subtitle_langs({}) == []
    assert _subtitle_langs({"subtitles": None}) == []
    assert _auto_caption_langs({}, []) == []
    assert _auto_caption_langs({"automatic_captions": "nope"}, []) == []


def test_build_video_subtitles_and_chapters():
    video = _build_video(
        {
            "id": "abc",
            "title": "Clip",
            "subtitles": {"en": [{}]},
            "automatic_captions": {"de": [{}]},
            "chapters": [{"title": "Intro", "start_time": 0}],
        }
    )
    assert video.subtitle_langs == ["en"]
    assert video.auto_caption_langs == ["de"]
    assert video.has_chapters is True


def test_build_video_no_subtitles_or_chapters():
    video = _build_video({"id": "abc", "title": "Clip"})
    assert video.subtitle_langs == []
    assert video.has_chapters is False


def test_build_options_audio_multistreams_no_cap(temp_dirs):
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video", container="mkv",
                        audio_multistreams=True),
        hook=lambda raw: None,
    )
    assert options["allow_multiple_audio_streams"] is True
    assert options["format"] == "bv*+mergeall[vcodec=none]"
    assert options["merge_output_format"] == "mkv"


def test_build_options_audio_multistreams_with_cap(temp_dirs):
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video", container="mkv",
                        quality="1080p", audio_multistreams=True),
        hook=lambda raw: None,
    )
    assert options["allow_multiple_audio_streams"] is True
    assert options["format"] == "bv*[height<=1080]+mergeall[vcodec=none]"


def test_build_options_no_audio_multistreams_by_default(temp_dirs):
    # audio_multistreams=False leaves the normal selector + options untouched.
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video", container="mkv"),
        hook=lambda raw: None,
    )
    assert "allow_multiple_audio_streams" not in options
    assert "mergeall" not in options["format"]
    assert options["format"] == "bestvideo+bestaudio/best"


def test_audio_langs_distinct_sorted_non_null():
    info = {
        "formats": [
            {"acodec": "none", "vcodec": "avc1", "language": "en"},  # no audio
            {"acodec": "mp4a", "language": "es"},
            {"acodec": "opus", "language": "en"},
            {"acodec": "opus", "language": "en"},  # duplicate
            {"acodec": "aac", "language": None},  # null lang ignored
            {"acodec": "aac"},  # missing lang ignored
            {"acodec": "aac", "language": ""},  # empty lang ignored
        ]
    }
    assert _audio_langs(info) == ["en", "es"]


def test_audio_langs_defensive():
    assert _audio_langs({}) == []
    assert _audio_langs({"formats": None}) == []
    assert _audio_langs({"formats": "nope"}) == []
    assert _audio_langs({"formats": [{"acodec": "none", "language": "en"}]}) == []


def test_build_video_audio_langs():
    video = _build_video(
        {
            "id": "abc",
            "title": "Clip",
            "formats": [
                {"format_id": "1", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a",
                 "language": "ja"},
                {"format_id": "2", "ext": "m4a", "vcodec": "none", "acodec": "mp4a",
                 "language": "en"},
            ],
        }
    )
    assert video.audio_langs == ["en", "ja"]


def test_build_options_sponsorblock_off_by_default(temp_dirs):
    """No SponsorBlock postprocessors unless it's explicitly enabled."""
    options = _build_options(
        DownloadRequest(url="http://x/a", kind="audio", audio_format="mp3"),
        hook=lambda raw: None,
    )
    assert [pp["key"] for pp in options["postprocessors"]] == ["FFmpegExtractAudio"]


def test_build_options_sponsorblock_remove_audio(temp_dirs, monkeypatch):
    monkeypatch.setattr(settings, "sponsorblock_enabled", True)
    monkeypatch.setattr(settings, "sponsorblock_action", "remove")
    options = _build_options(
        DownloadRequest(url="http://x/a", kind="audio", audio_format="mp3"),
        hook=lambda raw: None,
    )
    keys = [pp["key"] for pp in options["postprocessors"]]
    # SponsorBlock fetch + chapter modify run before the audio extraction.
    assert keys == ["SponsorBlock", "ModifyChapters", "FFmpegExtractAudio"]
    assert options["postprocessors"][1]["remove_sponsor_segments"]


def test_build_options_sponsorblock_mark_video(temp_dirs, monkeypatch):
    monkeypatch.setattr(settings, "sponsorblock_enabled", True)
    monkeypatch.setattr(settings, "sponsorblock_action", "mark")
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video"),
        hook=lambda raw: None,
    )
    # "mark" computes markers (ModifyChapters with no cuts) and an FFmpegMetadata
    # PP must follow to actually write them — without it mark mode is a no-op.
    assert [pp["key"] for pp in options["postprocessors"]] == [
        "SponsorBlock",
        "ModifyChapters",
        "FFmpegMetadata",
    ]
    assert options["postprocessors"][1]["remove_sponsor_segments"] == []
    assert options["postprocessors"][2]["add_chapters"] is True


def test_build_options_sponsorblock_remove_no_chapters_pp(temp_dirs, monkeypatch):
    # "remove" cuts segments; it must NOT add the FFmpegMetadata chapters PP.
    monkeypatch.setattr(settings, "sponsorblock_enabled", True)
    monkeypatch.setattr(settings, "sponsorblock_action", "remove")
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video"),
        hook=lambda raw: None,
    )
    assert [pp["key"] for pp in options["postprocessors"]] == [
        "SponsorBlock",
        "ModifyChapters",
    ]


def test_build_options_trim_range(temp_dirs):
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video", trim_start=30, trim_end=130),
        hook=lambda raw: None,
    )
    assert "download_ranges" in options
    assert options["force_keyframes_at_cuts"] is True


def test_build_options_no_trim_by_default(temp_dirs):
    options = _build_options(
        DownloadRequest(url="http://x/v", kind="video"),
        hook=lambda raw: None,
    )
    assert "download_ranges" not in options


def test_parse_rate_limit():
    assert _parse_rate_limit("1M") == 1024**2
    assert _parse_rate_limit("500K") == 500 * 1024
    assert _parse_rate_limit("1m") == 1024**2  # case-insensitive
    # Unset / unparseable / non-positive / non-finite all collapse to None.
    for bad in (None, "", "  ", "M", "1X", "-1M", "0", "inf", "nan"):
        assert _parse_rate_limit(bad) is None


def test_filename_template_cannot_escape_download_dir(temp_dirs):
    download_root = str(settings.ensure_download_dir())
    for evil in ("../../etc/evil", "/etc/passwd", "..\\..\\x", "   "):
        settings.filename_template = evil
        options = _build_options(
            DownloadRequest(url="http://x/v", kind="video"),
            hook=lambda raw: None,
        )
        # The resolved output template stays inside the download directory.
        assert options["outtmpl"].startswith(download_root)
    settings.filename_template = "%(title)s"
