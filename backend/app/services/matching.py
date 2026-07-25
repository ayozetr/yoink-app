"""YouTube match-ranking for Spotify tracks — a port of spotDL's algorithm.

spotDL (MIT) sources Spotify songs from YouTube. We reuse its *scoring* idea —
no spotDL dependency, no Spotify API: score yt-dlp ``ytsearch`` candidates
against a music track on fuzzy name/artist similarity + a duration penalty,
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


# Symbol/currency glyphs artists stylize letters with (Cruz Cafuné's "rang€ rov€r",
# "A$AP", "Ke$ha") — folded to their letter so the slug matches a plain title.
_LOOKALIKES = str.maketrans({
    "€": "e", "$": "s", "@": "a", "£": "l", "¥": "y", "ø": "o", "ł": "l", "đ": "d",
})


def _slug(text: str) -> str:
    """Lowercase, de-accented, alphanumeric-only token string for comparison."""
    text = _strip_accents(text.translate(_LOOKALIKES)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _token_set_ratio(a: str, b: str) -> float:
    """fuzzywuzzy-style token-set ratio (0–1): robust to extra words on one side.

    The crucial property: when one string's tokens are a subset of the other's,
    the score is ~1.0 — so a bare track title ("despechá") still matches a noisy
    YouTube title ("ROSALÍA - DESPECHÁ (Official Video)") that merely surrounds it
    with the artist + "(Official Video)" boilerplate.
    """
    t1, t2 = set(a.split()), set(b.split())
    if not t1 or not t2:
        return 0.0
    inter = " ".join(sorted(t1 & t2))
    combined1 = (inter + " " + " ".join(sorted(t1 - t2))).strip()
    combined2 = (inter + " " + " ".join(sorted(t2 - t1))).strip()
    return max(
        SequenceMatcher(None, inter, combined1).ratio(),
        SequenceMatcher(None, inter, combined2).ratio(),
        SequenceMatcher(None, combined1, combined2).ratio(),
    )


def _ratio(a: str, b: str) -> float:
    """Fuzzy similarity 0–100: max of direct, token-sorted, and token-set ratios."""
    if not a or not b:
        return 0.0
    direct = SequenceMatcher(None, a, b).ratio()
    sorted_a = " ".join(sorted(a.split()))
    sorted_b = " ".join(sorted(b.split()))
    token = SequenceMatcher(None, sorted_a, sorted_b).ratio()
    return max(direct, token, _token_set_ratio(a, b)) * 100


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
    # Drop the "(feat. X)" credit from the song name — it isn't part of the title
    # and, when a *different* song shares the same featured artist, the common
    # "feat X" tokens would otherwise inflate the similarity into a false match.
    t = _slug(_FEAT_RE.sub("", track_title))
    c = _slug(cand_title)
    best = _ratio(t, c)
    # YouTube titles are often "Artist - Title (…)" — compare against the tail too.
    if " - " in cand_title:
        best = max(best, _ratio(t, _slug(cand_title.split(" - ", 1)[1])))
    penalty = _forbidden_penalty(c, t)
    return max(0.0, best - penalty)


# "feat. X" / "ft. X" / "featuring X" — a *secondary* artist that the source
# tacks onto the main credit but the YouTube channel/title usually omits, so it
# only drags the coverage down. Drop it before matching.
_FEAT_RE = re.compile(r"\s*[\(\[]?\s*\b(?:feat\.?|ft\.?|featuring)\s.+$", re.IGNORECASE)
# Credit separators between collaborating artists ("A, B & C" / "A x B").
_ARTIST_SPLIT_RE = re.compile(r"\s*(?:,|&|/|\bx\b)\s*", re.IGNORECASE)


def _coverage(artist_slug: str, cand_tokens: set[str]) -> float:
    """Share of an artist's tokens that appear in the candidate (0–100)."""
    tokens = artist_slug.split()
    if not tokens:
        return 0.0
    return 100.0 * sum(1 for tok in tokens if tok in cand_tokens) / len(tokens)


def artist_match(track_artists: str, cand_title: str, cand_channel: str) -> float:
    """How well the track's artists appear in the candidate's channel + title.

    A YouTube upload of a collab usually credits only the *primary* artist
    ("HUNTR/X - Golden" for a 5-name Spotify credit), so requiring every listed
    artist's tokens sinks valid matches. Score the full credit AND the lead
    artist alone, and take the best (plus a direct channel ratio floor).
    """
    cleaned = _FEAT_RE.sub("", track_artists)
    artist_slug = _slug(cleaned)
    if not artist_slug:
        return 0.0
    cand_tokens = set(_slug(f"{cand_channel} {cand_title}").split())
    primary_slug = _slug(_ARTIST_SPLIT_RE.split(cleaned, maxsplit=1)[0])
    # Artist-branded channels run the name together ("ElAlfaElJefeTV", "DrakeVEVO"),
    # so the tokens don't line up — but the de-spaced artist is a substring of the
    # de-spaced channel. Guard on length (>=5) so short names don't match by chance.
    channel_blob = _slug(cand_channel).replace(" ", "")
    for variant in (artist_slug, primary_slug):
        despaced = variant.replace(" ", "")
        if len(despaced) >= 5 and despaced in channel_blob:
            return 100.0
    return max(
        _coverage(artist_slug, cand_tokens),
        _coverage(primary_slug, cand_tokens),
        _ratio(artist_slug, _slug(cand_channel)),
    )


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

    # A near-exact name+artist hit shouldn't be rejected over a length gap — an
    # official video adds a 25–40s intro/outro, an edit a "ft." tag. The stronger
    # name+artist are, the less duration should gate (it still ranks closer hits
    # higher via the score, and forbidden words already filter live/remix cuts).
    # A grossly wrong length still scores ~0, so even the loosest tier rejects it.
    if nm >= 90 and am >= 90:
        min_time = 0.5  # ~50s tolerance — same song, different cut
    elif nm >= 85 and am >= 85:
        min_time = 10.0
    else:
        min_time = _MIN_TIME
    if nm < _MIN_NAME or am < _MIN_ARTIST or tm < min_time:
        return None

    avg = (nm + am) / 2
    # Fold in duration closeness only when the source track actually has a duration
    # to compare against. When it doesn't (e.g. Amazon embeds carry none), time_match
    # returns a neutral 100 for *every* candidate, so folding it in just adds a flat
    # +50 that inflates the score without telling candidates apart. Skipping it keeps
    # the exact same pick (tm is constant across candidates, so it can't reorder them)
    # while reporting an honest score. Tracks that do carry a duration are unchanged.
    if track_secs is not None:
        avg = (avg + tm) / 2
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
