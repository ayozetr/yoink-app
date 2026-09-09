"""EBU R128 loudness normalization (ffmpeg two-pass ``loudnorm``).

Brings every audio download to the same integrated loudness (-14 LUFS, the
streaming standard) so tracks play at the same volume regardless of how the
source was mastered — a quiet track is raised, a loud one lowered, both landing
on the target. Two-pass: measure the file, then re-encode applying the measured
values (precise, unlike a single-pass estimate).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

from app.core.ffmpeg import ffmpeg_path, ffprobe_path

logger = logging.getLogger(__name__)

# Streaming-standard target (Spotify/YouTube). TP = true-peak ceiling (dBTP);
# LRA = loudness range — loudnorm's reference values for this target.
_TARGET_I = -14.0
_TARGET_TP = -1.5
_TARGET_LRA = 11.0

# Re-encode args per output format (loudnorm is a filter, so the stream is
# re-encoded — match the download's codec). Lossless formats carry no bitrate.
_ENCODERS: dict[str, list[str]] = {
    "mp3": ["-c:a", "libmp3lame"],
    "m4a": ["-c:a", "aac"],
    "flac": ["-c:a", "flac"],
    "wav": ["-c:a", "pcm_s16le"],
}
# Lossy bitrate for the re-encode when the user picked "best" (keep it high).
_BEST_BITRATE = {"mp3": "320", "m4a": "256"}


# A single ffmpeg/ffprobe pass must not run forever: a corrupt or absurdly long
# input can hang loudnorm, and this runs on the download worker *while the global
# download lock is held* — so a hang would wedge the whole queue for every client.
# Cap it (generous: a legit two-pass re-encode of a long track finishes well under
# this) and treat a timeout as a normalization failure (keep the original file).
_FFMPEG_TIMEOUT = 1800  # 30 min
_FFPROBE_TIMEOUT = 60


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run ffmpeg; ``None`` if it timed out (a normalization failure)."""
    try:
        return subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-nostdin", *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=_FFMPEG_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("loudnorm: ffmpeg timed out after %ss", _FFMPEG_TIMEOUT)
        return None


def _run_ffprobe(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run ffprobe; ``None`` if it timed out."""
    try:
        return subprocess.run(
            [ffprobe_path(), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=_FFPROBE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("loudnorm: ffprobe timed out after %ss", _FFPROBE_TIMEOUT)
        return None


# loudnorm's measured-values JSON keys (first pass) that the second pass needs.
_MEASURED_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")


def _measure(path: Path, target_i: float) -> dict[str, str] | None:
    """First pass: analyze loudness; returns loudnorm's measured JSON values."""
    filt = (
        f"loudnorm=I={target_i}:TP={_TARGET_TP}:LRA={_TARGET_LRA}:print_format=json"
    )
    proc = _run_ffmpeg(["-i", str(path), "-af", filt, "-f", "null", "-"])
    if proc is None:
        return None
    # loudnorm prints its JSON to stderr; pick the brace block that actually holds
    # the measured values, not merely the first `{...}` in ffmpeg's log.
    for block in reversed(re.findall(r"\{[^{}]+\}", proc.stderr)):
        if '"input_i"' in block:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                return None
    return None


def _sample_rate(path: Path) -> str:
    """The audio's sample rate (Hz), so the re-encode preserves it instead of
    leaving loudnorm's internal 192 kHz. Falls back to 44100."""
    proc = _run_ffprobe(
        [
            "-v", "quiet", "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate", "-of", "csv=p=0", str(path),
        ]
    )
    rate = proc.stdout.strip() if proc else ""
    return rate if rate.isdigit() else "44100"


def _has_cover(path: Path) -> bool:
    """True if the file carries a video/attached-picture stream (embedded cover)."""
    proc = _run_ffprobe(
        [
            "-v", "quiet", "-select_streams", "v",
            "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path),
        ]
    )
    return bool(proc and "video" in proc.stdout)


def normalize(
    path: Path,
    audio_format: str,
    bitrate: str = "best",
    target_i: float = _TARGET_I,
) -> bool:
    """Two-pass loudness-normalize ``path`` in place to ``target_i`` LUFS
    (default -14, the streaming standard).

    Best-effort: on any measurement/encode failure it leaves the original file
    untouched and returns ``False``, so a normalization hiccup never loses a
    finished download.
    """
    encoder = _ENCODERS.get(audio_format)
    if encoder is None:
        return False
    measured = _measure(path, target_i)
    if measured is None:
        logger.warning("loudnorm: could not measure %s", path.name)
        return False
    if any(measured.get(key) is None for key in _MEASURED_KEYS):
        logger.warning("loudnorm: incomplete measurement for %s", path.name)
        return False
    filt = (
        f"loudnorm=I={target_i}:TP={_TARGET_TP}:LRA={_TARGET_LRA}"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true"
    )
    bitrate_args: list[str] = []
    if audio_format in _BEST_BITRATE:
        chosen = _BEST_BITRATE[audio_format] if bitrate == "best" else bitrate
        bitrate_args = ["-b:a", f"{chosen}k"]
    # Preserve an embedded cover through the re-encode: `-af` only touches audio,
    # and without an explicit map ffmpeg's auto stream selection can drop the
    # attached picture (e.g. the fallback thumbnail yt-dlp embeds when auto-tagging
    # is off). Only when a cover stream actually exists — mapping a non-existent
    # video stream (or muxing one into WAV, which can't hold it) would fail the job.
    cover_args: list[str] = []
    if audio_format != "wav" and _has_cover(path):
        cover_args = [
            "-map", "0:a", "-map", "0:v", "-c:v", "copy",
            "-disposition:v:0", "attached_pic",
        ]
    tmp = path.with_name(f"{path.stem}.loudnorm{path.suffix}")
    proc = _run_ffmpeg(
        [
            "-y", "-i", str(path), "-af", filt,
            "-ar", _sample_rate(path), "-map_metadata", "0",
            *cover_args, *encoder, *bitrate_args, str(tmp),
        ]
    )
    if proc is None or proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        logger.warning("loudnorm: re-encode failed for %s", path.name)
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(path)
    return True
