"""SQLite-backed persistence for the download history.

Uses the stdlib ``sqlite3`` (no extra dependency). A fresh connection is opened
per operation so the store is safe to call from background threads / the event
loop without sharing a connection across threads.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from app.core.config import settings
from app.core.humanize import humanize_bytes
from app.models.media import HistoryEntry, HistoryStats, HistoryStatus, MediaKind

_SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    title     TEXT    NOT NULL,
    url       TEXT    NOT NULL,
    kind      TEXT    NOT NULL,
    status    TEXT    NOT NULL,
    filename  TEXT,
    filepath  TEXT,
    filesize  INTEGER,
    quality   TEXT,
    created_at TEXT   NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    settings.ensure_data_dir()
    # timeout is the busy-timeout: wait for a held lock instead of erroring with
    # "database is locked". The persistent queue can fire several completions in
    # quick succession, so a short wait beats a lost history row.
    connection = sqlite3.connect(settings.db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def _add_column_if_missing(
    connection: sqlite3.Connection, table: str, column: str, coltype: str
) -> None:
    """Add a column to an existing table only if it isn't there yet (migration)."""
    cols = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


# Ordered schema migrations. Each step upgrades the DB *to* its 1-based index;
# on startup every step past the DB's `user_version` runs in order, then the
# version is bumped. Append-only — never edit or reorder a shipped step. Steps
# must be idempotent (they may re-run on a DB whose version wasn't recorded).
def _v1_base_table(connection: sqlite3.Connection) -> None:
    connection.execute(_SCHEMA)


def _v2_extra_columns(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(connection, "downloads", "quality", "TEXT")
    _add_column_if_missing(connection, "downloads", "error_message", "TEXT")


_MIGRATIONS = [_v1_base_table, _v2_extra_columns]


def init_db() -> None:
    """Create / migrate the history DB, tracked by ``PRAGMA user_version``."""
    with closing(_connect()) as connection, connection:
        # WAL lets a reader and a writer coexist (the queue writes bursts of
        # history rows); it's a persistent DB property, set once here.
        connection.execute("PRAGMA journal_mode=WAL")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        # Pre-versioning DBs report 0, so every (idempotent) step re-runs and
        # brings them up to date without touching existing rows.
        for target, migrate in enumerate(_MIGRATIONS[version:], start=version + 1):
            migrate(connection)
            connection.execute(f"PRAGMA user_version = {target}")


def _row_to_entry(row: sqlite3.Row) -> HistoryEntry:
    # The file's mtime bumps when auto-tagging rewrites it, so the UI can refetch
    # only that row's cover instead of busting every cover on each refresh.
    mtime: float | None = None
    if row["filepath"]:
        try:
            mtime = os.stat(row["filepath"]).st_mtime
        except OSError:
            mtime = None
    return HistoryEntry(
        id=row["id"],
        title=row["title"],
        url=row["url"],
        kind=row["kind"],
        status=row["status"],
        filename=row["filename"],
        filepath=row["filepath"],
        filesize=row["filesize"],
        quality=row["quality"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        mtime=mtime,
    )


def add_entry(
    *,
    title: str,
    url: str,
    kind: MediaKind,
    status: HistoryStatus,
    filename: str | None = None,
    filepath: str | None = None,
    filesize: int | None = None,
    quality: str | None = None,
    error_message: str | None = None,
) -> HistoryEntry:
    """Insert a download record and return it (with its generated id)."""
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            """
            INSERT INTO downloads
                (title, url, kind, status, filename, filepath, filesize, quality,
                 error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, url, kind, status, filename, filepath, filesize, quality,
             error_message, created_at),
        )
        new_id = cursor.lastrowid
    return HistoryEntry(
        id=int(new_id) if new_id is not None else 0,
        title=title,
        url=url,
        kind=kind,
        status=status,
        filename=filename,
        filepath=filepath,
        filesize=filesize,
        quality=quality,
        error_message=error_message,
        created_at=created_at,
    )


def update_title(filepath: str, title: str) -> None:
    """Update the stored title for the most recent row with this file path.

    Used after auto-tagging so the history shows "Artist - Title". Targets only
    the latest matching row (by id) — re-downloading the same name produces a new
    row, and tagging one shouldn't relabel old, unrelated entries that reused the
    path.
    """
    with closing(_connect()) as connection, connection:
        connection.execute(
            "UPDATE downloads SET title = ? "
            "WHERE id = (SELECT MAX(id) FROM downloads WHERE filepath = ?)",
            (title, filepath),
        )


def list_entries(limit: int = 50) -> list[HistoryEntry]:
    """Return the most recent entries, newest first."""
    with closing(_connect()) as connection, connection:
        rows = connection.execute(
            "SELECT * FROM downloads ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_entry(row) for row in rows]


def completed_urls() -> set[str]:
    """Source URLs of every successfully-completed download — used to flag which
    playlist entries you already have, so re-analyzing a playlist only pre-selects
    what's new (playlist sync)."""
    with closing(_connect()) as connection, connection:
        rows = connection.execute(
            "SELECT DISTINCT url FROM downloads WHERE status = 'completed'"
        ).fetchall()
    return {row["url"] for row in rows}


def get_entry(entry_id: int) -> HistoryEntry | None:
    """Return a single entry by id, or None."""
    with closing(_connect()) as connection, connection:
        row = connection.execute(
            "SELECT * FROM downloads WHERE id = ?", (entry_id,)
        ).fetchone()
    return _row_to_entry(row) if row else None


def clear() -> int:
    """Delete all history records; returns the number removed."""
    with closing(_connect()) as connection, connection:
        cursor = connection.execute("DELETE FROM downloads")
        return cursor.rowcount


def get_stats() -> HistoryStats:
    """Aggregate count and total bytes across successful downloads."""
    with closing(_connect()) as connection, connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count, COALESCE(SUM(filesize), 0) AS total
            FROM downloads
            WHERE status = 'completed'
            """
        ).fetchone()
    total_bytes = int(row["total"]) if row else 0
    return HistoryStats(
        total_downloads=int(row["count"]) if row else 0,
        total_bytes=total_bytes,
        transferred=humanize_bytes(total_bytes),
    )
