"""Tests for the `yoink` CLI front-end (argument parsing + guards, no network)."""

from __future__ import annotations

import pytest

from app.cli import _build_parser, _parse_items, _selected, main


class _Entry:
    def __init__(self, title: str):
        self.title = title


def test_parse_items_expands_ranges():
    assert _parse_items("1,3,5-8") == {1, 3, 5, 6, 7, 8}
    assert _parse_items(" 2 ") == {2}


def test_selected_applies_items_and_filter():
    entries = [_Entry("Alpha"), _Entry("Beta remix"), _Entry("Gamma")]
    by_items = _selected(entries, _build_parser().parse_args(["u", "--items", "1,3"]),
                         key=lambda e: e.title)
    assert [e.title for e in by_items] == ["Alpha", "Gamma"]
    by_text = _selected(entries, _build_parser().parse_args(["u", "--filter", "REMIX"]),
                        key=lambda e: e.title)
    assert [e.title for e in by_text] == ["Beta remix"]


def test_parser_reads_flags():
    a = _build_parser().parse_args(["http://x", "--audio", "-f", "mp3", "-q", "1080"])
    assert a.url == "http://x"
    assert a.audio and not a.video
    assert a.format == "mp3"
    assert a.quality == "1080"


def test_audio_and_video_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["http://x", "--audio", "--video"])


def test_invalid_format_is_rejected():
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["http://x", "-f", "ogg"])


def test_vr_flags_parse():
    a = _build_parser().parse_args(["http://x", "--vr-layout", "180_sbs"])
    assert a.vr_layout == "180_sbs"
    b = _build_parser().parse_args(["http://x", "--vr"])
    assert b.vr and b.vr_layout is None
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["http://x", "--vr-layout", "nope"])


def test_invalid_url_returns_2(capsys):
    # main() validates the URL into a DownloadRequest before any network call, so a
    # bogus URL fails fast with exit code 2 (invalid arguments) and never downloads.
    assert main(["not-a-url"]) == 2
    assert "invalid request" in capsys.readouterr().err
