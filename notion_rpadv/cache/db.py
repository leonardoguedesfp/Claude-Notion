"""SQLite local cache for Notion data. Schema and CRUD operations."""
from __future__ import annotations

import contextlib
import json
import pathlib
import sqlite3
import time
from typing import Any, Generator

DB_VERSION = 1


def get_conn(path: pathlib.Path | None = None) -> sqlite3.Connection:
    """Return a sqlite3.Connection.  If *path* is None the in-memory DB is used."""
    from notion_bulk_edit.config import get_cache_db_path  # lazy import

    resolved = path if path is not None else get_cache_db_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and run migrations if needed."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS records (
            base       TEXT NOT NULL,
            page_id    TEXT NOT NULL,
            data_json  TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (base, page_id)
        );

        CREATE TABLE IF NOT EXISTS pending_edits (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            base       TEXT    NOT NULL,
            page_id    TEXT    NOT NULL,
            key        TEXT    NOT NULL,
            old_value  TEXT    NOT NULL,
            new_value  TEXT    NOT NULL,
            created_at REAL    NOT NULL,
            status     TEXT    NOT NULL DEFAULT 'pending'
        );

        CREATE TABLE IF NOT EXISTS edit_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            base       TEXT    NOT NULL,
            page_id    TEXT    NOT NULL,
            key        TEXT    NOT NULL,
            old_value  TEXT    NOT NULL,
            new_value  TEXT    NOT NULL,
            applied_at REAL    NOT NULL,
            user       TEXT    NOT NULL,
            reverted   INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    # Store / check schema version.
    row = conn.execute("SELECT value FROM meta WHERE key='db_version'").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('db_version', ?)",
            (str(DB_VERSION),),
        )
        conn.commit()


@contextlib.contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that commits on success and rolls back on error."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def upsert_record(
    conn: sqlite3.Connection,
    base: str,
    page_id: str,
    data: dict[str, Any],
) -> None:
    """Insert or replace a decoded record."""
    now = time.time()
    data_json = json.dumps(data, ensure_ascii=False, default=str)
    conn.execute(
        """
        INSERT INTO records (base, page_id, data_json, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(base, page_id) DO UPDATE SET
            data_json  = excluded.data_json,
            updated_at = excluded.updated_at
        """,
        (base, page_id, data_json, now),
    )


def delete_record(conn: sqlite3.Connection, base: str, page_id: str) -> None:
    """Remove a record from the local cache."""
    conn.execute(
        "DELETE FROM records WHERE base=? AND page_id=?",
        (base, page_id),
    )


def get_all_records(conn: sqlite3.Connection, base: str) -> list[dict[str, Any]]:
    """Return all cached records for *base* as plain dicts."""
    rows = conn.execute(
        "SELECT data_json FROM records WHERE base=? ORDER BY updated_at DESC",
        (base,),
    ).fetchall()
    return [json.loads(row["data_json"]) for row in rows]


def get_record(
    conn: sqlite3.Connection, base: str, page_id: str
) -> dict[str, Any] | None:
    """Return a single cached record or None."""
    row = conn.execute(
        "SELECT data_json FROM records WHERE base=? AND page_id=?",
        (base, page_id),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["data_json"])  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Sync timestamps
# ---------------------------------------------------------------------------


def get_last_sync(conn: sqlite3.Connection, base: str) -> float:
    """Return the UNIX timestamp of the last successful sync, or 0.0."""
    row = conn.execute(
        "SELECT value FROM meta WHERE key=?",
        (f"last_sync_{base}",),
    ).fetchone()
    if row is None:
        return 0.0
    try:
        return float(row["value"])
    except (TypeError, ValueError):
        return 0.0


def set_last_sync(conn: sqlite3.Connection, base: str, ts: float) -> None:
    """Persist the last-sync timestamp for *base*."""
    conn.execute(
        """
        INSERT INTO meta(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (f"last_sync_{base}", str(ts)),
    )
    conn.commit()


def is_stale(conn: sqlite3.Connection, base: str, stale_hours: float) -> bool:
    """Return True if the cache for *base* exists but is older than *stale_hours*.

    Returns False when never synced — use is_never_synced() for that check.
    """
    last = get_last_sync(conn, base)
    if last == 0.0:
        # BUG-23: never synced is not the same as "stale"; handle separately
        return False
    age_hours = (time.time() - last) / 3600.0
    return age_hours > stale_hours


def is_never_synced(conn: sqlite3.Connection, base: str) -> bool:
    """Return True if *base* has never been synced (no timestamp recorded)."""
    return get_last_sync(conn, base) == 0.0


# ---------------------------------------------------------------------------
# Pending edits
# ---------------------------------------------------------------------------


def add_pending_edit(
    conn: sqlite3.Connection,
    base: str,
    page_id: str,
    key: str,
    old_value: Any,
    new_value: Any,
) -> int:
    """Queue an edit and return its auto-generated id."""
    now = time.time()
    old_json = json.dumps(old_value, ensure_ascii=False, default=str)
    new_json = json.dumps(new_value, ensure_ascii=False, default=str)
    cursor = conn.execute(
        """
        INSERT INTO pending_edits (base, page_id, key, old_value, new_value, created_at, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """,
        (base, page_id, key, old_json, new_json, now),
    )
    conn.commit()
    return int(cursor.lastrowid)  # type: ignore[arg-type]


def get_pending_edits(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all pending edits as plain dicts."""
    rows = conn.execute(
        "SELECT * FROM pending_edits WHERE status='pending' ORDER BY created_at"
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["old_value"] = json.loads(d["old_value"])
        d["new_value"] = json.loads(d["new_value"])
        result.append(d)
    return result


def mark_edit_applied(
    conn: sqlite3.Connection, edit_id: int, user: str
) -> None:
    """Move a pending edit to edit_log and mark it applied."""
    row = conn.execute(
        "SELECT * FROM pending_edits WHERE id=?", (edit_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"No pending edit with id={edit_id}")

    now = time.time()
    conn.execute(
        """
        INSERT INTO edit_log (base, page_id, key, old_value, new_value, applied_at, user, reverted)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            row["base"],
            row["page_id"],
            row["key"],
            row["old_value"],
            row["new_value"],
            now,
            user,
        ),
    )
    conn.execute(
        "UPDATE pending_edits SET status='applied' WHERE id=?", (edit_id,)
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Edit log
# ---------------------------------------------------------------------------


def get_edit_log(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    """Return the most recent *limit* log entries as plain dicts."""
    rows = conn.execute(
        "SELECT * FROM edit_log ORDER BY applied_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["old_value"] = json.loads(d["old_value"])
        d["new_value"] = json.loads(d["new_value"])
        result.append(d)
    return result


def get_log_entry(conn: sqlite3.Connection, log_id: int) -> dict[str, Any] | None:
    """Return a single edit_log entry without modifying it, or None if missing."""
    row = conn.execute(
        "SELECT * FROM edit_log WHERE id=?", (log_id,)
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["old_value"] = json.loads(d["old_value"])
    d["new_value"] = json.loads(d["new_value"])
    return d


def revert_edit(conn: sqlite3.Connection, log_id: int) -> dict[str, Any]:
    """Mark log entry as reverted and return it so the caller can apply old_value back."""
    row = conn.execute(
        "SELECT * FROM edit_log WHERE id=?", (log_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"No log entry with id={log_id}")

    d = dict(row)
    d["old_value"] = json.loads(d["old_value"])
    d["new_value"] = json.loads(d["new_value"])

    conn.execute(
        "UPDATE edit_log SET reverted=1 WHERE id=?", (log_id,)
    )
    conn.commit()
    return d
