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


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-nostdin", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _measure(path: Path) -> dict[str, str] | None:
    """First pass: analyze loudness; returns loudnorm's measured JSON values."""
    filt = (
        f"loudnorm=I={_TARGET_I}:TP={_TARGET_TP}:LRA={_TARGET_LRA}:print_format=json"
    )
    proc = _run_ffmpeg(["-i", str(path), "-af", filt, "-f", "null", "-"])
    match = re.search(r"\{[^{}]+\}", proc.stderr)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _sample_rate(path: Path) -> str:
    """The audio's sample rate (Hz), so the re-encode preserves it instead of
    leaving loudnorm's internal 192 kHz. Falls back to 44100."""
    proc = subprocess.run(
        [
            ffprobe_path(), "-v", "quiet", "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate", "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    rate = proc.stdout.strip()
    return rate if rate.isdigit() else "44100"


def normalize(path: Path, audio_format: str, bitrate: str = "best") -> bool:
    """Two-pass loudness-normalize ``path`` in place to -14 LUFS.

    Best-effort: on any measurement/encode failure it leaves the original file
    untouched and returns ``False``, so a normalization hiccup never loses a
    finished download.
    """
    encoder = _ENCODERS.get(audio_format)
    if encoder is None:
        return False
    measured = _measure(path)
    if measured is None:
        logger.warning("loudnorm: could not measure %s", path.name)
        return False
    filt = (
        f"loudnorm=I={_TARGET_I}:TP={_TARGET_TP}:LRA={_TARGET_LRA}"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true"
    )
    bitrate_args: list[str] = []
    if audio_format in _BEST_BITRATE:
        chosen = _BEST_BITRATE[audio_format] if bitrate == "best" else bitrate
        bitrate_args = ["-b:a", f"{chosen}k"]
    tmp = path.with_name(f"{path.stem}.loudnorm{path.suffix}")
    proc = _run_ffmpeg(
        [
            "-y", "-i", str(path), "-af", filt,
            "-ar", _sample_rate(path), "-map_metadata", "0",
            *encoder, *bitrate_args, str(tmp),
        ]
    )
    if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        logger.warning("loudnorm: re-encode failed for %s", path.name)
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(path)
    return True
