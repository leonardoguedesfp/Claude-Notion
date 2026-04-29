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
        total(base: str, n: int) — page count returned by the API, emitted
                                   once before any progress event so the UI
                                   can size its progress bar
        progress(base: str, count: int) — pages decoded so far
        finished(base: str, added: int, updated: int, removed: int)
        error(base: str, message: str)
    """

    # §2.3: total emitted right after `query_all` so the progress bar has a
    # determinate maximum. Without it the bar would have to stay indeterminate.
    total: Signal = Signal(str, int)
    progress: Signal = Signal(str, int)
    finished: Signal = Signal(str, int, int, int)
    error: Signal = Signal(str, str)
    # BUG-OP-11: separate signal for auth failure so the SyncManager can
    # forward it to the application-wide re-auth flow. The `error` signal
    # still fires too (it is the caller's "the sync didn't finish" channel).
    auth_invalidated: Signal = Signal()

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
        except NotionAuthError as exc:
            # BUG-OP-11: surface the auth invalidation so the global re-auth
            # dialog can open. Still emit `error` so existing per-base error
            # handlers continue to behave (status bar, toast).
            self.auth_invalidated.emit()
            self.error.emit(base, str(exc))
        except NotionAPIError as exc:
            self.error.emit(base, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(base, f"Unexpected error: {exc}")

    def _sync(self, base: str) -> None:
        client = NotionClient(self._token)
        db_id = DATA_SOURCES[base]
        raw_pages: list[dict[str, Any]] = client.query_all(db_id)
        # §2.3: announce the total now so the dashboard's progress bar has
        # a determinate maximum from the very first paint.
        self.total.emit(base, len(raw_pages))

        schema = SCHEMAS.get(base, {})

        existing_records = cache_db.get_all_records(self._conn, base)
        existing_ids: set[str] = {r["page_id"] for r in existing_records if "page_id" in r}

        added = 0
        # BUG-N2: renamed from 'updated' — counts pages already in cache, not "changed"
        existing = 0
        notion_ids: set[str] = set()

        with cache_db.transaction(self._conn):
            for idx, page in enumerate(raw_pages, start=1):
                page_id: str = page.get("id", "")
                if not page_id:
                    continue

                # BUG-V5: skip template and archived/trashed pages
                if page.get("in_trash") or page.get("archived"):
                    continue
                if page.get("is_template", False):
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
                    existing += 1
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
        # BUG-N2: emit (added, existing, removed) — semantics are clear, no arithmetic
        self.finished.emit(base, added, existing, removed)


class SyncManager(QObject):
    """Manages sync workers across all bases defined in DATA_SOURCES.

    BUG-14: workers run sequentially (one at a time) to avoid concurrent
    writes to the shared SQLite connection from multiple QThreads.
    """

    all_done: Signal = Signal()
    base_done: Signal = Signal(str, int, int, int)
    sync_error: Signal = Signal(str, str)
    # §2.3: per-base lifecycle signals so the Dashboard sync panel and the
    # global progress strip can paint live state without polling.
    base_started: Signal = Signal(str)            # base
    base_total: Signal = Signal(str, int)         # base, total pages
    base_progress: Signal = Signal(str, int)      # base, pages processed
    # BUG-OP-11: re-broadcast worker auth failures so MainWindow can open
    # the re-auth dialog whether the failure came from a sync or a save.
    auth_invalidated: Signal = Signal()

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
        # §2.3: forward total/progress so dashboard widgets can paint live
        # progress without hooking into the worker directly.
        worker.total.connect(self.base_total)
        worker.progress.connect(self.base_progress)
        # BUG-OP-11: forward auth failures up to MainWindow.
        worker.auth_invalidated.connect(self.auth_invalidated)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        # P2-004 (Lote 2): worker e thread agora ambos recebem
        # deleteLater. Antes, só thread.deleteLater era conectado — o
        # QObject worker sobrevivia ao GC do Python (parent=None pos
        # moveToThread), criando leak pequeno mas crescente em sessoes
        # longas (~1 worker por sync_base).
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        # When thread finishes, start the next queued one
        thread.finished.connect(self._start_next)
        thread.finished.connect(thread.deleteLater)

        self._threads[base] = thread
        self._workers[base] = worker

        # §2.3: announce that this base is now actively syncing — the
        # dashboard chip flips to "Sincronizando…" before the first network
        # call returns.
        self.base_started.emit(base)
        thread.start()

    def _on_worker_finished(
        self, base: str, added: int, existing: int, removed: int
    ) -> None:
        # BUG-N5: pop dead thread refs so isRunning() check in sync_base() doesn't crash
        self._threads.pop(base, None)
        self._workers.pop(base, None)
        self.base_done.emit(base, added, existing, removed)
        self._pending.discard(base)
        if not self._pending:
            self.all_done.emit()

    def _on_worker_error(self, base: str, message: str) -> None:
        # BUG-N5: pop dead thread refs
        self._threads.pop(base, None)
        self._workers.pop(base, None)
        self.sync_error.emit(base, message)
        self._pending.discard(base)
        if not self._pending:
            self.all_done.emit()
