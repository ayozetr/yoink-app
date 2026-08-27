"""Tests for the `yoink` CLI front-end (argument parsing + guards, no network)."""

from __future__ import annotations

import pytest

import types

from app.cli import (
    _apply_cli_overrides,
    _build_parser,
    _build_request,
    _coerce_setting,
    _collect_urls,
    _completion_script,
    _extract_urls,
    _parse_items,
    _run_config,
    _selected,
    _timestamp,
    main,
)


class _Defaults:
    """Stand-in for the persisted settings defaults used by _build_request."""

    default_kind = "video"
    default_quality = "best"
    default_container = "mp4"
    default_audio_format = "mp3"
    default_embed_subs = False
    default_embed_chapters = False


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
    assert a.urls == ["http://x"]
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


def test_timestamp_parses_seconds_and_clocks():
    assert _timestamp("90") == 90.0
    assert _timestamp("1.5") == 1.5
    assert _timestamp("1:30") == 90.0
    assert _timestamp("01:02:03") == 3723.0
    with pytest.raises(Exception):  # argparse.ArgumentTypeError
        _timestamp("1:2:3:4")
    with pytest.raises(Exception):
        _timestamp("nope")


def test_trim_flags_parse_to_seconds():
    a = _build_parser().parse_args(["u", "--trim-start", "1:30", "--trim-end", "2:05"])
    assert a.trim_start == 90.0
    assert a.trim_end == 125.0


def test_inverted_trim_returns_2(capsys):
    # Validated up front, before any network/URL work — a real-looking URL still exits 2.
    assert main(["http://x", "--trim-start", "100", "--trim-end", "10"]) == 2
    assert "trim-end" in capsys.readouterr().err


def test_subs_flag_variants():
    bare = _build_parser().parse_args(["u", "--subs"])
    assert bare.subs == "all"  # const when no language is given
    lang = _build_parser().parse_args(["u", "--subs", "es"])
    assert lang.subs == "es"
    with pytest.raises(SystemExit):  # --subs and --no-subs are mutually exclusive
        _build_parser().parse_args(["u", "--subs", "en", "--no-subs"])


def test_chapters_flags_are_mutually_exclusive():
    assert _build_parser().parse_args(["u", "--chapters"]).chapters is True
    assert _build_parser().parse_args(["u", "--no-chapters"]).no_chapters is True
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["u", "--chapters", "--no-chapters"])


def test_build_request_maps_subs_chapters_trim():
    a = _build_parser().parse_args(
        ["https://x/", "--subs", "es", "--chapters", "--trim-start", "1:00",
         "--trim-end", "1:30"]
    )
    r = _build_request("https://x/", a, _Defaults)
    assert r.embed_subs is True and r.subtitle_lang == "es"
    assert r.embed_chapters is True
    assert r.trim_start == 60.0 and r.trim_end == 90.0


def test_build_request_ignores_subs_for_audio():
    a = _build_parser().parse_args(["https://x/", "--audio", "--subs", "es"])
    r = _build_request("https://x/", a, _Defaults)
    assert r.embed_subs is False and r.subtitle_lang is None


def test_bare_subs_requests_all_languages():
    a = _build_parser().parse_args(["https://x/", "--subs"])
    r = _build_request("https://x/", a, _Defaults)
    # "all" maps to subtitle_lang=None, which the engine reads as every real track.
    assert r.embed_subs is True and r.subtitle_lang is None


@pytest.mark.parametrize(
    "shell, marker",
    [
        ("bash", "complete -F _yoink yoink"),
        ("zsh", "#compdef yoink"),
        ("fish", "complete -c yoink"),
    ],
)
def test_completion_script_per_shell(shell, marker):
    script = _completion_script(shell)
    assert marker in script
    # The volatile bits come from the parser, so a choice list must show through.
    assert "mp3 m4a flac wav" in script


def test_print_completion_exits_before_url_is_required(capsys):
    # Like --help: the action fires during parsing and exits 0, so no URL is needed.
    with pytest.raises(SystemExit) as exc:
        main(["--print-completion", "fish"])
    assert exc.value.code == 0
    assert "complete -c yoink" in capsys.readouterr().out


def test_completion_includes_file_arg_arms():
    # --batch-file / --cookies-file take a FILE, so completion offers file names.
    bash = _completion_script("bash")
    assert "--batch-file) COMPREPLY=( $(compgen -f" in bash
    assert "--cookies-file) COMPREPLY=( $(compgen -f" in bash


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "yoink" in capsys.readouterr().out


# ---------------------------------------------------------------- batch input


def test_extract_urls_takes_only_links_from_prose():
    text = (
        "# my list\n"
        "https://youtu.be/AAA  best clip\n"
        "just a note, no link here\n"
        "see https://youtube.com/watch?v=BBB, and https://soundcloud.com/x/y).\n"
    )
    assert _extract_urls(text) == [
        "https://youtu.be/AAA",
        "https://youtube.com/watch?v=BBB",  # trailing comma stripped
        "https://soundcloud.com/x/y",       # trailing ). stripped
    ]


def test_collect_urls_dedupes_preserving_order():
    a = _build_parser().parse_args(["https://x/1", "https://x/2", "https://x/1"])
    assert _collect_urls(a) == ["https://x/1", "https://x/2"]


def test_collect_urls_reads_a_batch_file(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("# notes\nhttps://a/1\njunk line\nhttps://a/2\nhttps://a/1\n")
    a = _build_parser().parse_args(["-a", str(f)])
    assert _collect_urls(a) == ["https://a/1", "https://a/2"]


def test_no_url_returns_2(capsys):
    assert main([]) == 2
    assert "no URL given" in capsys.readouterr().err


# ------------------------------------------------------------- per-run overrides


def test_apply_cli_overrides_layers_flags_onto_settings():
    s = types.SimpleNamespace()
    a = _build_parser().parse_args(
        ["u", "--rate-limit", "2M", "--proxy", "socks5://p", "-t", "%(id)s",
         "--cookies-from-browser", "firefox", "--sponsorblock", "mark", "--normalize"]
    )
    _apply_cli_overrides(a, s)
    assert s.rate_limit == "2M"
    assert s.proxy == "socks5://p"
    assert s.filename_template == "%(id)s"
    assert s.cookies_from_browser == "firefox"
    assert s.sponsorblock_enabled is True and s.sponsorblock_action == "mark"
    assert s.normalize_audio is True


def test_sponsorblock_bare_defaults_to_remove():
    assert _build_parser().parse_args(["u", "--sponsorblock"]).sponsorblock == "remove"
    assert _build_parser().parse_args(
        ["u", "--sponsorblock", "mark"]).sponsorblock == "mark"
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["u", "--sponsorblock", "nope"])


def test_quiet_and_no_progress_parse():
    a = _build_parser().parse_args(["u", "--quiet", "--no-progress"])
    assert a.quiet is True and a.no_progress is True


def test_video_codec_and_audio_bitrate_overrides():
    s = types.SimpleNamespace()
    a = _build_parser().parse_args(
        ["u", "--video-codec", "av1", "--audio-bitrate", "192"]
    )
    _apply_cli_overrides(a, s)
    assert s.video_codec == "av1"
    assert s.audio_bitrate == "192"


def test_list_formats_flag_parses():
    assert _build_parser().parse_args(["u", "--list-formats"]).list_formats is True


def test_coerce_setting_types():
    assert _coerce_setting(True, "false") is False
    assert _coerce_setting(True, "on") is True
    assert _coerce_setting("x", "none") is None
    assert _coerce_setting("x", "") is None
    assert _coerce_setting("x", "hello") == "hello"


def test_config_get_set_and_errors(temp_dirs, capsys):
    # set persists and get reads it back (isolated to the temp data dir).
    assert _run_config(["set", "default_kind", "audio"], as_json=False) == 0
    capsys.readouterr()
    assert _run_config(["get", "default_kind"], as_json=False) == 0
    assert capsys.readouterr().out.strip() == "audio"
    # unknown key and invalid value both fail cleanly (exit 2).
    assert _run_config(["get", "nope"], as_json=False) == 2
    assert _run_config(["set", "default_kind", "bogus"], as_json=False) == 2
    # bare `config` prints every setting.
    capsys.readouterr()
    assert _run_config([], as_json=False) == 0
    assert "download_dir = " in capsys.readouterr().out


def test_run_backend_dispatches_to_cli_with_args():
    """The packaged entry point runs the CLI when given arguments (server mode
    otherwise). This is what lets the bundled binary double as `yoink-cli`."""
    import subprocess
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "run_backend.py", "--version"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout.strip().startswith("yoink ")
