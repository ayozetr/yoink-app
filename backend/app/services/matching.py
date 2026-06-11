"""YouTube match-ranking for Spotify tracks — a port of spotDL's algorithm.

spotDL (MIT) sources Spotify songs from YouTube. We reuse its *scoring* idea —
no spotDL dependency, no Spotify API: score yt-dlp ``ytmsearch`` candidates
against a Spotify track on fuzzy name/artist similarity + a duration penalty,
and filter the wrong *kind* (live/remix/cover…) with a forbidden-word list.

Pure functions, no network. ``best_match`` returns the highest-scoring candidate
that clears the accept thresholds, or ``None`` (caller falls back to the top
result / manual pick).
"""

from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

# A candidate the wording marks as a *different* recording than the album track —
# penalised when present in the result but not asked for by the Spotify title.
FORBIDDEN_WORDS = (
    "remix", "remastered", "live", "acoustic", "8d", "concert", "acapella",
    "slowed", "instrumental", "cover", "karaoke", "bassboost", "bass boost",
    "reverb", "sped up", "nightcore", "mashup", "tribute",
)

# Accept thresholds (spotDL's): below any of these, the candidate is rejected.
_MIN_NAME = 60.0
_MIN_ARTIST = 60.0
_MIN_TIME = 25.0


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _slug(text: str) -> str:
    """Lowercase, de-accented, alphanumeric-only token string for comparison."""
    text = _strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _ratio(a: str, b: str) -> float:
    """Fuzzy similarity 0–100, order-insensitive (token-sorted too)."""
    if not a or not b:
        return 0.0
    direct = SequenceMatcher(None, a, b).ratio()
    sorted_a = " ".join(sorted(a.split()))
    sorted_b = " ".join(sorted(b.split()))
    token = SequenceMatcher(None, sorted_a, sorted_b).ratio()
    return max(direct, token) * 100


def _forbidden_penalty(cand_title_slug: str, track_title_slug: str) -> float:
    """15 points per forbidden word the candidate has but the track didn't ask for."""
    penalty = 0.0
    for word in FORBIDDEN_WORDS:
        w = _slug(word)
        if w and w in cand_title_slug and w not in track_title_slug:
            penalty += 15.0
    return penalty


def name_match(track_title: str, cand_title: str) -> float:
    """Title similarity. Also tries the candidate's text after an 'Artist - ' prefix."""
    t = _slug(track_title)
    c = _slug(cand_title)
    best = _ratio(t, c)
    # YouTube titles are often "Artist - Title (…)" — compare against the tail too.
    if " - " in cand_title:
        best = max(best, _ratio(t, _slug(cand_title.split(" - ", 1)[1])))
    penalty = _forbidden_penalty(c, t)
    return max(0.0, best - penalty)


def artist_match(track_artists: str, cand_title: str, cand_channel: str) -> float:
    """How well the track's artists appear in the candidate's channel + title."""
    artist_slug = _slug(track_artists)
    if not artist_slug:
        return 0.0
    cand_text = _slug(f"{cand_channel} {cand_title}")
    cand_tokens = set(cand_text.split())
    artist_tokens = artist_slug.split()
    present = sum(1 for tok in artist_tokens if tok in cand_tokens)
    coverage = 100.0 * present / len(artist_tokens)
    # Floor with a direct ratio against the channel (often exactly the artist).
    return max(coverage, _ratio(artist_slug, _slug(cand_channel)))


def time_match(track_secs: float | None, cand_secs: float | None) -> float:
    """Duration closeness: exp(-0.1·|Δseconds|)·100. Neutral (100) if unknown."""
    if not track_secs or not cand_secs:
        return 100.0
    return math.exp(-0.1 * abs(track_secs - cand_secs)) * 100


def score(
    *,
    track_title: str,
    track_artists: str,
    track_duration_ms: int | None,
    cand: dict[str, Any],
) -> float | None:
    """Combined 0–100 score for one candidate, or None if it's rejected.

    ``cand`` is a yt-dlp flat search entry: ``title``, ``channel``/``uploader``,
    ``duration`` (seconds), ``url``.
    """
    cand_title = str(cand.get("title") or "")
    cand_channel = str(cand.get("channel") or cand.get("uploader") or "")
    nm = name_match(track_title, cand_title)
    am = artist_match(track_artists, cand_title, cand_channel)
    track_secs = (track_duration_ms / 1000) if track_duration_ms else None
    tm = time_match(track_secs, cand.get("duration"))

    if nm < _MIN_NAME or am < _MIN_ARTIST or tm < _MIN_TIME:
        return None

    avg = (nm + am) / 2
    avg = (avg + tm) / 2  # fold in duration closeness
    return min(avg, 100.0)


def best_match(
    *,
    track_title: str,
    track_artists: str,
    track_duration_ms: int | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """The highest-scoring candidate that clears the thresholds, or None."""
    scored: list[tuple[float, dict[str, Any]]] = []
    for cand in candidates:
        s = score(
            track_title=track_title,
            track_artists=track_artists,
            track_duration_ms=track_duration_ms,
            cand=cand,
        )
        if s is not None:
            scored.append((s, cand))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    best = dict(scored[0][1])
    best["match_score"] = round(scored[0][0], 1)
    return best
