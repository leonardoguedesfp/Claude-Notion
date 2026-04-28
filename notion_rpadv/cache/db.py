"""SQLite local cache for Notion data. Schema and CRUD operations.

BUG-OP-09: the cache and the audit log used to share a single SQLite file
(``cache.db``). This made the audit log collateral damage of any
"clear cache" workflow. Audit data now lives in a separate file
(``audit.db``) and the legacy combined database is auto-migrated on first
boot. The old ``init_db`` / ``get_conn`` helpers create both schemas to
preserve backward compatibility for in-memory tests that don't care about
the split.
"""
from __future__ import annotations

import contextlib
import json
import pathlib
import shutil
import sqlite3
import time
from typing import Any, Generator

DB_VERSION = 1
AUDIT_MIGRATION_KEY = "audit_migrated_v1"


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------


def _init_meta(conn: sqlite3.Connection) -> None:
    """Both schemas need a `meta` table; created idempotently."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta ("
        "  key   TEXT PRIMARY KEY,"
        "  value TEXT NOT NULL"
        ")"
    )
    row = conn.execute(
        "SELECT value FROM meta WHERE key='db_version'"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('db_version', ?)",
            (str(DB_VERSION),),
        )
    conn.commit()


def init_cache_db(conn: sqlite3.Connection) -> None:
    """BUG-OP-09: create only the cache-side tables (records + meta).

    Idempotent — safe to call against a connection that already has these
    tables. Audit tables are NOT created here.
    """
    _init_meta(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS records (
            base       TEXT NOT NULL,
            page_id    TEXT NOT NULL,
            data_json  TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (base, page_id)
        );
        """
    )
    conn.commit()


def init_audit_db(conn: sqlite3.Connection) -> None:
    """BUG-OP-09: create only the audit-side tables (pending_edits +
    edit_log + meta). Idempotent."""
    _init_meta(conn)
    conn.executescript(
        """
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
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    """Legacy initialiser: creates both cache and audit schemas in the
    same connection. Kept so:

    * Existing in-memory tests (and any caller still using the old
      single-conn ``get_conn``) continue to work without modification.
    * The migration helper below can read the legacy tables before they
      are dropped.

    Production code should prefer ``init_cache_db`` / ``init_audit_db``
    against separate files.
    """
    init_cache_db(conn)
    init_audit_db(conn)


def get_conn(path: pathlib.Path | None = None) -> sqlite3.Connection:
    """Return a sqlite3.Connection with both cache + audit schemas.

    Legacy entry point — kept for backward compatibility with tests. New
    production code uses ``get_cache_conn`` / ``get_audit_conn``.
    """
    from notion_bulk_edit.config import get_cache_db_path  # lazy import

    resolved = path if path is not None else get_cache_db_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn


def get_cache_conn(path: pathlib.Path | None = None) -> sqlite3.Connection:
    """BUG-OP-09: open the cache-only database.

    With *path* = None, opens the production ``cache.db``. Auto-creates
    the parent directory and runs ``init_cache_db`` so the schema is
    always ready.
    """
    from notion_bulk_edit.config import get_cache_db_path  # lazy import

    resolved = path if path is not None else get_cache_db_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_cache_db(conn)
    return conn


def get_audit_db_path() -> pathlib.Path:
    """BUG-OP-09: ``%APPDATA%\\NotionRPADV\\audit.db``."""
    from notion_bulk_edit.config import get_cache_dir  # lazy import
    return get_cache_dir() / "audit.db"


def get_audit_conn(path: pathlib.Path | None = None) -> sqlite3.Connection:
    """BUG-OP-09: open the audit-only database (pending_edits + edit_log)."""
    resolved = path if path is not None else get_audit_db_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_audit_db(conn)
    return conn


# ---------------------------------------------------------------------------
# Migration: legacy combined cache.db → split cache + audit
# ---------------------------------------------------------------------------


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def _get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM meta WHERE key=?", (key,)
    ).fetchone()
    return None if row is None else str(row["value"])


def migrate_audit_from_cache_if_needed(
    cache_conn: sqlite3.Connection,
    audit_conn: sqlite3.Connection,
) -> int:
    """BUG-OP-09: copy ``pending_edits`` and ``edit_log`` rows from the
    legacy *cache_conn* to the new *audit_conn*, then drop them from the
    cache. Returns the number of rows migrated.

    Idempotent — flagged in ``audit_conn.meta[audit_migrated_v1]``. Safe
    to call on every boot. Migration runs in a single audit transaction
    so a crash mid-copy leaves audit_conn empty (caller can re-run).
    Cache-side ``DROP TABLE`` happens only after the audit commit.
    """
    if _get_meta(audit_conn, AUDIT_MIGRATION_KEY) is not None:
        return 0
    has_pending = _table_exists(cache_conn, "pending_edits")
    has_log = _table_exists(cache_conn, "edit_log")
    if not has_pending and not has_log:
        # Nothing to do — fresh install. Mark anyway to skip on reboots.
        _set_meta(audit_conn, AUDIT_MIGRATION_KEY, "true")
        return 0

    pending_rows = (
        list(cache_conn.execute("SELECT * FROM pending_edits"))
        if has_pending else []
    )
    log_rows = (
        list(cache_conn.execute("SELECT * FROM edit_log"))
        if has_log else []
    )

    try:
        audit_conn.execute("BEGIN")
        for r in pending_rows:
            audit_conn.execute(
                "INSERT OR IGNORE INTO pending_edits "
                "(id, base, page_id, key, old_value, new_value, created_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    r["id"], r["base"], r["page_id"], r["key"],
                    r["old_value"], r["new_value"], r["created_at"], r["status"],
                ),
            )
        for r in log_rows:
            audit_conn.execute(
                "INSERT OR IGNORE INTO edit_log "
                "(id, base, page_id, key, old_value, new_value, applied_at, user, reverted) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    r["id"], r["base"], r["page_id"], r["key"],
                    r["old_value"], r["new_value"], r["applied_at"],
                    r["user"], r["reverted"],
                ),
            )
        audit_conn.commit()
    except Exception:
        audit_conn.rollback()
        raise

    # Audit side committed; now drop legacy tables from cache. A failure
    # here leaves the duplicate rows behind, which is safe because the
    # migration flag is set after this block.
    try:
        if has_pending:
            cache_conn.execute("DROP TABLE pending_edits")
        if has_log:
            cache_conn.execute("DROP TABLE edit_log")
        cache_conn.commit()
    except Exception:
        cache_conn.rollback()
        # Don't re-raise: audit already has the rows; the migration is
        # functionally complete.

    _set_meta(audit_conn, AUDIT_MIGRATION_KEY, "true")
    return len(pending_rows) + len(log_rows)


def backup_legacy_cache_file(cache_path: pathlib.Path) -> pathlib.Path | None:
    """BUG-OP-09: copy ``cache.db`` to ``cache.db.bak`` once, before the
    very first migration, so a corrupt migration can be recovered by
    hand. Returns the backup path, or None if the cache file isn't
    present.

    Skips silently if the backup already exists — backups are not
    rotated to avoid silently overwriting useful disaster-recovery data.
    """
    if not cache_path.exists():
        return None
    bak = cache_path.with_suffix(cache_path.suffix + ".bak")
    if bak.exists():
        return bak
    try:
        shutil.copy2(cache_path, bak)
    except Exception:  # noqa: BLE001
        return None
    return bak


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


def upsert_pending_edit(
    conn: sqlite3.Connection,
    base: str,
    page_id: str,
    key: str,
    old_value: Any,
    new_value: Any,
) -> int:
    """BUG-OP-02: idempotent insert/update of a pending edit for *(base,
    page_id, key)*. Returns the id of the existing or newly-created row.

    If a pending row already exists for the cell, only the *new_value* and
    *created_at* are refreshed — the original *old_value* is preserved so the
    revert chain stays anchored on the cache value at the time the user
    started editing, not a re-read of the (potentially mutated) cell.
    """
    row = conn.execute(
        "SELECT id FROM pending_edits "
        "WHERE base=? AND page_id=? AND key=? AND status='pending' LIMIT 1",
        (base, page_id, key),
    ).fetchone()
    now = time.time()
    new_json = json.dumps(new_value, ensure_ascii=False, default=str)
    if row is not None:
        edit_id = int(row["id"])
        conn.execute(
            "UPDATE pending_edits SET new_value=?, created_at=? WHERE id=?",
            (new_json, now, edit_id),
        )
        conn.commit()
        return edit_id
    old_json = json.dumps(old_value, ensure_ascii=False, default=str)
    cursor = conn.execute(
        "INSERT INTO pending_edits "
        "(base, page_id, key, old_value, new_value, created_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
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
