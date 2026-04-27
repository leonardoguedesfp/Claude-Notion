"""High-level service layer: applies pending edits from cache to Notion API."""
from __future__ import annotations

import sqlite3
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from notion_bulk_edit.encoders import encode_value
from notion_bulk_edit.notion_api import NotionAPIError, NotionAuthError, NotionClient
from notion_bulk_edit.schemas import get_prop
from notion_rpadv.cache import db as cache_db


class CommitWorker(QObject):
    """Sends dirty edits to Notion in a background thread.

    Each element of *edits* is expected to be a dict with keys:
        id, base, page_id, key, old_value, new_value
    (the shape returned by cache_db.get_pending_edits()).

    Emits:
        progress(done: int, total: int)
        finished(base: str, succeeded: int, failed: int)
        error(message: str)  — fatal, no edits were applied
    """

    progress: Signal = Signal(int, int)
    finished: Signal = Signal(str, int, int)  # BUG-07: base, succeeded, failed
    error: Signal = Signal(str)

    def __init__(
        self,
        token: str,
        conn: sqlite3.Connection,
        edits: list[dict[str, Any]],
        user: str = "",
        base: str = "",
    ) -> None:
        super().__init__()
        self._token = token
        self._conn = conn
        self._edits = edits
        self._user = user
        self._base = base

    def run(self) -> None:
        """For each edit: encode_value + client.update_page + mark_edit_applied."""
        try:
            client = NotionClient(self._token)
        except (NotionAuthError, NotionAPIError) as exc:
            self.error.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Cannot connect to Notion: {exc}")
            return

        total = len(self._edits)
        succeeded = 0
        failed = 0

        for i, edit in enumerate(self._edits, start=1):
            base: str = edit.get("base", self._base)
            page_id: str = edit.get("page_id", "")
            key: str = edit.get("key", "")
            new_value: Any = edit.get("new_value")
            edit_id: int = int(edit.get("id", 0))

            spec = get_prop(base, key)
            if spec is None:
                failed += 1
                self.progress.emit(i, total)
                continue

            try:
                # BUG-01: fixed argument order — encode_value(value, tipo)
                encoded = encode_value(new_value, spec.tipo)
                client.update_page(page_id, {spec.notion_name: encoded})
                if edit_id:
                    cache_db.mark_edit_applied(self._conn, edit_id, self._user)
                succeeded += 1
            except (NotionAPIError, NotionAuthError):
                failed += 1
            except Exception:  # noqa: BLE001
                failed += 1

            self.progress.emit(i, total)

        # BUG-07: emit base along with counts
        self.finished.emit(self._base, succeeded, failed)


class _RevertWorker(QObject):
    """Applies a single reversed edit (old_value → Notion) in a background thread."""

    finished: Signal = Signal(bool, str)  # (success, message)

    def __init__(
        self,
        token: str,
        conn: sqlite3.Connection,
        log_id: int,
        user: str,
    ) -> None:
        super().__init__()
        self._token = token
        self._conn = conn
        self._log_id = log_id
        self._user = user

    def run(self) -> None:
        try:
            client = NotionClient(self._token)

            # BUG-16: fetch entry WITHOUT marking reverted first
            entry = cache_db.get_log_entry(self._conn, self._log_id)
            if entry is None:
                self.finished.emit(False, f"Log entry {self._log_id} not found.")
                return

            base: str = entry["base"]
            page_id: str = entry["page_id"]
            key: str = entry["key"]
            old_value: Any = entry["old_value"]

            spec = get_prop(base, key)
            if spec is None:
                self.finished.emit(False, f"Property '{key}' not found in schema '{base}'.")
                return

            # BUG-01: fixed argument order — encode_value(value, tipo)
            encoded = encode_value(old_value, spec.tipo)

            # BUG-16: API call BEFORE marking reverted in DB
            client.update_page(page_id, {spec.notion_name: encoded})

            # Only mark reverted after successful API call
            cache_db.revert_edit(self._conn, self._log_id)

            # Add a new log entry for the reversion so history is complete.
            new_edit_id = cache_db.add_pending_edit(
                self._conn, base, page_id, key, entry["new_value"], old_value
            )
            cache_db.mark_edit_applied(self._conn, new_edit_id, self._user)

            self.finished.emit(True, "")
        except (NotionAPIError, NotionAuthError) as exc:
            self.finished.emit(False, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, f"Unexpected error: {exc}")


class NotionFacade(QObject):
    """Facade used by UI pages to commit or revert edits to Notion."""

    commit_started: Signal = Signal()
    # BUG-07: base added so pages only clear dirty for their own base
    commit_finished: Signal = Signal(str, int, int)   # base, succeeded, failed
    commit_error: Signal = Signal(str)

    revert_finished: Signal = Signal(bool, str)  # success, message

    def __init__(self, token: str, conn: sqlite3.Connection) -> None:
        super().__init__()
        self._token = token
        self._conn = conn
        self._commit_thread: QThread | None = None
        self._commit_worker: CommitWorker | None = None
        self._revert_thread: QThread | None = None
        self._revert_worker: _RevertWorker | None = None

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------

    def commit_edits(self, edits: list[dict[str, Any]], user: str, base: str = "") -> None:
        """Launch CommitWorker in a QThread to push *edits* to Notion."""
        if self._commit_thread is not None and self._commit_thread.isRunning():
            return  # already busy

        thread = QThread(self)
        worker = CommitWorker(self._token, self._conn, edits, user, base)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_commit_finished)
        worker.error.connect(self._on_commit_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._commit_thread = thread
        self._commit_worker = worker

        self.commit_started.emit()
        thread.start()

    def _on_commit_finished(self, base: str, succeeded: int, failed: int) -> None:
        self._commit_thread = None
        self._commit_worker = None
        self.commit_finished.emit(base, succeeded, failed)

    def _on_commit_error(self, message: str) -> None:
        self._commit_thread = None
        self._commit_worker = None
        self.commit_error.emit(message)

    # ------------------------------------------------------------------
    # Revert
    # ------------------------------------------------------------------

    def revert_log_entry(self, log_id: int, user: str) -> None:
        """Reverse a logged edit by applying the old_value back to Notion."""
        if self._revert_thread is not None and self._revert_thread.isRunning():
            return

        thread = QThread(self)
        worker = _RevertWorker(self._token, self._conn, log_id, user)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_revert_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._revert_thread = thread
        self._revert_worker = worker

        thread.start()

    def _on_revert_finished(self, success: bool, message: str) -> None:
        self._revert_thread = None
        self._revert_worker = None
        self.revert_finished.emit(success, message)
