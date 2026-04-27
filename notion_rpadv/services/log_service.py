"""Service for reading the edit log and triggering reversions."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from notion_rpadv.cache import db as cache_db


def get_log_entries(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    """Return the most recent *limit* edit-log entries as plain dicts."""
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
    """BUG-N13: fetch by id directly — no full-table scan."""
    return cache_db.get_log_entry(conn, log_id)


def get_log_entries_for_page(
    conn: sqlite3.Connection, base: str, page_id: str, limit: int = 100
) -> list[dict[str, Any]]:
    """BUG-N13: SQL-filtered query instead of loading 10k rows into memory."""
    rows = conn.execute(
        """
        SELECT * FROM edit_log
        WHERE base=? AND page_id=?
        ORDER BY applied_at DESC LIMIT ?
        """,
        (base, page_id, limit),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["old_value"] = json.loads(d["old_value"])
        d["new_value"] = json.loads(d["new_value"])
        result.append(d)
    return result


def get_log_entries_by_user(
    conn: sqlite3.Connection, user: str, limit: int = 200
) -> list[dict[str, Any]]:
    """BUG-N13: SQL-filtered query instead of loading 10k rows into memory."""
    rows = conn.execute(
        """
        SELECT * FROM edit_log
        WHERE user=?
        ORDER BY applied_at DESC LIMIT ?
        """,
        (user, limit),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["old_value"] = json.loads(d["old_value"])
        d["new_value"] = json.loads(d["new_value"])
        result.append(d)
    return result


def get_log_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """BUG-N13: SQL aggregates instead of loading 100k rows into Python."""
    row = conn.execute(
        "SELECT COUNT(*) AS total, SUM(reverted) AS reverted FROM edit_log"
    ).fetchone()
    total_applied = int(row["total"]) if row else 0
    total_reverted = int(row["reverted"] or 0) if row else 0
    pending = get_pending_count(conn)

    by_base_rows = conn.execute(
        "SELECT base, COUNT(*) AS cnt FROM edit_log GROUP BY base"
    ).fetchall()
    by_base = {r["base"]: int(r["cnt"]) for r in by_base_rows}

    by_user_rows = conn.execute(
        "SELECT user, COUNT(*) AS cnt FROM edit_log GROUP BY user"
    ).fetchall()
    by_user = {r["user"]: int(r["cnt"]) for r in by_user_rows}

    return {
        "total_applied": total_applied,
        "total_reverted": total_reverted,
        "pending": pending,
        "by_base": by_base,
        "by_user": by_user,
    }
