"""Tests for the spotDL-ported YouTube match ranking (pure, no network)."""

from __future__ import annotations

from app.services.matching import best_match, name_match, score, time_match


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
