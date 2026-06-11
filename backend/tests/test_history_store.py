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


def test_update_title_by_filepath(history_db):
    entry = _add(title="Raw Name | VIDEO", kind="audio", filepath="/dl/song.mp3")
    history_store.update_title("/dl/song.mp3", "Artist - Song")
    assert history_store.get_entry(entry.id).title == "Artist - Song"
    # No row matches → silent no-op.
    history_store.update_title("/dl/missing.mp3", "Nope")


def test_update_title_only_touches_latest_row(history_db):
    # Re-downloading the same name makes a new row; tagging one must not relabel
    # the older, unrelated entry that reused the path.
    old = _add(title="old entry", kind="audio", filepath="/dl/song.mp3")
    new = _add(title="raw name", kind="audio", filepath="/dl/song.mp3")
    history_store.update_title("/dl/song.mp3", "Artist - Title")
    assert history_store.get_entry(new.id).title == "Artist - Title"
    assert history_store.get_entry(old.id).title == "old entry"  # untouched


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


def test_quality_is_stored(history_db):
    entry = _add(title="vid", kind="video", quality="1080p")
    assert history_store.get_entry(entry.id).quality == "1080p"


def test_migration_adds_quality_column_to_old_db(temp_dirs):
    import sqlite3

    from app.core.config import settings

    settings.ensure_data_dir()
    conn = sqlite3.connect(settings.db_path)
    conn.execute(
        "CREATE TABLE downloads (id INTEGER PRIMARY KEY, title TEXT, url TEXT, "
        "kind TEXT, status TEXT, filename TEXT, filepath TEXT, filesize INTEGER, "
        "created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO downloads (title, url, kind, status, created_at) "
        "VALUES ('old', 'u', 'video', 'completed', '2026')"
    )
    conn.commit()
    conn.close()

    history_store.init_db()  # idempotent migration adds the new column
    entry = history_store.list_entries()[0]
    assert entry.title == "old" and entry.quality is None
