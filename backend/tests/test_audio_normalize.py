"""Tests for loudness normalization (ffmpeg two-pass loudnorm).

Uses ffmpeg to synthesize a quiet clip, then checks that normalization raises it
to the target. Skipped when ffmpeg isn't on PATH.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from app.services import audio_normalize as norm

FFMPEG = shutil.which("ffmpeg")
requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not on PATH")


def _synth(path, extra_af=None, dur=6):
    af = "anoisesrc=d={}:c=pink:a=0.05".format(dur)
    args = [FFMPEG, "-hide_banner", "-y", "-f", "lavfi", "-i", af]
    if path.suffix == ".mp3":
        args += ["-c:a", "libmp3lame", "-b:a", "192k"]
    subprocess.run([*args, str(path)], capture_output=True, check=True)


def _lufs(path):
    measured = norm._measure(path, -14.0)  # target doesn't affect the input measure
    assert measured is not None
    return float(measured["input_i"])


@requires_ffmpeg
def test_normalize_raises_quiet_audio_to_target(tmp_path):
    src = tmp_path / "clip.mp3"
    _synth(src)
    before = _lufs(src)

    ok = norm.normalize(src, "mp3", "192")

    assert ok is True
    assert src.exists() and src.stat().st_size > 0
    after = _lufs(src)
    assert after > before  # a quiet clip got louder
    assert abs(after - (-14.0)) < 2.0  # landed on the -14 LUFS target


@requires_ffmpeg
def test_normalize_honors_custom_target(tmp_path):
    """A non-default target (e.g. -20 LUFS) is what the file lands on."""
    src = tmp_path / "clip.mp3"
    _synth(src)
    ok = norm.normalize(src, "mp3", "192", target_i=-20.0)
    assert ok is True
    assert abs(_lufs(src) - (-20.0)) < 2.0


@requires_ffmpeg
def test_normalize_preserves_embedded_cover(tmp_path):
    # Embed a cover, normalize, and confirm it survives the re-encode. Regression:
    # `-af` re-encodes only audio and auto stream selection dropped the attached pic.
    src = tmp_path / "clip.mp3"
    _synth(src)
    cover = tmp_path / "cover.png"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-y", "-f", "lavfi", "-i",
         "color=c=red:s=64x64:d=1", "-frames:v", "1", str(cover)],
        capture_output=True, check=True,
    )
    with_cover = tmp_path / "withcover.mp3"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-y", "-i", str(src), "-i", str(cover),
         "-map", "0:a", "-map", "1:v", "-c", "copy", "-id3v2_version", "3",
         "-disposition:v:0", "attached_pic", str(with_cover)],
        capture_output=True, check=True,
    )
    assert norm._has_cover(with_cover) is True
    assert norm.normalize(with_cover, "mp3", "192") is True
    assert norm._has_cover(with_cover) is True  # cover survived the normalization


@requires_ffmpeg
def test_normalize_leaves_no_temp_file(tmp_path):
    src = tmp_path / "clip.wav"
    _synth(src)
    norm.normalize(src, "wav")
    assert not list(tmp_path.glob("*.loudnorm*"))  # temp cleaned / renamed away


def test_normalize_rejects_unsupported_format(tmp_path):
    f = tmp_path / "x.ogg"
    f.write_bytes(b"not audio")
    assert norm.normalize(f, "ogg") is False


@requires_ffmpeg
def test_normalize_missing_file_is_best_effort(tmp_path):
    # A path that can't be measured must fail cleanly (False), never raise.
    assert norm.normalize(tmp_path / "nope.mp3", "mp3") is False
