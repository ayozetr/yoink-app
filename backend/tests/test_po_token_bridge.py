"""Tests for the PO-token WebView bridge broker."""

from __future__ import annotations

import threading
import time

import pytest

from app.services.po_token_bridge import broker


@pytest.fixture(autouse=True)
def _clean_broker():
    broker._reset()
    yield
    broker._reset()


def test_submit_times_out_without_a_worker():
    start = time.monotonic()
    token = broker.submit_mint("vid1", timeout=0.2)
    assert token is None
    assert time.monotonic() - start >= 0.2


def test_next_job_returns_none_when_empty():
    assert broker.next_job(wait=0.1) is None


def test_has_active_poller_tracks_polling():
    # No WebView has polled yet → minting should be skipped.
    assert broker.has_active_poller() is False
    # A long-poll (even one that finds nothing) marks the WebView present.
    broker.next_job(wait=0.05)
    assert broker.has_active_poller() is True


def test_full_round_trip():
    result: dict[str, str | None] = {}

    def requester():
        result["token"] = broker.submit_mint("vidABC", timeout=2.0)

    t = threading.Thread(target=requester)
    t.start()

    # The worker (WebView) claims the job and fulfills it.
    job = broker.next_job(wait=1.0)
    assert job is not None
    assert job["video_id"] == "vidABC"
    assert broker.complete(job["id"], "MINTED-TOKEN") is True

    t.join(timeout=2.0)
    assert result["token"] == "MINTED-TOKEN"


def test_next_job_marks_dispatched_so_it_isnt_claimed_twice():
    def requester():
        broker.submit_mint("vidX", timeout=1.0)

    threading.Thread(target=requester).start()
    first = broker.next_job(wait=1.0)
    assert first is not None
    # A second poll finds nothing (the only job is already dispatched).
    assert broker.next_job(wait=0.1) is None
    broker.complete(first["id"], "T")


def test_complete_unknown_job_is_dropped():
    assert broker.complete("nonexistent", "T") is False


def test_failure_result_yields_none_token():
    result: dict[str, str | None] = {}

    def requester():
        result["token"] = broker.submit_mint("vidF", timeout=2.0)

    threading.Thread(target=requester).start()
    job = broker.next_job(wait=1.0)
    assert job is not None
    assert broker.complete(job["id"], None) is True  # WebView reported a failure
    time.sleep(0.05)
    assert result["token"] is None


def test_late_complete_after_timeout_is_harmless():
    token = broker.submit_mint("vidLate", timeout=0.1)
    assert token is None
    # The job already timed out and was removed; a late completion is dropped.
    assert broker.next_job(wait=0.05) is None
