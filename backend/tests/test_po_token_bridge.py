"""Tests for the PO-token WebView bridge broker."""

from __future__ import annotations

import threading
import time

import pytest

from app.services.po_token_bridge import broker

_RESULT = {"token": "MINTED-TOKEN", "visitor_data": "VDATA"}


@pytest.fixture(autouse=True)
def _clean_broker():
    broker._reset()
    yield
    broker._reset()


def test_submit_times_out_without_a_worker():
    start = time.monotonic()
    result = broker.submit_mint(timeout=0.2)
    assert result is None
    # It waited for (about) the timeout rather than returning instantly. Allow a
    # little slack: Windows' timer granularity can wake an Event.wait a hair early
    # (~0.19s for a 0.2s wait), which shouldn't fail the test.
    assert time.monotonic() - start >= 0.15


def test_next_job_returns_none_when_empty():
    assert broker.next_job(wait=0.1) is None


def test_has_active_poller_tracks_polling():
    # No WebView has polled yet → minting should be skipped.
    assert broker.has_active_poller() is False
    # A long-poll (even one that finds nothing) marks the WebView present.
    broker.next_job(wait=0.05)
    assert broker.has_active_poller() is True


def test_full_round_trip():
    result: dict[str, dict | None] = {}

    def requester():
        result["out"] = broker.submit_mint(timeout=2.0)

    t = threading.Thread(target=requester)
    t.start()

    # The worker (WebView) claims the job and fulfills it.
    job = broker.next_job(wait=1.0)
    assert job is not None
    assert "id" in job and "video_id" not in job
    assert broker.complete(job["id"], _RESULT) is True

    t.join(timeout=2.0)
    assert result["out"] == _RESULT


def test_next_job_marks_dispatched_so_it_isnt_claimed_twice():
    def requester():
        broker.submit_mint(timeout=1.0)

    threading.Thread(target=requester).start()
    first = broker.next_job(wait=1.0)
    assert first is not None
    # A second poll finds nothing (the only job is already dispatched).
    assert broker.next_job(wait=0.1) is None
    broker.complete(first["id"], _RESULT)


def test_complete_unknown_job_is_dropped():
    assert broker.complete("nonexistent", _RESULT) is False


def test_failure_result_yields_none():
    result: dict[str, dict | None] = {}

    def requester():
        result["out"] = broker.submit_mint(timeout=2.0)

    threading.Thread(target=requester).start()
    job = broker.next_job(wait=1.0)
    assert job is not None
    assert broker.complete(job["id"], None) is True  # WebView reported a failure
    time.sleep(0.05)
    assert result["out"] is None


def test_late_complete_after_timeout_is_harmless():
    result = broker.submit_mint(timeout=0.1)
    assert result is None
    # The job already timed out and was removed; a late completion is dropped.
    assert broker.next_job(wait=0.05) is None
