"""Syncs Notion → SQLite. Runs in a background QThread."""
from __future__ import annotations

import sqlite3
import time
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from notion_bulk_edit.config import DATA_SOURCES
from notion_bulk_edit.encoders import decode_value
from notion_bulk_edit.notion_api import NotionAPIError, NotionAuthError, NotionClient
from notion_bulk_edit.schemas import SCHEMAS
from notion_rpadv.cache import db as cache_db


class SyncWorker(QObject):
    """Sync worker that runs in a QThread.

    Emits:
        progress(base: str, count: int) — pages fetched so far
        finished(base: str, added: int, updated: int, removed: int)
        error(base: str, message: str)
    """

    progress: Signal = Signal(str, int)
    finished: Signal = Signal(str, int, int, int)
    error: Signal = Signal(str, str)

    def __init__(
        self,
        token: str,
        base: str,
        conn: sqlite3.Connection,
    ) -> None:
        super().__init__()
        self._token = token
        self._base = base
        self._conn = conn

    def run(self) -> None:
        """Fetch all pages from Notion and upsert into SQLite."""
        # BUG-15: wrap entire body in try/except to prevent silent crashes
        base = self._base
        try:
            self._sync(base)
        except (NotionAuthError, NotionAPIError) as exc:
            self.error.emit(base, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(base, f"Unexpected error: {exc}")

    def _sync(self, base: str) -> None:
        client = NotionClient(self._token)
        db_id = DATA_SOURCES[base]
        raw_pages: list[dict[str, Any]] = client.query_all(db_id)

        schema = SCHEMAS.get(base, {})

        existing_records = cache_db.get_all_records(self._conn, base)
        existing_ids: set[str] = {r["page_id"] for r in existing_records if "page_id" in r}

        added = 0
        updated = 0
        notion_ids: set[str] = set()

        with cache_db.transaction(self._conn):
            for idx, page in enumerate(raw_pages, start=1):
                page_id: str = page.get("id", "")
                if not page_id:
                    continue

                notion_ids.add(page_id)

                decoded: dict[str, Any] = {"page_id": page_id}
                notion_props: dict[str, Any] = page.get("properties", {})

                for prop_key, spec in schema.items():
                    notion_prop = notion_props.get(spec.notion_name)
                    if notion_prop is not None:
                        try:
                            decoded[prop_key] = decode_value(notion_prop, spec.tipo)
                        except Exception:  # noqa: BLE001
                            decoded[prop_key] = None
                    else:
                        decoded[prop_key] = None

                if page_id in existing_ids:
                    updated += 1
                else:
                    added += 1

                cache_db.upsert_record(self._conn, base, page_id, decoded)

                if idx % 50 == 0:
                    self.progress.emit(base, idx)

        removed_ids = existing_ids - notion_ids
        removed = len(removed_ids)
        if removed_ids:
            with cache_db.transaction(self._conn):
                for pid in removed_ids:
                    cache_db.delete_record(self._conn, base, pid)

        cache_db.set_last_sync(self._conn, base, time.time())
        self.progress.emit(base, len(raw_pages))
        # BUG-12: emit correct updated count (pages that existed before, not counting added)
        truly_updated = updated - added if updated >= added else 0
        self.finished.emit(base, added, truly_updated, removed)


class SyncManager(QObject):
    """Manages sync workers across all bases defined in DATA_SOURCES.

    BUG-14: workers run sequentially (one at a time) to avoid concurrent
    writes to the shared SQLite connection from multiple QThreads.
    """

    all_done: Signal = Signal()
    base_done: Signal = Signal(str, int, int, int)
    sync_error: Signal = Signal(str, str)

    def __init__(self, token: str, conn: sqlite3.Connection) -> None:
        super().__init__()
        self._token = token
        self._conn = conn
        self._threads: dict[str, QThread] = {}
        self._workers: dict[str, SyncWorker] = {}
        self._pending: set[str] = set()
        # BUG-14: queue for sequential execution
        self._queue: list[str] = []
        self._running: bool = False

    def sync_all(self) -> None:
        """Start sync for every base in DATA_SOURCES (sequentially)."""
        for base in DATA_SOURCES:
            self.sync_base(base)

    def sync_base(self, base: str) -> None:
        """Enqueue sync for *base*; starts immediately if nothing is running."""
        if base in self._threads and self._threads[base].isRunning():
            return
        if base in self._queue:
            return

        self._pending.add(base)
        self._queue.append(base)

        if not self._running:
            self._start_next()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_next(self) -> None:
        """BUG-14: start the next queued base, ensuring serial execution."""
        if not self._queue:
            self._running = False
            return

        self._running = True
        base = self._queue.pop(0)

        thread = QThread(self)
        worker = SyncWorker(self._token, base, self._conn)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(lambda b, a, u, r: self._on_worker_finished(b, a, u, r))
        worker.error.connect(lambda b, msg: self._on_worker_error(b, msg))
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        # When thread finishes, start the next queued one
        thread.finished.connect(self._start_next)
        thread.finished.connect(thread.deleteLater)

        self._threads[base] = thread
        self._workers[base] = worker

        thread.start()

    def _on_worker_finished(
        self, base: str, added: int, updated: int, removed: int
    ) -> None:
        self.base_done.emit(base, added, updated, removed)
        self._pending.discard(base)
        if not self._pending:
            self.all_done.emit()

    def _on_worker_error(self, base: str, message: str) -> None:
        self.sync_error.emit(base, message)
        self._pending.discard(base)
        if not self._pending:
            self.all_done.emit()
