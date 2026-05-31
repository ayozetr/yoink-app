"""SQLite-backed persistence for the download history.

Uses the stdlib ``sqlite3`` (no extra dependency). A fresh connection is opened
per operation so the store is safe to call from background threads / the event
loop without sharing a connection across threads.
"""

from __future__ import annotations

import sqlite3
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
    created_at TEXT   NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    settings.ensure_data_dir()
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    """Create the history table if it does not exist yet."""
    with _connect() as connection:
        connection.execute(_SCHEMA)


def _row_to_entry(row: sqlite3.Row) -> HistoryEntry:
    return HistoryEntry(
        id=row["id"],
        title=row["title"],
        url=row["url"],
        kind=row["kind"],
        status=row["status"],
        filename=row["filename"],
        filepath=row["filepath"],
        filesize=row["filesize"],
        created_at=row["created_at"],
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
) -> HistoryEntry:
    """Insert a download record and return it (with its generated id)."""
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO downloads
                (title, url, kind, status, filename, filepath, filesize, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, url, kind, status, filename, filepath, filesize, created_at),
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
        created_at=created_at,
    )


def list_entries(limit: int = 50) -> list[HistoryEntry]:
    """Return the most recent entries, newest first."""
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM downloads ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_entry(row) for row in rows]


def get_entry(entry_id: int) -> HistoryEntry | None:
    """Return a single entry by id, or None."""
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM downloads WHERE id = ?", (entry_id,)
        ).fetchone()
    return _row_to_entry(row) if row else None


def clear() -> int:
    """Delete all history records; returns the number removed."""
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM downloads")
        return cursor.rowcount


def get_stats() -> HistoryStats:
    """Aggregate count and total bytes across successful downloads."""
    with _connect() as connection:
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
