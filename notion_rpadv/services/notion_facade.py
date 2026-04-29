"""High-level service layer: applies pending edits from cache to Notion API."""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from notion_bulk_edit.encoders import encode_value
from notion_bulk_edit.notion_api import NotionAPIError, NotionAuthError, NotionClient
from notion_bulk_edit.schemas import get_prop
from notion_rpadv.cache import db as cache_db

logger = logging.getLogger(__name__)


class CommitWorker(QObject):
    """Sends dirty edits to Notion in a background thread.

    Each element of *edits* is expected to be a dict with keys:
        id, base, page_id, key, old_value, new_value
    (the shape returned by cache_db.get_pending_edits()).

    Emits:
        progress(done: int, total: int)
        finished(base: str, results: list[dict])
            BUG-OP-03: per-cell results so callers can clear only the
            successful dirty cells and surface the failures by name.
            Each dict carries:
                {"page_id": str, "key": str, "edit_id": int,
                 "ok": bool, "error": str | None}
        error(message: str)  — fatal, no edits were applied
        auth_invalidated()   — BUG-OP-11: token expired or revoked. Surfaced
            to the application so a re-auth dialog can be shown without
            tearing down dirty state.
    """

    progress: Signal = Signal(int, int)
    # BUG-OP-03: switched to (base, results). Old (base, succeeded, failed)
    # tuple is reconstructible from `results` by counting; this shape lets
    # callers clear only the successful dirty cells.
    finished: Signal = Signal(str, list)
    error: Signal = Signal(str)
    # BUG-OP-11: signal that Notion rejected our token mid-commit.
    auth_invalidated: Signal = Signal()

    def __init__(
        self,
        token: str,
        conn: sqlite3.Connection,
        edits: list[dict[str, Any]],
        user: str = "",
        base: str = "",
        audit_conn: sqlite3.Connection | None = None,
    ) -> None:
        super().__init__()
        self._token = token
        self._conn = conn
        # BUG-OP-09: pending_edits/edit_log live in audit.db. Fall back to
        # the cache conn for legacy in-memory tests where both schemas
        # share one handle.
        self._audit_conn: sqlite3.Connection = audit_conn or conn
        self._edits = edits
        self._user = user
        self._base = base

    def run(self) -> None:
        """For each edit: encode_value + client.update_page + mark_edit_applied.

        BUG-OP-01: every successful API call calls
        ``cache_db.mark_edit_applied(edit_id, user)`` to move the row from
        ``pending_edits`` to ``edit_log``. Edit ids reach this point as
        non-zero only after _on_save → flush_dirty_to_pending; an id of 0
        signals a stale caller that bypassed the flush, in which case we
        log a warning but still let the API call go through.

        Phases are separated: an exception while writing to ``edit_log``
        must not mask a successful API call, otherwise the cell stays
        marked dirty forever even though Notion already has the new value.
        """
        try:
            client = NotionClient(self._token)
        except NotionAuthError as exc:
            # BUG-OP-11: the token itself is bad — surface for the re-auth
            # dialog before bailing.
            self.auth_invalidated.emit()
            self.error.emit(str(exc))
            return
        except NotionAPIError as exc:
            self.error.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Cannot connect to Notion: {exc}")
            return

        total = len(self._edits)
        # BUG-OP-03: collect per-cell outcomes instead of bare counters so
        # _on_commit_finished can clear only the successful dirty cells and
        # name the failures in the toast.
        results: list[dict[str, Any]] = []
        # BUG-OP-11: only emit auth_invalidated once even if every edit in a
        # batch trips the same expired-token error.
        auth_emitted = False

        for i, edit in enumerate(self._edits, start=1):
            base: str = edit.get("base", self._base)
            page_id: str = edit.get("page_id", "")
            key: str = edit.get("key", "")
            new_value: Any = edit.get("new_value")
            # P1-004 (Lote 1): tolerar edit["id"] None / "" / não-numérico.
            # Antes, ``int(edit.get("id", 0))`` estourava TypeError em None
            # e ValueError em string inválida, derrubando o batch INTEIRO.
            # ``or 0`` cobre None/"" via short-circuit; try/except cobre
            # strings não-numéricas. ``edit_id == 0`` já era tratado no
            # path Phase 2 (linha do ``if edit_id:``), então um id ruim
            # apenas significa "não escreve no audit log" — outros edits
            # do batch continuam.
            try:
                edit_id: int = int(edit.get("id") or 0)
            except (TypeError, ValueError):
                logger.warning(
                    "CommitWorker: edit com id inválido %r, "
                    "tratando como 0 (sem audit log).",
                    edit.get("id"),
                )
                edit_id = 0

            def _record(ok: bool, error: str | None) -> None:
                results.append({
                    "page_id": page_id, "key": key, "edit_id": edit_id,
                    "ok": ok, "error": error,
                })

            spec = get_prop(base, key)
            if spec is None:
                _record(False, f"Property '{key}' missing from schema '{base}'")
                self.progress.emit(i, total)
                continue

            # Phase 1 — API call. A failure here leaves the pending_edits
            # row untouched (status='pending') so a retry can pick it up.
            try:
                # BUG-01: fixed argument order — encode_value(value, tipo)
                encoded = encode_value(new_value, spec.tipo)
                client.update_page(page_id, {spec.notion_name: encoded})
            except NotionAuthError as exc:
                # BUG-OP-11: token went sideways mid-batch. Mark this and
                # the rest as auth failures and stop hammering the API.
                if not auth_emitted:
                    self.auth_invalidated.emit()
                    auth_emitted = True
                _record(False, str(exc) or "Token inválido ou sem permissão.")
                self.progress.emit(i, total)
                continue
            except NotionAPIError as exc:
                _record(False, str(exc))
                self.progress.emit(i, total)
                continue
            except Exception as exc:  # noqa: BLE001
                _record(False, f"Erro inesperado: {exc}")
                self.progress.emit(i, total)
                continue

            # Phase 2 — local audit log. The API call already succeeded; a
            # DB error here must not flip the cell back to "failed", or the
            # user would re-send a value that's already in Notion.
            if edit_id:
                try:
                    # BUG-OP-09: write the audit-log entry to audit.db.
                    cache_db.mark_edit_applied(
                        self._audit_conn, edit_id, self._user,
                    )
                except Exception:  # noqa: BLE001
                    # Audit log corruption is a separate ops concern; the
                    # edit itself is durable in Notion.
                    pass
            _record(True, None)

            self.progress.emit(i, total)

        # BUG-OP-03: emit the per-cell results list. Old (succeeded, failed)
        # callers should compute `sum(1 for r in results if r["ok"])`.
        self.finished.emit(self._base, results)


class _RevertWorker(QObject):
    """Applies a single reversed edit (old_value → Notion) in a background thread."""

    finished: Signal = Signal(bool, str)  # (success, message)
    # BUG-OP-11: a revert that hits an expired token must reach the global
    # re-auth dialog the same way a save would.
    auth_invalidated: Signal = Signal()

    def __init__(
        self,
        token: str,
        conn: sqlite3.Connection,
        log_id: int,
        user: str,
        audit_conn: sqlite3.Connection | None = None,
    ) -> None:
        super().__init__()
        self._token = token
        self._conn = conn
        # BUG-OP-09: revert reads/writes from edit_log + pending_edits, all
        # in audit.db. Fall back to cache conn when caller didn't split.
        self._audit_conn: sqlite3.Connection = audit_conn or conn
        self._log_id = log_id
        self._user = user

    def run(self) -> None:
        try:
            client = NotionClient(self._token)

            # BUG-16: fetch entry WITHOUT marking reverted first
            entry = cache_db.get_log_entry(self._audit_conn, self._log_id)
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

            # Only mark reverted after successful API call (BUG-OP-09: in audit.db)
            cache_db.revert_edit(self._audit_conn, self._log_id)

            # Add a new log entry for the reversion so history is complete.
            new_edit_id = cache_db.add_pending_edit(
                self._audit_conn, base, page_id, key, entry["new_value"], old_value
            )
            cache_db.mark_edit_applied(self._audit_conn, new_edit_id, self._user)

            self.finished.emit(True, "")
        except NotionAuthError as exc:
            # BUG-OP-11: signal the global re-auth flow first; the regular
            # finished(False, …) keeps existing connectors working.
            self.auth_invalidated.emit()
            self.finished.emit(False, str(exc))
        except NotionAPIError as exc:
            self.finished.emit(False, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, f"Unexpected error: {exc}")


class NotionFacade(QObject):
    """Facade used by UI pages to commit or revert edits to Notion."""

    commit_started: Signal = Signal()
    # BUG-07: base added so pages only clear dirty for their own base.
    # BUG-OP-03: shape changed to (base, results: list[dict]) where each
    # dict is {page_id, key, edit_id, ok, error}.
    commit_finished: Signal = Signal(str, list)
    commit_error: Signal = Signal(str)

    revert_finished: Signal = Signal(bool, str)  # success, message
    # BUG-OP-11: re-broadcast from CommitWorker / _RevertWorker so a single
    # slot in MainWindow can react regardless of which path failed.
    auth_invalidated: Signal = Signal()

    def __init__(
        self,
        token: str,
        conn: sqlite3.Connection,
        audit_conn: sqlite3.Connection | None = None,
    ) -> None:
        super().__init__()
        self._token = token
        self._conn = conn
        # BUG-OP-09: route audit-log writes (mark_edit_applied, revert) to
        # the dedicated audit.db connection instead of the cache db.
        self._audit_conn: sqlite3.Connection = audit_conn or conn
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
        worker = CommitWorker(
            self._token, self._conn, edits, user, base,
            audit_conn=self._audit_conn,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_commit_finished)
        worker.error.connect(self._on_commit_error)
        # BUG-OP-11: re-broadcast the worker's auth signal at facade level
        # so MainWindow only needs one connection point.
        worker.auth_invalidated.connect(self.auth_invalidated)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._commit_thread = thread
        self._commit_worker = worker

        self.commit_started.emit()
        thread.start()

    def _on_commit_finished(self, base: str, results: list[dict[str, Any]]) -> None:
        self._commit_thread = None
        self._commit_worker = None
        self.commit_finished.emit(base, results)

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
        worker = _RevertWorker(
            self._token, self._conn, log_id, user,
            audit_conn=self._audit_conn,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_revert_finished)
        # BUG-OP-11: re-broadcast revert auth failures.
        worker.auth_invalidated.connect(self.auth_invalidated)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._revert_thread = thread
        self._revert_worker = worker

        thread.start()

    def _on_revert_finished(self, success: bool, message: str) -> None:
        self._revert_thread = None
        self._revert_worker = None
        self.revert_finished.emit(success, message)
