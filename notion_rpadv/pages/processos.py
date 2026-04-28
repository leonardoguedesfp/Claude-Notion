"""Processos page."""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import QWidget

from notion_rpadv.cache.sync import SyncManager
from notion_rpadv.models.delegates import CnjDelegate
from notion_rpadv.pages.base_table_page import BaseTablePage
from notion_rpadv.services.notion_facade import NotionFacade


class ProcessosPage(BaseTablePage):
    """Table page for the Processos base."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        token: str,
        user: str,
        facade: NotionFacade,
        sync_manager: SyncManager | None = None,
        dark: bool = False,
        parent: QWidget | None = None,
        audit_conn: sqlite3.Connection | None = None,
    ) -> None:
        super().__init__(
            base="Processos",
            conn=conn,
            token=token,
            user=user,
            facade=facade,
            sync_manager=sync_manager,
            dark=dark,
            parent=parent,
            audit_conn=audit_conn,
        )
        # P1-002 (Lote 1): instância única do CnjDelegate cacheada e
        # reaplicada via _install_delegates a cada modelReset.
        self._cnj_delegate = CnjDelegate(self._table)
        # §3.8: install the CNJ-specific delegate on the CNJ column so rows
        # with a `processo_pai` render the parent CNJ inline (↳ ABOVE own).
        self._install_delegates()
        self._model.modelReset.connect(self._install_delegates)

    def _install_delegates(self) -> None:
        """P1-002 (Lote 1): re-resolve índice de 'numero_do_processo' a
        partir do estado atual de ``_cols``. Em Processos o título é
        sempre o índice 0 (não pode ser ocultado pelo picker), mas o
        re-bind protege contra reordenações futuras."""
        col_count = self._table.model().columnCount() if self._table.model() else 0
        for col_idx in range(col_count):
            self._table.setItemDelegateForColumn(col_idx, None)
        cols = self._model.cols()
        if "numero_do_processo" in cols:
            cnj_col = cols.index("numero_do_processo")
            self._table.setItemDelegateForColumn(cnj_col, self._cnj_delegate)
