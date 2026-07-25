"""Tests for the spotDL-ported YouTube match ranking (pure, no network)."""

from __future__ import annotations

from app.services.matching import (
    artist_match,
    best_match,
    name_match,
    score,
    time_match,
)


def _track(**kw):
    base = dict(track_title="Never Gonna Give You Up", track_artists="Rick Astley",
                track_duration_ms=213573)
    base.update(kw)
    return base


def test_picks_official_over_live_and_remix():
    cands = [
        {"title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
         "channel": "Rick Astley", "duration": 213, "url": "good"},
        {"title": "Never Gonna Give You Up (Live at Wembley)",
         "channel": "Rick Astley", "duration": 240, "url": "live"},
        {"title": "Never Gonna Give You Up - Lo-Fi Remix",
         "channel": "SomeDJ", "duration": 200, "url": "remix"},
    ]
    best = best_match(**_track(), candidates=cands)
    assert best is not None and best["url"] == "good"
    assert best["match_score"] > 70


def test_forbidden_word_penalises_unless_asked_for():
    # A "(Live)" with identical name+duration isn't hard-rejected, but the
    # forbidden word costs it points, so the studio cut outranks it.
    official = score(**_track(), cand={"title": "Never Gonna Give You Up",
                                       "channel": "Rick Astley", "duration": 213})
    live = score(**_track(), cand={"title": "Never Gonna Give You Up (Live)",
                                   "channel": "Rick Astley", "duration": 213})
    assert official is not None and live is not None
    assert official > live
    # …but if the track itself is the remix, the remix result is NOT penalised out.
    s = score(track_title="Dracula - JENNIE Remix", track_artists="Tame Impala, JENNIE",
              track_duration_ms=209720,
              cand={"title": "Tame Impala, JENNIE - Dracula (JENNIE Remix)",
                    "channel": "Tame Impala", "duration": 209})
    assert s is not None and s > 80


def test_unrelated_candidate_is_rejected():
    assert score(**_track(), cand={"title": "Completely Unrelated Song",
                                   "channel": "Nobody", "duration": 200}) is None


def test_duration_far_off_lowers_or_rejects():
    near = score(**_track(), cand={"title": "Never Gonna Give You Up",
                                   "channel": "Rick Astley", "duration": 213})
    far = score(**_track(), cand={"title": "Never Gonna Give You Up",
                                  "channel": "Rick Astley", "duration": 600})
    assert near is not None
    # 6+ minutes vs 3:33 → time_match collapses → rejected or far lower.
    assert far is None or far < near


def test_unknown_source_duration_keeps_the_pick():
    # A no-duration source (Amazon-style) must still pick the same candidate the
    # scorer would have — duration is a neutral constant across all candidates, so
    # it can't reorder them. This guards the change that stops the neutral 100 from
    # inflating the score.
    t = dict(track_title="Never Gonna Give You Up", track_artists="Rick Astley",
             track_duration_ms=None)
    cands = [
        {"title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
         "channel": "Rick Astley", "duration": 213, "url": "good"},
        {"title": "Never Gonna Give You Up - Lo-Fi Remix",
         "channel": "SomeDJ", "duration": 200, "url": "remix"},
    ]
    best = best_match(**t, candidates=cands)
    assert best is not None and best["url"] == "good"


def test_unknown_source_duration_is_not_inflated():
    # Without a source duration the score is a plain name/artist average, not lifted
    # by a flat +50 floor (the old `(nm+am)/4 + 50`).
    t = dict(track_title="Despechá", track_artists="ROSALÍA", track_duration_ms=None)
    cand = {"title": "ROSALÍA - DESPECHÁ (Official Video)", "channel": "ROSALÍA",
            "duration": 165}
    nm = name_match(t["track_title"], cand["title"])
    am = artist_match(t["track_artists"], cand["title"], cand["channel"])
    s = score(**t, cand=cand)
    assert s is not None
    assert abs(s - (nm + am) / 2) < 0.6            # honest average
    assert nm + am >= 199 or s < (nm + am) / 4 + 50  # strictly below the old floor
    # A track *with* a duration is unchanged (duration still folded in).
    with_dur = score(track_title="Despechá", track_artists="ROSALÍA",
                     track_duration_ms=165000, cand=cand)
    assert with_dur is not None and abs(with_dur - (( (nm + am) / 2 ) + 100) / 2) < 0.6


def test_time_match_curve():
    assert time_match(200, 200) == 100.0
    assert time_match(200, 205) < 100.0
    assert time_match(200, None) == 100.0  # unknown → neutral


def test_no_candidates_or_all_rejected_returns_none():
    assert best_match(**_track(), candidates=[]) is None
    assert best_match(**_track(), candidates=[
        {"title": "x", "channel": "y", "duration": 999}]) is None


def test_name_match_handles_accents_and_order():
    # de-accented + order-insensitive
    assert name_match("QUÉ CRUEL", "que cruel") > 90
    assert name_match("Tití Me Preguntó", "Preguntó Me Tití") > 60


def test_name_match_ignores_surrounding_youtube_noise():
    # The real failure mode: a bare track title vs a noisy YouTube title that
    # wraps it in "Artist - … (Official Video)". The token-set ratio must keep
    # the score high (these were wrongly skipped before).
    assert name_match("Despechá", "ROSALÍA - DESPECHÁ (Official Video)") >= 90
    assert name_match("Beggin'", "Måneskin - Beggin' (Lyrics/Testo)") >= 90
    assert name_match("Calm Down", "Rema, Selena Gomez - Calm Down (Official Music Video)") >= 90
    # …but an unrelated longer title still doesn't get a free pass.
    assert name_match("Calm Down", "Imagine Dragons - Thunder (Official Video)") < 60
