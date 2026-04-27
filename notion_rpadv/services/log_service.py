"""Service for reading the edit log and triggering reversions."""
from __future__ import annotations

import sqlite3
from typing import Any

from notion_rpadv.cache import db as cache_db


def get_log_entries(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    """Return the most recent *limit* edit-log entries as plain dicts.

    Each dict has the following keys (matching the edit_log table):
        id, base, page_id, key, old_value, new_value,
        applied_at (float UNIX timestamp), user (str), reverted (bool int).

    old_value and new_value are already decoded from JSON by cache_db.get_edit_log.
    """
    return cache_db.get_edit_log(conn, limit=limit)


def get_pending_count(conn: sqlite3.Connection) -> int:
    """Return the number of edits currently in status='pending'."""
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM pending_edits WHERE status='pending'"
    ).fetchone()
    if row is None:
        return 0
    return int(row["cnt"])


def get_log_entry(conn: sqlite3.Connection, log_id: int) -> dict[str, Any] | None:
    """Return a single log entry by its *log_id*, or None if not found."""
    entries = get_log_entries(conn, limit=10_000)
    for entry in entries:
        if entry.get("id") == log_id:
            return entry
    return None


def get_log_entries_for_page(
    conn: sqlite3.Connection, base: str, page_id: str, limit: int = 100
) -> list[dict[str, Any]]:
    """Return log entries filtered to a specific page, newest-first."""
    all_entries = cache_db.get_edit_log(conn, limit=10_000)
    matching = [
        e for e in all_entries if e.get("base") == base and e.get("page_id") == page_id
    ]
    return matching[:limit]


def get_log_entries_by_user(
    conn: sqlite3.Connection, user: str, limit: int = 200
) -> list[dict[str, Any]]:
    """Return log entries filtered by *user*, newest-first."""
    all_entries = cache_db.get_edit_log(conn, limit=10_000)
    matching = [e for e in all_entries if e.get("user") == user]
    return matching[:limit]


def get_log_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return aggregate statistics about the edit log.

    Returns a dict with::
        total_applied: int
        total_reverted: int
        pending: int
        by_base: dict[str, int]   # base -> count of applied edits
        by_user: dict[str, int]   # user -> count of applied edits
    """
    all_entries = cache_db.get_edit_log(conn, limit=100_000)
    total_applied = len(all_entries)
    total_reverted = sum(1 for e in all_entries if e.get("reverted"))
    pending = get_pending_count(conn)

    by_base: dict[str, int] = {}
    by_user: dict[str, int] = {}
    for entry in all_entries:
        base = str(entry.get("base", ""))
        user = str(entry.get("user", ""))
        by_base[base] = by_base.get(base, 0) + 1
        by_user[user] = by_user.get(user, 0) + 1

    return {
        "total_applied": total_applied,
        "total_reverted": total_reverted,
        "pending": pending,
        "by_base": by_base,
        "by_user": by_user,
    }
