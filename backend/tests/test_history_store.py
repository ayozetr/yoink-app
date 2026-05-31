"""Tests for the SQLite history store (against a temp DB)."""

from __future__ import annotations

from app.services import history_store


def _add(**kw):
    base = dict(title="t", url="http://x", kind="video", status="completed")
    base.update(kw)
    return history_store.add_entry(**base)


def test_add_list_order_and_get(history_db):
    first = _add(title="first")
    second = _add(title="second")

    entries = history_store.list_entries()
    assert [e.title for e in entries] == ["second", "first"]  # newest first
    assert entries[0].id == second.id
    assert history_store.get_entry(first.id).title == "first"
    assert history_store.get_entry(99999) is None


def test_stats_counts_only_completed(history_db):
    _add(status="completed", filesize=1000)
    _add(status="completed", filesize=500)
    _add(status="error")  # ignored by stats

    stats = history_store.get_stats()
    assert stats.total_downloads == 2
    assert stats.total_bytes == 1500
    assert stats.transferred == "1.5 KB"


def test_clear(history_db):
    _add()
    _add()
    removed = history_store.clear()
    assert removed == 2
    assert history_store.list_entries() == []
    assert history_store.get_stats().total_downloads == 0
