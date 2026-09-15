"""Tests for the patched Odnoklassniki (ok.ru) extractor.

Covers only the fix + registration — no network, no specific URLs. The bug: the
bundled extractor calls `_parse_json` on `flashvars['metadata']`, which ok.ru now
serves as an already-parsed dict, raising a TypeError.
"""

from __future__ import annotations

from yt_dlp import YoutubeDL

from app.services.odnoklassniki_extractor import PatchedOdnoklassnikiIE, register


def test_parse_json_passes_a_dict_through():
    with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        ie = PatchedOdnoklassnikiIE(ydl)
        # A dict is already the parsed result — returned unchanged (the bug fix).
        payload = {"movie": {"title": "x"}, "videos": []}
        assert ie._parse_json(payload, "vid") == payload


def test_parse_json_still_parses_a_string():
    with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        ie = PatchedOdnoklassnikiIE(ydl)
        # A string (e.g. the player config) parses through the normal path.
        assert ie._parse_json('{"a": 2}', "vid") == {"a": 2}


def test_annotate_formats_labels_named_progressive_streams():
    # ok.ru's name-only progressive MP4s get a height, a resolution and muxed
    # codecs so the app can list them as quality tiers; the HLS variants (which
    # already carry a height) are left untouched.
    formats = [
        {"format_id": "hd", "ext": "mp4", "url": "x"},
        {"format_id": "full", "ext": "mp4", "url": "y"},
        {"format_id": "hls-2676", "ext": "mp4", "height": 682},
        {"format_id": "mobile", "ext": "mp4", "url": "z"},
    ]
    PatchedOdnoklassnikiIE._annotate_formats(formats)
    by_id = {f["format_id"]: f for f in formats}
    assert by_id["hd"]["height"] == 720 and by_id["hd"]["resolution"] == "720p"
    assert by_id["hd"]["vcodec"] == "h264" and by_id["hd"]["acodec"] == "aac"
    assert by_id["full"]["height"] == 1080
    assert by_id["mobile"]["height"] == 144
    # The HLS format already had a height, so it isn't relabelled.
    assert by_id["hls-2676"]["height"] == 682
    assert by_id["hls-2676"].get("vcodec") is None


def test_register_puts_the_patched_ie_first():
    with YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        register(ydl)
        key = PatchedOdnoklassnikiIE.ie_key()
        assert key in ydl._ies
        assert next(iter(ydl._ies)) == key  # ahead of the bundled extractor
